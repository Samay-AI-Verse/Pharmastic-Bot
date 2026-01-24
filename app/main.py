import os
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import google.generativeai as genai

# Load env variables
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-pro")
else:
    print("⚠️ GEMINI_API_KEY is missing!")
    model = None

app = FastAPI()


# ------------------------
# Gemini AI Function
# ------------------------
def ask_gemini(user_msg):
    if not model:
        return "System Error: AI model is not configured."

    try:
        # Create a prompt for the pharmacy bot
        prompt = f"""You are a helpful pharmacy WhatsApp chatbot. 
        Keep your answers concise and helpful.
        User says: {user_msg}"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return "Sorry, I'm having trouble processing your request right now. Please try again later."


# ------------------------
# WhatsApp Send Function
# ------------------------
def send_whatsapp_message(to, text, message_id=None):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    if message_id:
        payload["context"] = {"message_id": message_id}

    print(f"📤 Sending to {to}: {text[:50]}...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status: {response.status_code}, Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Send Error: {e}")
        return False


# ------------------------
# Webhook Verify
# ------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"


# ------------------------
# Receive Messages
# ------------------------
@app.post("/webhook")
async def receive_message(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "ignored"}

    print("\n" + "=" * 50)
    print("📨 INCOMING WEBHOOK DATA")
    print("=" * 50)

    try:
        # Extract message data
        if "entry" not in data:
            return {"status": "ok"}

        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        user_number = message["from"]
        message_id = message["id"]

        if message.get("type") != "text":
            return {"status": "ok"}

        user_text = message["text"]["body"]
        print(f"👤 User: {user_number} says: {user_text}")

        # Get AI response
        ai_reply = ask_gemini(user_text)
        print(f"🤖 AI Reply: {ai_reply}")

        # Send reply
        send_whatsapp_message(user_number, ai_reply, message_id)

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        import traceback

        traceback.print_exc()

    return {"status": "ok"}


# ------------------------
# Test Endpoint
# ------------------------
@app.get("/test-send")
async def test_send(
    phone: str = "919876543210", message: str = "Test message from Gemini Bot"
):
    success = send_whatsapp_message(phone, message)
    return {"success": success, "phone": phone, "message": message}


# ------------------------
# Health Check
# ------------------------
@app.get("/")
def root():
    return {"status": "WhatsApp Pharmacy Bot (Gemini) Running"}
