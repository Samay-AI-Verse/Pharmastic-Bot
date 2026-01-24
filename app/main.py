import os
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

# Load env variables
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = FastAPI()

# ------------------------
# Groq AI Function
# ------------------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def ask_groq(user_msg):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful pharmacy WhatsApp chatbot.",
            },
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.4,
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()  # Raises exception for 4xx/5xx errors
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        print("❌ Groq API Timeout")
        return "Sorry, I'm taking too long to respond. Please try again."
    except requests.exceptions.RequestException as e:
        print(f"❌ Groq API Error: {e}")
        return "Sorry, I'm having trouble processing your request right now. Please try again later."
    except (KeyError, IndexError) as e:
        print(f"❌ Unexpected Groq response format: {e}")
        return "Sorry, something went wrong. Please try again."


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

    response = requests.post(url, headers=headers, json=payload)
    print(response.status_code, response.text)
    return response.status_code == 200


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
        print("⚠️ Received empty or invalid JSON payload (ignoring)")
        return {"status": "ignored"}

    print("\n" + "=" * 50)
    print("📨 INCOMING WEBHOOK DATA:")
    print("=" * 50)
    print(data)
    print("=" * 50 + "\n")

    try:
        # Extract message data
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Check if this is a message event (not a status update)
        if "messages" not in value:
            print("⚠️ No messages in webhook (might be a status update)")
            return {"status": "ok"}

        message = value["messages"][0]
        user_number = message["from"]

        # Check if it's a text message
        if message.get("type") != "text":
            print(f"⚠️ Non-text message type: {message.get('type')}")
            return {"status": "ok"}

        user_text = message["text"]["body"]

        print(f"👤 User: {user_number}")
        print(f"💬 Message: {user_text}")

        # Get AI response
        print("🤖 Asking Groq AI...")
        ai_reply = ask_groq(user_text)
        print(f"🤖 AI Reply: {ai_reply}")

        # Send reply
        print("📤 Sending WhatsApp reply...")
        success = send_whatsapp_message(user_number, ai_reply)

        if success:
            print("✅ Message sent successfully!")
        else:
            print("❌ Failed to send message!")

    except KeyError as e:
        print(f"❌ KeyError - Missing field in webhook data: {e}")
        print(f"Full data structure: {data}")
    except Exception as e:
        print(f"❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

    return {"status": "ok"}


# ------------------------
# Test Endpoint
# ------------------------
@app.get("/test-send")
async def test_send(
    phone: str = "919876543210", message: str = "Test message from bot"
):
    """
    Test endpoint to manually send a message
    Usage: http://localhost:8000/test-send?phone=919876543210&message=Hello
    """
    print(f"\n🧪 TEST ENDPOINT CALLED")
    print(f"📱 Phone: {phone}")
    print(f"💬 Message: {message}\n")

    success = send_whatsapp_message(phone, message)

    return {
        "success": success,
        "phone": phone,
        "message": message,
        "token_configured": bool(WHATSAPP_TOKEN),
        "phone_id_configured": bool(PHONE_NUMBER_ID),
    }


# ------------------------
# Health Check
# ------------------------
@app.get("/")
def root():
    return {"status": "WhatsApp Pharmacy Bot Running"}
