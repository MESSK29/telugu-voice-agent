from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
import uvicorn
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
import os

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

app = FastAPI(title="Telugu Voice Agent")

@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "service": "Telugu Voice Agent"
    }

class DebugProcessor(FrameProcessor):
    async def process_frame(self, frame, direction):
        if isinstance(frame, TranscriptionFrame):
            print(f"\\n[USER] ({frame.language}): {frame.text}")
        elif isinstance(frame, TextFrame):
            print(frame.text, end="", flush=True)
        elif type(frame).__name__ == "LLMFullResponseEndFrame":
            print("\\n[AGENT DONE]")
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
    await websocket.accept()

    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    if not sarvam_api_key or not groq_api_key:
        print("ERROR: API keys are not fully set in environment.")
        await websocket.close(code=1011)
        return

    try:
        # Wait for Twilio's "start" event to get the actual stream_sid
        stream_sid = ""
        call_sid = ""
        import json
        
        # Twilio typically sends 'connected' then 'start'
        for _ in range(2):
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("event") == "start":
                stream_sid = data["start"]["streamSid"]
                call_sid = data["start"]["callSid"]
                break

        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                add_wav_header=False,
                serializer=TwilioFrameSerializer(stream_sid=stream_sid, call_sid=call_sid),
            )
        )

        stt = SarvamSTTService(
            api_key=sarvam_api_key,
            language="te-IN"
        )

        tts = SarvamTTSService(
            api_key=sarvam_api_key,
            settings=SarvamTTSService.Settings(voice="priya") # "meera" is not found in enum, falling back to priya
        )

        llm = GroqLLMService(
            api_key=groq_api_key,
            settings=GroqLLMService.Settings(model="llama-3.1-8b-instant")
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

        context = LLMContext(
            messages=[
                {"role": "system", "content": system_prompt}
            ]
        )
        context_aggregators = LLMContextAggregatorPair(context=context)

        debug_processor = DebugProcessor()

        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregators.user(),
            llm,
            debug_processor,
            tts,
            context_aggregators.assistant(),
            transport.output()
        ])

        worker = PipelineWorker(pipeline, params=PipelineParams(allow_interruptions=True))
        
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            print("Client connected!")
            # Kickstart the conversation by pretending the user said "Hello" so the agent speaks first
            await worker.task.queue.put(TranscriptionFrame(text="Hello", user_id="user", timestamp="0"))

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            print("Client disconnected!")
            await worker.cancel()

        await worker.run()

        # Call ended, send the data to Google Sheets via Webhook/n8n
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            print("Sending call log to webhook...")
            
            # Extract conversation context
            conversation = []
            for msg in context.messages:
                if msg.get("role") in ["user", "assistant"]:
                    conversation.append(f"{msg['role'].upper()}: {msg.get('content')}")
            
            summary = "\n".join(conversation)
            
            payload = {
                "timestamp": datetime.now().isoformat(),
                "caller_number": phone or "Unknown", 
                "summary": summary
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload) as response:
                        print(f"Webhook response status: {response.status}")
            except Exception as e:
                print(f"Failed to send webhook: {e}")

    except Exception as e:
        print(f"Runtime error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
