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
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import (
    TranscriptionFrame,
    TextFrame,
    LLMMessagesAppendFrame,
    LLMRunFrame,
)

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
@app.head("/")
async def root():
    return {"status": "ok", "service": "Telugu Voice Agent"}


@app.get("/health")
@app.head("/health")
async def health():
    """
    Readiness probe polled by bowls-n-jars before placing any batch calls.
    Also used by Render's health check (both GET and HEAD).
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
@app.head("/wake-up")
async def wake_up():
    """Alias for /health — kept for backward compat with older bowls-n-jars calls."""
    return await health()


class DebugInputProcessor(FrameProcessor):
    """Logs every frame entering the STT stage (between transport.input() and STT)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._first_audio_in = False

    async def process_frame(self, frame, direction):
        frame_name = type(frame).__name__
        if frame_name == "InputAudioRawFrame":
            if not self._first_audio_in:
                logger.info("[PIPELINE-IN] First InputAudioRawFrame received from Twilio.")
                self._first_audio_in = True
        elif isinstance(frame, TranscriptionFrame):
            logger.info(f"[PIPELINE-IN] TranscriptionFrame: text={frame.text!r} finalized={frame.finalized}")
        elif isinstance(frame, LLMMessagesAppendFrame):
            logger.info(f"[PIPELINE-IN] LLMMessagesAppendFrame: msgs={frame.messages!r} run_llm={frame.run_llm}")
        elif frame_name not in ("HeartbeatFrame", "StartFrame", "EndFrame"):
            logger.info(f"[PIPELINE-IN] Frame: {frame_name}")
        await self.push_frame(frame, direction)


class DebugOutputProcessor(FrameProcessor):
    """Logs every frame leaving the LLM (between LLM and TTS)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tts_started = False
        self._first_audio_out = False

    async def process_frame(self, frame, direction):
        frame_name = type(frame).__name__
        if isinstance(frame, TextFrame):
            logger.info(f"[PIPELINE-OUT] TextFrame (LLM output): {frame.text!r}")
        elif frame_name == "TTSAudioRawFrame":
            if not self._tts_started:
                logger.info("[PIPELINE-OUT] TTS started generating audio.")
                self._tts_started = True
        elif frame_name == "TTSStartedFrame":
            logger.info("[PIPELINE-OUT] TTSStartedFrame.")
        elif frame_name == "TTSStoppedFrame":
            logger.info("[PIPELINE-OUT] TTSStoppedFrame.")
            self._tts_started = False
        elif frame_name == "LLMFullResponseStartFrame":
            logger.info("[PIPELINE-OUT] LLM response START.")
        elif frame_name == "LLMFullResponseEndFrame":
            logger.info("[PIPELINE-OUT] LLM response END.")
            self._tts_started = False
            self._first_audio_out = False
        elif frame_name == "OutputAudioRawFrame":
            if not self._first_audio_out:
                logger.info("[PIPELINE-OUT] First OutputAudioRawFrame sent to Twilio.")
                self._first_audio_out = True
        elif frame_name not in ("HeartbeatFrame", "StartFrame", "EndFrame"):
            logger.info(f"[PIPELINE-OUT] Frame: {frame_name}")
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

        # Issue 1 fix: language must be 'te-IN' (not the default 'en-IN').
        # 'meera' is a confirmed bulbul:v3 Telugu voice.
        tts = SarvamTTSService(
            api_key=sarvam_api_key,
            settings=SarvamTTSService.Settings(
                language="te-IN",
                voice="meera",
                model="bulbul:v3",
            ),
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
        runner = WorkerRunner()
        await runner.add_workers(worker)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("[WS] Pipecat client connected — kickstarting with Telugu greeting.")
            # Issue 2 fix: TranscriptionFrame is only aggregated by LLMUserAggregator —
            # the LLM never runs until a turn-stop signal fires (which never comes for
            # a bot-initiated greeting). Instead, use LLMMessagesAppendFrame(run_llm=True)
            # which appends a user turn message AND immediately fires the LLM.
            try:
                greeting_msg = [
                    {"role": "user", "content": "Hello, please greet me and tell me why you are calling."}
                ]
                await worker.queue_frame(
                    LLMMessagesAppendFrame(messages=greeting_msg, run_llm=True)
                )
                logger.info("[WS] Kickstart LLMMessagesAppendFrame(run_llm=True) queued.")
            except Exception as kick_err:
                logger.error(f"[WS] Failed to queue kickstart frame: {kick_err}")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("[WS] Pipecat client disconnected.")
            await runner.cancel()

        logger.info("[WS] Pipeline built. Starting PipelineWorker via WorkerRunner...")
        await runner.run()
        logger.info("[WS] WorkerRunner finished normally.")

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
