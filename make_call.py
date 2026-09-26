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
        "TWILIO_TWIML_URL"
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
    twiml_url = os.getenv("TWILIO_TWIML_URL")
    
    # Initialize Twilio client
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        print(f"Error initializing Twilio client: {e}")
        sys.exit(1)
        
    # If target_number contains commas, treat it as a list
    numbers_to_call = [n.strip() for n in target_number.split(',')]
    
    try:
        for number in numbers_to_call:
            if not number: continue
            print(f"Initiating call to {number}...")
            call = client.calls.create(
                to=number,
                from_=from_number,
                url=twiml_url
            )
            print(f"Success! Calling... Call SID: {call.sid}")
            
            if len(numbers_to_call) > 1:
                import time
                print("Waiting 10 seconds before next call...")
                time.sleep(10)
                
    except Exception as e:
        print(f"Failed to place call via Twilio API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    make_call()
