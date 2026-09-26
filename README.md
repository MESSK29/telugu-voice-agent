# Telugu Voice Agent

## Project Purpose
A real-time Telugu voice AI agent providing instant conversation help and responding to queries in Telugu.

## Technology Stack
- **Python**: Core programming language
- **Pipecat**: Voice pipeline management
- **Sarvam AI**: Speech-to-Text (STT) and Text-to-Speech (TTS) for Indian languages (Telugu)
- **Groq**: Fast LLM inference for generating responses
- **FastAPI**: Web framework for the API and WebSocket server
- **WebSocket**: Real-time bidirectional communication
- **Uvicorn**: ASGI web server

## Planned Voice Pipeline
1. Receive user audio via WebSocket.
2. Transcribe Telugu audio to text using Sarvam AI STT.
3. Generate response using Groq LLM.
4. Synthesize Telugu speech from response text using Sarvam AI TTS.
5. Stream audio back to the user via WebSocket.

## Required API Keys
- `SARVAM_API_KEY`: Required for Sarvam AI STT/TTS services.
- `GROQ_API_KEY`: Required for Groq LLM services.

## Basic Installation Instructions
1. Clone the repository.
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
5. Run the application:
   ```bash
   python bot.py
   ```

## Endpoints
- **Health Check (`GET /`)**: Returns `{ "status": "ok", "service": "Telugu Voice Agent" }`.
- **Voice WebSocket (`ws /ws`)**: Connect with a WebSocket client to stream raw audio frames in and out.

## Deployment Basics
- Ensure the production environment provides `SARVAM_API_KEY`, `GROQ_API_KEY`, and sets `PORT`.
- Deploy using a process manager or Docker container running `python bot.py`.
- The application exposes a single Uvicorn ASGI server binding on `0.0.0.0`.

## Outbound Calling
You can use `make_call.py` to trigger an outbound call to a customer's phone using Twilio. The outbound call connects the customer to the *same* existing Telugu AI bot!

**Architecture:**
```text
Python make_call.py
↓
Twilio REST API
↓
Customer phone
↓
Twilio
↓
Existing TwiML Bin
↓
Existing Pipecat Telugu Voice Agent
↓
Sarvam STT
↓
Groq
↓
Sarvam TTS
↓
Customer hears Telugu response
```

### Setup Outbound Calls
1. Create/configure a Twilio account.
2. Get your **Account SID** and **Auth Token**.
3. Get a **Twilio phone number** capable of making calls.
4. Configure your existing TwiML Bin to point to this bot's WebSocket endpoint.
5. Put the TwiML Bin URL in `TWILIO_TWIML_URL` in your `.env` file.
6. Set the destination phone number (`OUTBOUND_TO_NUMBER`) in your `.env` file using E.164 format (e.g. `+919876543210`).

**If you are using a Twilio Trial Account:**
- The destination number may need to be verified in Twilio.
- The caller ID must be the exact Twilio number.
- The destination number must use the correct international format.
- The TwiML URL must be publicly accessible.
- The Twilio credentials must be valid.

### Run the Call
```bash
python make_call.py
```
*Note: A successful run will print something like `Calling... Call SID: CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`*

### Multiple Outbound Numbers (Optional Example)
Later, the same Twilio call function can be used in a loop to call multiple numbers:
```python
from make_call import make_call
import time

numbers = [
    "+919xxxxxxxxx",
    "+919xxxxxxxxx"
]

for number in numbers:
    make_call(number)
    time.sleep(2) # Small delay between calls
```
