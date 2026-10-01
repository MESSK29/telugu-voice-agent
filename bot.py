"""
Telugu Voice Agent - Pipecat + FastAPI + Twilio

Cold-start readiness: GET /health returns {"ready": true} only after the
server is fully initialised and able to accept WebSocket connections.
The bowls-n-jars backend polls this endpoint before placing any calls.
"""

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response, JSONResponse
import uvicorn
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
import os
import json
import logging

from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import TranscriptionFrame, TextFrame

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("telugu-voice-agent")

# ---------------------------------------------------------------------------
# Readiness flag — True only after startup completes successfully.
# ---------------------------------------------------------------------------
_server_ready = False

app = FastAPI(title="Telugu Voice Agent")


@app.on_event("startup")
async def on_startup():
    """
    Mark the server as ready once FastAPI finishes startup.
    Heavy work (model loading, warm-up calls) belongs here, NOT in the
    WebSocket handler, so HTTP readiness can be reported accurately.
    """
    global _server_ready
    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not sarvam_api_key or not groq_api_key:
        logger.error(
            "STARTUP FAILED: SARVAM_API_KEY and/or GROQ_API_KEY not set. "
            "Server will NOT accept calls (/health returns ready=false)."
        )
        return
    logger.info("All API keys present. Server is READY to accept WebSocket connections.")
    _server_ready = True


@app.get("/")
async def root():
    return {"status": "ok", "service": "Telugu Voice Agent"}


@app.get("/health")
async def health():
    """
    Readiness probe polled by bowls-n-jars before placing any batch calls.
    HTTP 200 + {ready: true}  => server fully up, safe to call.
    HTTP 503 + {ready: false} => still initialising (cold start).
    """
    if _server_ready:
        return JSONResponse(status_code=200, content={"ready": True, "service": "Telugu Voice Agent"})
    return JSONResponse(
        status_code=503,
        content={"ready": False, "service": "Telugu Voice Agent", "reason": "initialising"},
    )


@app.get("/wake-up")
async def wake_up():
    """Alias for /health — kept for backward compat with older bowls-n-jars calls."""
    return await health()


