# Pharmastic Bot - DEBUG VERSION
# ==================== IMPORTS ====================
import os
import random
import json
import httpx
from typing import Dict, Optional, List, Any
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

# LangChain Imports
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================
class Settings:
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "pharmastic_bot")

    # WhatsApp Cloud API Credentials
    WA_API_TOKEN: str = os.getenv("WHATSAPP_API_TOKEN", "")
    WA_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WA_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_secret_token_123")
    
    # AI
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

settings = Settings()

# ==================== DATABASE & MODELS ====================
db_client: AsyncIOMotorClient = None

async def get_db():
    return db_client[settings.DATABASE_NAME]

class ChatMessage(BaseModel):
    phone: str
    message: str

# ==================== UTILS ====================
def clean_phone_number(phone: str) -> str:
    """
    Removes +, spaces, dashes, brackets, and 'whatsapp:' prefix.
    Returns only digits (e.g., '919876543210').
    """
    if not phone:
        return ""
    phone = str(phone).replace("whatsapp:", "")
    clean_num = "".join(filter(str.isdigit, phone))
    return clean_num

# ==================== WHATSAPP CLIENT ====================
class WhatsAppClient:
    def __init__(self):
        self.api_url = f"https://graph.facebook.com/v18.0/{settings.WA_PHONE_NUMBER_ID}/messages"
        self.headers = {
            "Authorization": f"Bearer {settings.WA_API_TOKEN}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to_phone: str, text: str):
        print(f"📤 [DEBUG] Sending reply to {to_phone}...")
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text}
        }
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(self.api_url, json=payload, headers=self.headers)
                print(f"📤 [DEBUG] Meta API Status: {r.status_code}")
                if r.status_code != 200:
                    print(f"❌ [DEBUG] Meta API Error: {r.text}")
            except Exception as e:
                print(f"❌ [DEBUG] Network Error sending message: {e}")

    async def send_interactive_buttons(self, to_phone: str, text: str, buttons: List[dict]):
        print(f"📤 [DEBUG] Sending buttons to {to_phone}...")
        wa_buttons = []
        for btn in buttons[:3]:
            wa_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20]
                }
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {"buttons": wa_buttons}
            }
        }
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(self.api_url, json=payload, headers=self.headers)
                print(f"📤 [DEBUG] Meta API Status: {r.status_code}")
                if r.status_code != 200:
                    print(f"❌ [DEBUG] Meta API Error: {r.text}")
            except Exception as e:
                print(f"❌ [DEBUG] Network Error sending buttons: {e}")

wa_client = WhatsAppClient()

# ==================== LANGCHAIN AI ENGINE ====================
class AIEngine:
    def __init__(self):
        if settings.GROQ_API_KEY:
            try:
                self.llm = ChatGroq(
                    temperature=0.1,
                    model_name=settings.GROQ_MODEL,
                    api_key=settings.GROQ_API_KEY,
                )
                print("✅ [DEBUG] AI Engine Initialized")
            except Exception as e:
                print(f"❌ [DEBUG] AI Init Failed: {e}")
                self.llm = None
        else:
            self.llm = None
            print("⚠️ [DEBUG] No GROQ_API_KEY found")

    async def translate_response(self, text: str, target_language: str) -> str:
        if not self.llm or target_language == "english":
            return text
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Translate to {language}. Professional but friendly. Keep emojis."),
                ("user", "{text}"),
            ])
            chain = prompt | self.llm
            response = await chain.ainvoke({"language": target_language, "text": text})
            return response.content
        except Exception as e:
            print(f"❌ [DEBUG] AI Translation Error: {e}")
            return text

    async def extract_order_details(self, text: str) -> dict:
        if not self.llm:
            return {"medicine": text, "quantity": 1, "language": "english"}
        
        try:
            parser = JsonOutputParser()
            prompt = ChatPromptTemplate.from_messages([
                ("system", """
                Extract order details. Return JSON ONLY:
                {{
                    "intent": "order" | "greeting" | "history" | "other",
                    "medicine": "string" or null,
                    "quantity": int or null,
                    "unit": "string" or null,
                    "dosage_frequency": "string",
                    "prescription_required": "string",
                    "language": "string"
                }}
                """),
                ("user", "{text}"),
            ])
            chain = prompt | self.llm | parser
            return await chain.ainvoke({"text": text})
        except Exception as e:
            print(f"❌ [DEBUG] AI Extraction Error: {e}")
            # Fallback
            return {"intent": "other", "medicine": None}

ai_engine = AIEngine()

