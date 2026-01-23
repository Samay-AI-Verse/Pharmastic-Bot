# Pharmastic Bot - Refactored with LangChain & Structured Data
# ==================== IMPORTS ====================
import os
import random
from typing import Dict, Optional, List, Any
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, APIRouter, Form, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
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
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "pharmastic_db")

    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

    # AI
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")


settings = Settings()

# ==================== DATABASE & MODELS ====================
db_client: AsyncIOMotorClient = None


async def get_db():
    return db_client[settings.DATABASE_NAME]


# 1. Customer Data (Renamed from Patient)
class CustomerProfile(BaseModel):
    phone: str
    name: str = None
    age: int = None
    gender: str = None
    language: str = "english"
    medication_history: Dict[str, Any] = (
        {}
    )  # Tracks medicine usage: { "Dolo": { "count": 2, "last_ordered": date, "dosage": "Once daily" } }
    registered_at: datetime = Field(default_factory=datetime.utcnow)


# 2. Order Data (Matches the table structure in your image)
class Order(BaseModel):
    order_id: str
    customer_id: str
    customer_name: str
    customer_age: int
    customer_gender: str
    items: List[
        Dict[str, Any]
    ]  # List of {medicine, quantity, unit, price, dosage_frequency, prescription_required}
    total_price: float
    status: str = "Pending"  # Pending, Under Review, Confirmed
    review_status: str = "Pending"
    order_date: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    phone: str
    message: str


