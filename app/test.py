import os
import asyncio
import httpx
from dotenv import load_dotenv

# 1. Load your .env file
load_dotenv()

# 2. CONFIGURATION
# ---------------------------------------------------------
# Replace this with YOUR personal WhatsApp number (Sender)
# Format: Country Code + Number (No spaces, no +)
# Example: "919876543210" for India
TARGET_PHONE_NUMBER = "919764096358" 
# ---------------------------------------------------------

# Load credentials from .env
API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

if not API_TOKEN or not PHONE_ID:
    print("❌ Error: Missing credentials in .env file.")
    exit()

URL = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}

async def send_test_message():
    print(f"🚀 Attempting to send message to: {TARGET_PHONE_NUMBER}")
    
    # We use the "hello_world" template because it is pre-approved 
    # and works immediately for testing.
    payload = {
        "messaging_product": "whatsapp",
        "to": TARGET_PHONE_NUMBER,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(URL, json=payload, headers=HEADERS)
            
            print(f"Status Code: {response.status_code}")
            print("Response Body:", response.json())

            if response.status_code == 200:
                print("\n✅ SUCCESS! Message sent.")
                print("Check your WhatsApp now.")
            else:
                print("\n❌ FAILED.")
                print("Common fixes:")
                print("1. Did you verify the TARGET number in the Meta Dashboard?")
                print("2. Is the Token expired?")
                print("3. Is the Phone ID correct?")
                
        except Exception as e:
            print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(send_test_message())