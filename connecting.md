# Connecting Your Agent (Step 9 to Production)

This guide covers the final steps from the official PDF manual (Step 9 to the end), adapted specifically for integrating your new Telugu Voice Agent with your **Bowls 'N' Jars** website.

---

## Step 9: Automate & Integrate (The API Bridge)

In the official guide, Step 9 explains how to use a tool called **n8n** to catch a "Webhook" (a data ping) at the end of every call and save the summary to a Google Sheet. 

Since you have a custom Bowls 'N' Jars website, we will use this exact same **Webhook concept** to build the bridge between your Voice Agent and your Website's database!

### How it works:
Instead of sending the call summary to n8n, your Voice Agent will send it directly to your Bowls 'N' Jars Render Backend.

### How to do it:

**1. Create the Webhook Receiver on your Website**
In your Bowls 'N' Jars backend code (not the voice agent), you will create a new API route to receive call logs.
*(Example concept for your website's backend)*:
```javascript
app.post('/api/voice-logs', (req, res) => {
    const { caller_number, summary } = req.body;
    // Save this summary to Neon PostgreSQL so the Admin can see it!
    res.send({ status: "saved" });
});
```

**2. Send data from the Voice Agent**
Just like the PDF shows, you add a few lines of code to the end of `bot.py` inside your Voice Agent to fire off the data when the call hangs up.

First, install the requests library in your voice agent:
```bash
pip install requests
```

Then, add this to `bot.py`:
```python
import requests

def notify_website(caller_number, summary):
    try:
        requests.post(
            "https://your-bowls-n-jars-backend.onrender.com/api/voice-logs",
            json={"caller": caller_number, "summary": summary}
        )
    except Exception as e:
        print("Failed to send log to website:", e)
```
*Call `notify_website(...)` right after the pipeline finishes running in `bot.py`.*

This is your secure API Bridge! The Voice Agent handles the heavy audio processing, and when it finishes, it neatly drops the text summary into your website's database.

---

## Step 10: Full End-to-End Test Checklist

Before going live with your customers, run through this checklist:
- [ ] **Inbound:** Calling your Twilio number connects to the bot within ~1 minute (allow for cold start).
- [ ] The bot's Telugu greeting plays clearly.
- [ ] Speaking Telugu is transcribed correctly (check Render logs to confirm the STT text).
- [ ] The LLM's reply makes sense and stays in Telugu.
- [ ] The reply is spoken back in a natural-sounding Telugu voice.
- [ ] **Outbound:** Running `make_call.py` successfully calls a verified phone number.
- [ ] **Integration (Step 9):** After the call ends, the summary appears in your Bowls 'N' Jars Admin Dashboard database.

---

## Part 4: Free-Tier Limits (Cheat Sheet)
Keep an eye on these limits while testing:
* **Twilio:** You have a small trial credit. You can only call verified numbers until you upgrade.
* **Sarvam AI:** You have free starter credits for STT/TTS. (Pay-as-you-go later).
* **Groq:** High rate limits for free, but if you hit a cap, the bot might pause.
* **Render.com:** Free instances "sleep" after 15 minutes of inactivity. The first call wakes it up (takes 30-50 seconds).

---

## Part 5: Troubleshooting
* **Call connects but there's silence:** Check Render logs. Usually a missing API key or the Sarvam language code isn't `te-IN`.
* **Call drops after a few seconds:** The WebSocket URL in your TwiML Bin is wrong, or you used `ws://` instead of `wss://`.
* **First call takes 30–50 seconds to connect:** Normal on Render's free tier (the server was asleep).
* **Twilio says the number isn't verified:** In trial mode, Twilio can only dial out to numbers you've manually whitelisted in their console.

---

## Part 6: Going From Demo to Production

When you are ready to use this for real Bowls 'N' Jars customers, make these upgrades:
1. **Telecom Compliance:** Swap Twilio for an Indian provider like **Exotel** or **Ozonetel** for outbound Indian numbers (they handle DLT/TRAI compliance).
2. **Remove Cold Starts:** Upgrade the Voice Agent Render service to a paid "always-on" tier so it never sleeps and answers instantly.
3. **Call Recording:** Add a short recorded-call disclosure at the start of the call for compliance.
4. **Human Handoff:** Program the bot to transfer the call to your real phone number if the customer asks to speak to a human manager.
5. **Two-Way Integration:** Upgrade your API bridge so the bot can fetch live inventory from Neon Postgres *during* the call, not just send summaries at the end.