# ==================== LANGCHAIN AI ENGINE ====================
class AIEngine:
    def __init__(self):
        if settings.GROQ_API_KEY:
            self.llm = ChatGroq(
                temperature=0.1,
                model_name=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
            )
        else:
            self.llm = None
            print("⚠️ Warning: GROQ_API_KEY not found. AI features will be limited.")

    async def translate_response(self, text: str, target_language: str) -> str:
        """Translates bot response to the user's language (Hindi/Hinglish)"""
        if not self.llm or target_language == "english":
            return text

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful translator. Translate the following pharmacy bot message into {language}. Keep the tone professional but friendly. Keep emojis.",
                ),
                ("user", "{text}"),
            ]
        )
        chain = prompt | self.llm
        response = await chain.ainvoke({"language": target_language, "text": text})
        return response.content

    async def extract_order_details(self, text: str) -> dict:
        """Extracts medicine name, quantity, and detects language"""
        if not self.llm:
            return {"medicine": text, "quantity": 1, "language": "english"}

        parser = JsonOutputParser()
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
            You are an AI Pharmacy Assistant. Your job is to understand the user's intent and extract order details if applicable.

            Step 1: Determine the INTENT.
            - If the user is greeting (e.g., "hi", "hello", "hey"), intent is "greeting".
            - If the user is asking strictly about their order status (e.g., "my orders", "status"), intent is "history".
            - If the user mentions a medicine name (e.g., "I want Dolo", "Paracetamol", "Need crocin", "4 strips of aspirin"), intent is "order".
            
            Step 2: If intent is "order", extract:
            - Medicine Name: The name of the medicine. Clean it (remove "I want", "strips", numbers).
            - Quantity: Integer.
            - Unit: String (strips, box, etc).
            - Dosage Frequency: "Once daily" (default) or as specified.
            - Prescription Required: "Yes" (default) or "No".
            
            Step 3: Detect Language (hindi, hinglish, english).

            Return JSON ONLY:
            {{
                "intent": "order" | "greeting" | "history" | "other",
                "medicine": "string" or null,
                "quantity": int or null,
                "unit": "string" or null,
                "dosage_frequency": "string",
                "prescription_required": "string",
                "language": "string"
            }}
            """,
                ),
                ("user", "{text}"),
            ]
        )

        chain = prompt | self.llm | parser
        try:
            return await chain.ainvoke({"text": text})
        except:
            # Fallback: Don't assume text is medicine blindly anymore
            return {
                "intent": "other",
                "medicine": None,
                "quantity": None,
                "unit": None,
                "dosage_frequency": "Once daily",
                "prescription_required": "Yes",
                "language": "english",
            }


ai_engine = AIEngine()


# ==================== BOT LOGIC ====================
class PharmacyBot:

    async def get_state(self, phone: str):
        db = await get_db()
        # We store simple state to know where the user is in the flow
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
        db = await get_db()
        state_doc = await self.get_state(phone)
        step = state_doc.get("step")
        temp_data = state_doc.get("data", {})

        # Check if user exists in our main Customers table
        patient = await db["customers"].find_one({"phone": phone})

        # --- FLOW 1: ONBOARDING (New User) ---

        if not patient and step == "check_user":
            # New User -> Start Registration
            await self.update_state(phone, "awaiting_name")
            return {
                "text": "👋 Welcome to Pharmastic!\n\nI see you are a new customer. Let's set up your profile.\n\n*What is your Name?*",
                "buttons": [],
            }

        if step == "awaiting_name":
            # Save Name -> Ask Gender
            name = message.strip()
            await self.update_state(phone, "awaiting_gender", {"name": name})
            return {
                "text": f"Nice to meet you, {name}! \n\n*Select your Gender:*",
                "buttons": [
                    {"id": "Male", "title": "Male"},
                    {"id": "Female", "title": "Female"},
                    {"id": "Other", "title": "Other"},
                ],
            }

        if step == "awaiting_gender":
            # Save Gender -> Ask Age
            gender = message.strip()  # Will come from button
            prev_name = temp_data.get("name")
            await self.update_state(
                phone, "awaiting_age", {"name": prev_name, "gender": gender}
            )
            return {
                "text": "Got it. \n\n*Please type your Age (e.g., 25):*",
                "buttons": [],
            }

        if step == "awaiting_age":
            # Save Age -> CREATE PROFILE -> Welcome
            try:
                age = int("".join(filter(str.isdigit, message)))
            except:
                return {"text": "Please enter a valid number for age.", "buttons": []}

            # Create Customer in DB
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

            # Reset state to main menu
            await self.update_state(phone, "main_menu")

            return {
                "text": f"✅ Profile Saved!\n\nWelcome {new_customer['name']}.\n\n*Which medicine do you want to order today?* \n(Type the medicine name)",
                "buttons": [],
            }

        # --- FLOW 2: MAIN MENU & ORDERING ---

        # Logic: Extract Medicine -> Calculate -> Confirm -> Save

        if step == "main_menu" or (patient and step == "check_user"):
            # 1. Extract details using LangChain
            extraction = await ai_engine.extract_order_details(message)

            intent = extraction.get("intent", "other")
            medicine = extraction.get("medicine")
            qty = extraction.get("quantity")
            unit = extraction.get("unit")
            detected_lang = extraction.get("language", "english")

            # Update user language preference
            if patient:
                await db["customers"].update_one(
                    {"phone": phone}, {"$set": {"language": detected_lang}}
                )

            # --- HANDLE INTENTS ---
            if intent == "greeting":
                msg = "👋 Hello! \n\nI am *Pharmastic AI*.\nTell me which medicine you need, or check your past orders."
                final_msg = await ai_engine.translate_response(msg, detected_lang)
                return {
                    "text": final_msg,
                    "buttons": [{"id": "my_orders", "title": "My Orders"}],
                }

            if intent == "history":
                pass  # Let it fall through to the 'my order' check at the bottom

            # --- IF MEDICINE DETECTED ---
            if medicine:
                # --- CHECK FOR MISSING QUANTITY ---
                if not qty:
                    # Ask for quantity WITH BUTTONS
                    await self.update_state(
                        phone,
                        "awaiting_quantity",
                        {
                            "medicine": medicine,
                            "lang": detected_lang,
                            "dosage": extraction.get("dosage_frequency"),
                            "presc": extraction.get("prescription_required"),
                        },
                    )

                    base_msg = f"How many *{medicine}* do you want? Select or type."
                    final_msg = await ai_engine.translate_response(
                        base_msg, detected_lang
                    )
                    return {
                        "text": final_msg,
                        "buttons": [
                            {"id": "1 strip", "title": "1 Strip"},
                            {"id": "2 strips", "title": "2 Strips"},
                            {"id": "1 box", "title": "1 Box"},
                        ],
                    }

                # Quantity present -> Process Order
                return await self.process_order_confirmation(
                    phone,
                    medicine,
                    qty,
                    unit,
                    extraction.get("dosage_frequency"),
                    extraction.get("prescription_required"),
                    detected_lang,
                )

        if step == "awaiting_quantity":
            # User provided quantity (hopefully)
            # We can run extraction again to be smart, or just parsing
            prev_data = temp_data
            extraction = await ai_engine.extract_order_details(message)

            # If extraction gives a number, use it. Else try parsing simple digits.
            new_qty = extraction.get("quantity")
            new_unit = extraction.get("unit")

            qty = new_qty if new_qty else 1  # Fallback
            unit = new_unit if new_unit else "units"

            medicine = prev_data.get("medicine")
            detected_lang = prev_data.get("lang", "english")
            dosage = prev_data.get("dosage", "Once daily")
            presc = prev_data.get("presc", "Yes")

            return await self.process_order_confirmation(
                phone, medicine, qty, unit, dosage, presc, detected_lang
            )

        if step == "awaiting_confirmation":
            # Get temp data
            order_data = temp_data
            detected_lang = order_data.get("lang", "english")

            # Improved check: Check if 'confirm' OR 'yes' is anywhere in the message
            msg_lower = message.lower()
            if "confirm" in msg_lower or "yes" in msg_lower or "ok" in msg_lower:
                # --- SAVE TO DATABASE ---
                # --- SAVE TO DATABASE ---
                # Try finding in Customers first (New Flow)
                p_data = await db["customers"].find_one({"phone": phone})

                # Fallback: finding in Patients (Old Flow) - Migration on the fly logic could go here,
                # but for now we just use the data if found.
                if not p_data:
                    p_data = await db["patients"].find_one({"phone": phone})

                # Ultimate Fallback to prevent crash
                if not p_data:
                    p_data = {"name": "Guest", "age": 0, "gender": "Unknown"}

                items_list = [
                    {
                        "medicine": order_data.get("medicine"),
                        "quantity": order_data.get("quantity"),
                        "unit": order_data.get("unit"),
                        "price": order_data.get("unit_price"),
                        "dosage_frequency": order_data.get(
                            "dosage_frequency", "Once daily"
                        ),
                        "prescription_required": order_data.get(
                            "prescription_required", "Yes"
                        ),
                    }
                ]

                new_order = {
                    "order_id": f"ORD-{random.randint(1000, 9999)}",
                    "customer_id": phone,
                    "customer_name": p_data.get("name"),
                    "customer_age": p_data.get("age"),
                    "customer_gender": p_data.get("gender"),
                    "items": items_list,  # Support multiple items structure
                    "total_price": order_data.get("total"),
                    "status": "Confirmed",  # Overall order status
                    "review_status": "Under Review",  # Specific review status
                    "order_date": datetime.utcnow(),
                    # Flattened fields for "spreadsheet" view
                    "product_name": order_data.get("medicine"),
                    "quantity_str": f"{order_data.get('quantity')} {order_data.get('unit', '')}",
                    "dosage_frequency": order_data.get(
                        "dosage_frequency", "Once daily"
                    ),
                    "prescription_required": order_data.get(
                        "prescription_required", "Yes"
                    ),
                }

                # 1. ADD NEW ORDER
                await db["orders"].insert_one(new_order)

                # 2. UPDATE CUSTOMER HISTORY (Track usage for refills)
                try:
                    med_name = order_data.get("medicine")
                    med_name_key = med_name.replace(".", "").replace(
                        "$", ""
                    )  # Sanitize key

                    # Update ONLY if user is in customers table
                    await db["customers"].update_one(
                        {"phone": phone},
                        {
                            "$inc": {f"medication_history.{med_name_key}.count": 1},
                            "$set": {
                                f"medication_history.{med_name_key}.last_ordered": datetime.utcnow(),
                                f"medication_history.{med_name_key}.dosage": order_data.get(
                                    "dosage_frequency"
                                ),
                            },
                        },
                        upsert=False,
                    )
                except Exception as e:
                    print(f"Error updating history (possibly guest user): {e}")

                # Success Message & New Options
                base_msg = f"✅ *Order Confirmed!*\n\nYour order for {order_data['medicine']} is in *Review*. We will notify you later once it is processed.\n\n*Do you want anything more?*"
                final_msg = await ai_engine.translate_response(base_msg, detected_lang)

                await self.update_state(phone, "main_menu")

                return {
                    "text": final_msg,
                    "buttons": [
                        {"id": "new", "title": "Buy Medicine"},
                        {"id": "my_orders", "title": "My Orders"},
                    ],
                }
            else:
                # Cancelled
                base_msg = "🚫 Order Cancelled."
                final_msg = await ai_engine.translate_response(base_msg, detected_lang)
                await self.update_state(phone, "main_menu")
                return {"text": final_msg, "buttons": []}

        # Fallback
        await self.update_state(phone, "main_menu")

        # --- HANDLE 'MY ORDERS' REQUEST ---
        if (
            "my order" in message.lower()
            or "status" in message.lower()
            or "check order" in message.lower()
        ):
            # Fetch last 5 orders
            cursor = (
                db["orders"]
                .find({"customer_id": phone})
                .sort("order_date", -1)
                .limit(5)
            )
            orders = await cursor.to_list(length=5)

            if not orders:
                return {
                    "text": "You have no past orders.",
                    "buttons": [{"id": "new", "title": "Order Medicine"}],
                }

            summary = "*Your Recent Orders:*\n"
            for o in orders:
                # Logic for multiple items if present, else fallback
                item_name = (
                    o.get("product_name")
                    or o.get("medicine_name")
                    or (o.get("items")[0]["medicine"] if o.get("items") else "Unknown")
                )
                status = o.get("review_status", "Pending")
                summary += f"• {item_name}: *{status}*\n"

            return {
                "text": summary,
                "buttons": [{"id": "new", "title": "Order Medicine"}],
            }

        return {
            "text": "How can I help you? Type a medicine name to order.",
            "buttons": [{"id": "my_orders", "title": "My Orders"}],
        }

    async def process_order_confirmation(
        self, phone, medicine, qty, unit, dosage, presc, lang
    ):
        # Helper to generate confirmation
        unit_price = random.randint(50, 500)
        total_price = unit_price * qty
        unit_str = unit if unit else "units"

        order_data = {
            "medicine": medicine,
            "quantity": qty,
            "unit": unit_str,
            "unit_price": unit_price,
            "total": total_price,
            "dosage_frequency": dosage,
            "prescription_required": presc,
            "lang": lang,
        }
        await self.update_state(phone, "awaiting_confirmation", order_data)

        msg_english = f"""📋 *Order Confirmation*
        