# ==================== BOT LOGIC ====================
class PharmacyBot:
    async def get_state(self, phone: str):
        db = await get_db()
        state = await db["session_state"].find_one({"phone": phone})
        if not state:
            return {"step": "check_user", "data": {}}
        return state

    async def update_state(self, phone: str, step: str, data: dict = None):
        db = await get_db()
        update_data = {"step": step}
        if data:
            update_data["data"] = data
        await db["session_state"].update_one(
            {"phone": phone}, {"$set": update_data}, upsert=True
        )

    async def process_message(self, phone: str, message: str) -> dict:
        print(f"🤖 [DEBUG] Processing message from {phone}: '{message}'")
        
        db = await get_db()
        state_doc = await self.get_state(phone)
        step = state_doc.get("step")
        temp_data = state_doc.get("data", {})
        
        print(f"📍 [DEBUG] Current Step: {step}")

        # Check customer profile
        patient = await db["customers"].find_one({"phone": phone})
        
        if patient:
            print(f"👤 [DEBUG] Found existing patient: {patient.get('name')}")
        else:
            print("👤 [DEBUG] No patient found (New User)")

        # --- FLOW 1: ONBOARDING ---
        if not patient and step == "check_user":
            await self.update_state(phone, "awaiting_name")
            return {
                "text": "👋 Welcome to Pharmastic!\n\nI see you are a new customer. Let's set up your profile.\n\n*What is your Name?*",
                "buttons": []
            }

        if step == "awaiting_name":
            name = message.strip()
            await self.update_state(phone, "awaiting_gender", {"name": name})
            return {
                "text": f"Nice to meet you, {name}! \n\nSelect your Gender:",
                "buttons": [
                    {"id": "Male", "title": "Male"},
                    {"id": "Female", "title": "Female"},
                    {"id": "Other", "title": "Other"}
                ]
            }

        if step == "awaiting_gender":
            gender = message.strip()
            prev_name = temp_data.get("name")
            await self.update_state(phone, "awaiting_age", {"name": prev_name, "gender": gender})
            return {
                "text": "Got it. \n\n*Please type your Age (e.g., 25):*",
                "buttons": []
            }

        if step == "awaiting_age":
            try:
                age = int("".join(filter(str.isdigit, message)))
            except:
                return {"text": "Please enter a valid number for age.", "buttons": []}

            new_customer = {
                "phone": phone,
                "name": temp_data.get("name"),
                "gender": temp_data.get("gender"),
                "age": age,
                "language": "english",
                "medication_history": {},
                "registered_at": datetime.utcnow(),
            }
            await db["customers"].insert_one(new_customer)
            await self.update_state(phone, "main_menu")
            return {
                "text": f"✅ Profile Saved!\n\nWelcome {new_customer['name']}.\n\n*Which medicine do you want to order today?*",
                "buttons": []
            }

        # --- FLOW 2: MAIN MENU & ORDERING ---
        if step == "main_menu" or (patient and step == "check_user"):
            print("🧠 [DEBUG] Asking AI to understand intent...")
            extraction = await ai_engine.extract_order_details(message)
            print(f"🧠 [DEBUG] AI Result: {extraction}")

            intent = extraction.get("intent", "other")
            medicine = extraction.get("medicine")
            qty = extraction.get("quantity")
            detected_lang = extraction.get("language", "english")

            if intent == "greeting":
                msg = "👋 Hello! I am *Pharmastic AI*.\nTell me which medicine you need."
                final_msg = await ai_engine.translate_response(msg, detected_lang)
                return {
                    "text": final_msg,
                    "buttons": [{"id": "my_orders", "title": "My Orders"}]
                }

            if medicine:
                if not qty:
                    await self.update_state(
                        phone, "awaiting_quantity",
                        {"medicine": medicine, "lang": detected_lang, "dosage": extraction.get("dosage_frequency")}
                    )
                    base_msg = f"How many *{medicine}* do you want?"
                    final_msg = await ai_engine.translate_response(base_msg, detected_lang)
                    return {
                        "text": final_msg,
                        "buttons": [
                            {"id": "1 strip", "title": "1 Strip"},
                            {"id": "2 strips", "title": "2 Strips"},
                            {"id": "1 box", "title": "1 Box"}
                        ]
                    }
                return await self.process_order_confirmation(
                    phone, medicine, qty, extraction.get("unit"), 
                    extraction.get("dosage_frequency"), "Yes", detected_lang
                )

        if step == "awaiting_quantity":
            qty_text = message.lower()
            qty = 1
            if "2" in qty_text: qty = 2
            
            prev_data = temp_data
            return await self.process_order_confirmation(
                phone, prev_data.get("medicine"), qty, "strip", 
                prev_data.get("dosage"), "Yes", prev_data.get("lang")
            )

        if step == "awaiting_confirmation":
            detected_lang = temp_data.get("lang", "english")
            if "yes" in message.lower() or "confirm" in message.lower():
                new_order = {
                    "order_id": f"ORD-{random.randint(1000, 9999)}",
                    "customer_id": phone,
                    "items": [{"medicine": temp_data.get("medicine")}],
                    "total_price": temp_data.get("total"),
                    "status": "Confirmed",
                    "order_date": datetime.utcnow()
                }
                await db["orders"].insert_one(new_order)
                
                await self.update_state(phone, "main_menu")
                msg = "✅ Order Confirmed! We will notify you shortly."
                final = await ai_engine.translate_response(msg, detected_lang)
                return {
                    "text": final, 
                    "buttons": [{"id": "new", "title": "Buy Medicine"}]
                }
            else:
                await self.update_state(phone, "main_menu")
                return {"text": "🚫 Order Cancelled.", "buttons": []}

        # FALLBACK IF NOTHING MATCHES
        print("⚠️ [DEBUG] No intent matched. Returning Fallback.")
        return {
            "text": "I didn't understand. Please type the medicine name.",
            "buttons": [{"id": "my_orders", "title": "My Orders"}]
        }

    async def process_order_confirmation(self, phone, medicine, qty, unit, dosage, presc, lang):
        unit_price = random.randint(50, 500)
        total_price = unit_price * qty
        order_data = {
            "medicine": medicine, "quantity": qty, "unit": unit,
            "total": total_price, "lang": lang
        }
        await self.update_state(phone, "awaiting_confirmation", order_data)
        
        msg = f"📋 *Order Confirmation*\nMedicine: {medicine}\nQty: {qty} {unit}\nTotal: ₹{total_price}\n\nConfirm?"
        final = await ai_engine.translate_response(msg, lang)
        return {
            "text": final,
            "buttons": [
                {"id": "yes", "title": "✅ Confirm"},
                {"id": "no", "title": "❌ Cancel"}
            ]
        }