class DebugInputProcessor(FrameProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._first_audio_in = False

    async def process_frame(self, frame, direction):
        if type(frame).__name__ == "InputAudioRawFrame" and not self._first_audio_in:
            print("\n[INFO - TRANSPORT IN] Received FIRST raw audio frame from Twilio!")
            self._first_audio_in = True
        elif isinstance(frame, TranscriptionFrame):
            print(f"\n[INFO - STT OUTPUT] User said: {frame.text}")
        await self.push_frame(frame, direction)

class DebugOutputProcessor(FrameProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tts_started = False
        self._first_audio_out = False

    async def process_frame(self, frame, direction):
        if isinstance(frame, TextFrame):
            print(f"\n[INFO - LLM OUTPUT] Agent says: {frame.text}")
        elif type(frame).__name__ == "TTSAudioRawFrame":
            if not self._tts_started:
                print("\n[INFO - TTS OUTPUT] TTS started generating audio...")
                self._tts_started = True
        elif type(frame).__name__ == "OutputAudioRawFrame" and not self._first_audio_out:
            print("\n[INFO - TRANSPORT OUT] Sending FIRST raw audio frame back to Twilio!")
            self._first_audio_out = True
        elif type(frame).__name__ == "LLMFullResponseEndFrame":
            print("\n[INFO] LLM finished response.")
            self._tts_started = False
            self._first_audio_out = False
        await self.push_frame(frame, direction)

@app.post("/voice")
async def voice(request: Request):
    name = request.query_params.get("name", "")
    details = request.query_params.get("details", "")
    phone = request.query_params.get("phone", "")
    host = request.headers.get("host")
    scheme = "wss" if request.url.scheme == "https" else "ws"

    import urllib.parse
    import html

    enc_name = urllib.parse.quote(name)
    enc_details = urllib.parse.quote(details)
    enc_phone = urllib.parse.quote(phone)

    # Sanity-check: the '+' must survive URL encoding round-trip.
    if phone and "+" in phone:
        decoded_back = urllib.parse.unquote(enc_phone)
        assert decoded_back.startswith("+"), (
            f"[BUG] Phone lost its '+' after encoding: raw={phone!r} encoded={enc_phone!r} decoded={decoded_back!r}"
        )
    logger.info(f"[VOICE TWIML] phone raw={phone!r} enc={enc_phone!r}")

    safe_name = html.escape(name)
    safe_details = html.escape(details)
    safe_phone = html.escape(phone)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{scheme}://{host}/ws?name={enc_name}&amp;details={enc_details}&amp;phone={enc_phone}">
      <Parameter name="customer_name" value="{safe_name}" />
      <Parameter name="customer_details" value="{safe_details}" />
      <Parameter name="customer_phone" value="{safe_phone}" />
    </Stream>
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, name: str = "", details: str = "", phone: str = ""):
    # -----------------------------------------------------------------------
    # EARLIEST POSSIBLE LOG — before accept(), before any pipeline setup.
    # Distinguishes "handshake never arrived" from "setup crashed".
    # -----------------------------------------------------------------------
    logger.info(
        f"[WS] WebSocket upgrade request received — "
        f"name={name!r} phone={phone!r} ready={_server_ready}"
    )

    await websocket.accept()
    logger.info("[WS] WebSocket ACCEPTED by FastAPI — Twilio handshake complete.")

    # Reject connections when the server isn't fully ready (e.g. mid cold-start)
    if not _server_ready:
        logger.error("[WS] Server not ready — closing with 1013 (Try Again Later).")
        await websocket.close(code=1013)
        return

    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    if not sarvam_api_key or not groq_api_key:
        logger.error("[WS] API keys missing — closing connection.")
        await websocket.close(code=1011)
        return

    try:
        # ------------------------------------------------------------------
        # Wait for Twilio's "start" event to extract stream_sid / call_sid.
        # Twilio typically sends 'connected' then 'start' (up to 5 msgs).
        # ------------------------------------------------------------------
        stream_sid = ""
        call_sid = ""

        logger.info("[WS] Waiting for Twilio 'start' event...")
        for _ in range(5):
            msg = await websocket.receive_text()
            data = json.loads(msg)
            event = data.get("event", "")
            logger.info(f"[WS] Twilio event received: {event!r}")
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                call_sid = data["start"]["callSid"]
                logger.info(
                    f"[WS] Twilio 'start' event OK — "
                    f"streamSid={stream_sid!r} callSid={call_sid!r}"
                )
                break

        if not stream_sid:
            logger.error("[WS] Never received Twilio 'start' event — closing connection.")
            await websocket.close(code=1011)
            return

        # ------------------------------------------------------------------
        # Build transport with correct stream_sid / call_sid and auto_hang_up=False.
        # ------------------------------------------------------------------
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                add_wav_header=False,
                serializer=TwilioFrameSerializer(
                    stream_sid=stream_sid,
                    call_sid=call_sid,
                    params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
                ),
            ),
        )

        stt = SarvamSTTService(api_key=sarvam_api_key, language="te-IN")

        tts = SarvamTTSService(
            api_key=sarvam_api_key,
            settings=SarvamTTSService.Settings(voice="priya"),
        )

        llm = GroqLLMService(
            api_key=groq_api_key,
            settings=GroqLLMService.Settings(model="llama-3.1-8b-instant"),
        )

        if name:
            system_prompt = (
                f"Nuvvu oka sahayaka voice agent vi. Telugu lo maatlaadu. "
                f"You are calling {name}. Details: {details}. "
                "Caller adigina prashnalaku chinnaga, spashtanga mariyu sahajanga samaadhaanam ivvu. "
                "Phone conversation kabatti responses short ga unchandi."
            )
        else:
            system_prompt = (
                "Nuvvu oka sahayaka voice agent vi. Telugu lo maatlaadu. "
                "Caller adigina prashnalaku chinnaga, spashtanga mariyu sahajanga samaadhaanam ivvu. "
                "Phone conversation kabatti responses short ga unchandi."
            )

        context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
        context_aggregators = LLMContextAggregatorPair(context=context)

        debug_input = DebugInputProcessor()
        debug_output = DebugOutputProcessor()

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                debug_input,
                context_aggregators.user(),
                llm,
                debug_output,
                tts,
                context_aggregators.assistant(),
                transport.output(),
            ]
        )

        worker = PipelineWorker(pipeline, params=PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("[WS] Pipecat client connected — kickstarting with Telugu greeting.")
            # pipecat 1.12: use worker.queue_frame() directly (worker.task does not exist)
            try:
                await worker.queue_frame(
                    TranscriptionFrame(text="Hello", user_id="user", timestamp="0")
                )
                logger.info("[WS] Kickstart TranscriptionFrame queued successfully.")
            except Exception as kick_err:
                logger.error(f"[WS] Failed to queue kickstart frame: {kick_err}")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("[WS] Pipecat client disconnected.")
            await worker.cancel()

        logger.info("[WS] Pipeline built. Starting PipelineWorker...")
        await worker.run()
        logger.info("[WS] PipelineWorker finished normally.")

        # ------------------------------------------------------------------
        # Post-call: send conversation summary to webhook
        # ------------------------------------------------------------------
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            logger.info("[WS] Sending call log to webhook...")
            conversation = []
            for msg in context.messages:
                if msg.get("role") in ["user", "assistant"]:
                    conversation.append(f"{msg['role'].upper()}: {msg.get('content')}")
            summary = "\n".join(conversation)
            payload = {
                "timestamp": datetime.now().isoformat(),
                "caller_number": phone or "Unknown",
                "summary": summary,
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload) as resp:
                        logger.info(f"[WS] Webhook response status: {resp.status}")
            except Exception as e:
                logger.error(f"[WS] Failed to send webhook: {e}")

    except Exception as e:
        logger.exception(f"[WS] FATAL ERROR in pipeline: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