Medicine: {medicine}
Quantity: {qty} {unit_str}
Total Amount: ₹{total_price}
Dosage: {dosage}

*Do you want to confirm this order?*"""

        final_msg = await ai_engine.translate_response(msg_english, lang)
        return {
            "text": final_msg,
            "buttons": [
                {"id": "yes", "title": "✅ Confirm Order"},
                {"id": "no", "title": "❌ Cancel"},
            ],
        }


bot = PharmacyBot()

# ==================== API ROUTES ====================
app = FastAPI()
router = APIRouter()

current_dir = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(current_dir, "..", "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

# # Serve static files for UI
# static_path = os.path.join(
#     os.path.dirname(__file__), "..", "static"
# )  # Adjust path if needed
# if not os.path.exists(static_path):
#     os.makedirs(static_path, exist_ok=True)
# app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.on_event("startup")
async def startup_db():
    global db_client
    db_client = AsyncIOMotorClient(settings.MONGODB_URL)
    print("✅ Connected to MongoDB")


@app.on_event("shutdown")
async def shutdown_db():
    db_client.close()


# 1. WhatsApp Webhook (Twilio)
@router.post("/webhook/twilio")
async def twilio_webhook(From: str = Form(...), Body: str = Form(...)):
    phone = From.replace("whatsapp:", "")
    response_data = await bot.process_message(phone, Body)

    # Create Twilio Response
    resp = MessagingResponse()
    msg = resp.message(response_data["text"])

    return Response(content=str(resp), media_type="application/xml")


# 2. Web UI Chat API (For index.html)
@router.post("/api/chat")
async def web_chat(chat: ChatMessage):
    response_data = await bot.process_message(chat.phone, chat.message)
    return JSONResponse(content=response_data)


@app.get("/")
async def serve_ui():
    # 4. Specifically look for index.html inside the static folder
    index_file = os.path.join(static_path, "index.html")

    if os.path.exists(index_file):
        return FileResponse(index_file)

    return {"error": "index.html not found in static folder"}


app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
