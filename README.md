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
