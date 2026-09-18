import os
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from utils.basics import get_text
from fastapi.responses import PlainTextResponse
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from langgraph.types import Command  # CHANGED: resume ke liye chahiye
from apps.graph import make_global, response  # CHANGED: `from graph import workflow` nahi kar sakte — workflow lifespan ke andar make_global() se set hota hai, import-time pe abhi bana hi nahi hota. Module import karke graph.workflow use karna padega.
from repository.helper import send_message
load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await make_global()
    yield

app = FastAPI(lifespan=lifespan)


@app.get("/webhook")
async def verify(request: Request):
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")
    if hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Invalid token", status_code=403)

async def process_and_reply(message: dict, thread_id: str, from_number: str):
    try:
        # LLM aur graph ka heavy kaam yahan background me hoga
        reply_text = await response(message, thread_id, from_number)
        print(reply_text)
        if reply_text:
            await send_message(from_number, reply_text)
    except Exception as e:
        print(f"[background task error]: {e}")

@app.post("/webhook")
async def receive(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages")
        if not messages:
            return {"status": "ok"}

        if len(messages) > 1:
            from_number = messages[0]["from"]
            await send_message(from_number, "Right now we accept only one media file at a time,\n \
                               So other files will be auto ignored and only the first one will be processed.")

        message = messages[0]  # CHANGED: pehle jaisa hi, sirf ab ek warning bhi bhej di agar zaroorat thi
        print(f"Received message: {message}")
        from_number = message["from"]

        # ... baaki code jaisa hai waisa hi

        # Fetch the user details from DB and
        existing_user = await fetch_users(from_number)

        # Check user existence for registration
        if not existing_user:
            await register_users(phone_number= from_number)
            await send_message(from_number, "Welcome to the JomoAI Expense Tracker, You heve been Registered and now You can continue to Record Your Expenses")
            return {"status": "ok"}

        # Send immideate reply of processing if the message is not text or interactive to not to be bored
        if not message['type'] in ['text', 'interactive']:
            await send_message(from_number, "⏳ Reading Your Receipt ...")

        # Process the file in background to immidiate {"status": "ok"} response and 
        # once process is complete send the reply back to the user
        thread_id = existing_user["id"]
        background_tasks.add_task(process_and_reply, message, thread_id, from_number)
        return {"status": "ok"}
    
    except Exception as e:
        print(f"[webhook error]: {e}")
        traceback.print_exc()
    return {"status": "ok"}

from apps.graph import async_pool
import uuid
from typing import Optional
async def register_users(phone_number, email_address: Optional[str] = None):
    id = uuid.uuid4().hex
    async with async_pool.connection() as conn:
        await conn.execute("INSERT INTO users (id, phone_number, email_id) VALUES (%s, %s, %s)", (id, phone_number, email_address))
        await conn.commit()

async def fetch_users(phone_number):
    async with async_pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM users WHERE phone_number = %s", (phone_number,))
        row = await cur.fetchone()
        return row