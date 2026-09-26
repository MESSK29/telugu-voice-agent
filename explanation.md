# Telugu Voice AI Agent - Simple Explanation

Here is a simple, step-by-step explanation of what we built across the 5 parts of this project.

## Overview
We built a **real-time AI voice assistant** that can talk to people over a phone call or web interface in the **Telugu** language. It listens to what the user says, thinks of an answer, and speaks it out loud instantly.

---

### Part 1: Setting up the Foundation (The Skeleton)
We started by creating the basic structure of our project. 
- We set up a web server using a tool called **FastAPI**. 
- We installed a library called **Pipecat**, which is designed specifically for building fast, real-time voice applications. 
- We created the folders and files we would need, like our main `bot.py` script and a list of dependencies (`requirements.txt`).

### Part 2: Listening (The Ears)
We needed the bot to understand when a human speaks Telugu.
- We used a service called **Sarvam AI**, which is very good at understanding Indian languages.
- We added the **Speech-to-Text (STT)** part into our pipeline. 
- When a user connects and talks, the bot takes their voice audio and converts it into readable Telugu text.

### Part 3: Thinking (The Brain)
Once the bot knows what the user said (in text), it needs to figure out how to reply.
- We used **Groq**, a super-fast AI brain (specifically the `llama-3.1-8b-instant` model).
- We gave the bot a "System Prompt" (a set of rules). We told it: *"You are a helpful voice agent. Speak in Telugu, keep your answers short and natural."*
- We added memory to the bot, so it remembers the conversation history while talking.

### Part 4: Speaking (The Mouth)
After the Groq brain generates a text reply in Telugu, the bot needs to speak it out loud.
- We went back to **Sarvam AI** and used their **Text-to-Speech (TTS)** service.
- We chose a voice (named "priya") for the bot.
- Now, as soon as the Groq brain writes the Telugu response, Sarvam instantly turns that text into human-sounding audio and sends it back to the caller.

### Part 5: Finishing and Sharing (The Cleanup)
Finally, we made sure the project was clean, secure, and ready to be used by others.
- We removed all the messy temporary files we created during testing.
- We made sure our secret "API Keys" (passwords for Groq and Sarvam) were hidden and safe so hackers couldn't steal them.
- We securely uploaded the final, clean code to your **GitHub repository** (`MESSK29/telugu-voice-agent`).

---

## How it flows in real-time:
1. **User Speaks:** "Hello, naaku oka doubt undi." (Audio comes in).
2. **Sarvam STT:** Converts the audio into Telugu text.
3. **Groq LLM:** Reads the text and writes a quick, helpful reply in Telugu.
4. **Sarvam TTS:** Converts the AI's written reply into actual voice audio.
5. **User Hears:** The bot speaking back naturally!