bot = PharmacyBot()

# ==================== API ROUTES ====================
app = FastAPI()
router = APIRouter()

current_dir = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(current_dir, "..", "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.on_event("startup")
async def startup_db():
    global db_client
    db_client = AsyncIOMotorClient(settings.MONGODB_URL)
    print("✅ [DEBUG] Connected to MongoDB")

@app.on_event("shutdown")
async def shutdown_db():
    if db_client:
        db_client.close()

@router.get("/webhook/whatsapp")
async def verify_whatsapp(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge")
):
    if mode == "subscribe" and token == settings.WA_VERIFY_TOKEN:
        print("✅ [DEBUG] Webhook Verification SUCCESS")
        return int(challenge)
    print("❌ [DEBUG] Webhook Verification FAILED")
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        body = await request.body()
        if not body:
            return {"status": "ignored"}
        
        data = await request.json()
        
        # 1. Print Raw Data to Debug
        # print(f"📥 [DEBUG] Raw Incoming Data: {json.dumps(data)}") 

        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" not in value:
            return {"status": "ignored"} 

        message_data = value["messages"][0]
        raw_phone = message_data["from"]
        
        # Clean Phone
        phone = clean_phone_number(raw_phone)
        print(f"📞 [DEBUG] Received from Phone: {phone} (Raw: {raw_phone})")

        msg_type = message_data["type"]
        user_message = ""
        
        if msg_type == "text":
            user_message = message_data["text"]["body"]
        elif msg_type == "interactive":
            if message_data["interactive"]["type"] == "button_reply":
                user_message = message_data["interactive"]["button_reply"]["title"]

        print(f"💬 [DEBUG] User Message: {user_message}")

        # 2. Process Logic
        response_data = await bot.process_message(phone, user_message)
        print(f"📤 [DEBUG] Bot Response Text: {response_data['text']}")

        # 3. Send Reply
        if response_data.get("buttons"):
            await wa_client.send_interactive_buttons(
                phone, response_data["text"], response_data["buttons"]
            )
        else:
            await wa_client.send_text(phone, response_data["text"])

        return {"status": "processed"}

    except Exception as e:
        print(f"❌ [DEBUG] CRITICAL ERROR in Webhook: {e}")
        return {"status": "error"}

@router.post("/api/chat")
async def web_chat(chat: ChatMessage):
    clean_phone = clean_phone_number(chat.phone)
    response_data = await bot.process_message(clean_phone, chat.message)
    return JSONResponse(content=response_data)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)