# Bowls 'N' Jars: Admin Workflow for AI Calling

Once the dynamic calling and webhook integration features are fully implemented, your system will be completely automated. The Voice Agent will act as a dedicated employee working behind the scenes.

Here is exactly what the day-to-day workflow will look like for you (the Admin) when using the Bowls 'N' Jars website.

---

## 1. The "Customer Calls" Flow (Starting the Campaign)

**Step 1: Open the Dashboard**
You log into the Bowls 'N' Jars admin dashboard and navigate to the **"Customer Calls"** section.

**Step 2: View the Customer List**
You will see a list of customers populated directly from your Neon Database (including the names and phone numbers extracted from your image processing features).

**Step 3: Provide the Context/Message**
You type out the message you want the AI to deliver today. 
*Example:* "We have new 500ml glass jars in stock. Please visit the store."

**Step 4: Press "Start Calls"**
You select the customers you want to contact and click the **Start Calls** button. 

**What happens behind the scenes?**
- Your website backend starts a safe, rate-limited loop (calling 1 customer every few seconds).
- It hands Twilio the specific Name, Phone Number, and your custom message for each customer.
- Twilio dials the phone. When the customer picks up, the Voice Agent greets them personally in Telugu: *"Namaskaram Ravi garu, Bowls 'N' Jars nunchi... we have new 500ml glass jars in stock."*

---

## 2. The "Customer Feedback" Flow (Reviewing the Results)

Because we bypassed n8n and set up a direct Webhook (from Step 9), you don't need to check Google Sheets or external tools to see what happened on the calls. 

**Step 1: The Call Ends**
The moment the customer hangs up the phone, the Voice Agent instantly creates a summary of the conversation and fires it straight back to your Bowls 'N' Jars backend.

**Step 2: Open the Feedback Dashboard**
You click over to the **"Customer Feedback"** (or Call Logs) tab on your website.

**Step 3: Review Day-Wise Reports**
You will see a beautifully organized, day-wise list of every call the agent made. For each row, you will see:
* **Customer Name:** Ravi
* **Phone Number:** +919876543210
* **Time of Call:** 10:30 AM
* **Status:** Answered
* **AI Summary:** "Ravi was very interested in the new stock. He asked about the price of the 500ml jars and said he will visit the store tomorrow evening."

---

### Conclusion
By implementing Claude's dynamic calling plan and our custom Step 9 webhook, you get a completely seamless experience. You press one button to start a personalized marketing campaign, and 30 minutes later, you have written summaries of 50 different phone conversations sitting right in your own website's dashboard!
