import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

def make_call(to_number: str = None):
    # Load environment variables
    load_dotenv()
    
    # Check for required environment variables
    required_vars = [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "OUTBOUND_TO_NUMBER",
        "BASE_URL"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variable(s): {', '.join(missing_vars)}")
        sys.exit(1)
        
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    
    # Use the passed argument if available, else fallback to the .env var
    target_number = to_number or os.getenv("OUTBOUND_TO_NUMBER")
    base_url = os.getenv("BASE_URL").rstrip('/')
    
    # Example simulated DB context for multiple calls
    customers = []
    numbers_to_call = [n.strip() for n in target_number.split(',')]
    for num in numbers_to_call:
        if num:
            customers.append({"phone": num, "name": "Customer", "details": "Wants to know about new stock"})
    
    # Initialize Twilio client
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        print(f"Error initializing Twilio client: {e}")
        sys.exit(1)
        
    try:
        for c in customers:
            print(f"Initiating call to {c['name']} ({c['phone']})...")
            
            # Twilio will hit this route to get the custom TwiML
            import urllib.parse
            call_url = f"{base_url}/voice?name={urllib.parse.quote(c['name'])}&details={urllib.parse.quote(c['details'])}&phone={urllib.parse.quote(c['phone'])}"
            
            call = client.calls.create(
                to=c['phone'],
                from_=from_number,
                url=call_url
            )
            print(f"Success! Calling... Call SID: {call.sid}")
            
            if len(customers) > 1:
                import time
                print("Waiting 10 seconds before next call...")
                time.sleep(10)
                
    except Exception as e:
        print(f"Failed to place call via Twilio API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    make_call()
