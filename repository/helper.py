#======================================================================================
#=============================== HELPER FUNCTIONS =====================================
import json, os, httpx
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
# CHANGED: reply_to_user() poora hata diya — image/audio/document/text extraction ab graph.py ke nodes handle karte hain.
# CHANGED: get_text() bhi hata diya, jo yahan use hi nahi ho raha tha (basics.py mein already canonical version hai).
# CHANGED: image/audio/files/jomoai imports hataye — ye ab yahan use nahi hote.

async def send_message(to, text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": str(text)},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)

    with open("messages.json", "a") as f:
        json.dump(f"{to}:{text}", f)
    return r.json()


async def send_interactive_buttons(recipient_number):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "*How can i help you today?*\n\nChose an Option from below:"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "btn_record_expense", "title": "Record Expense"}},
                    {"type": "reply", "reply": {"id": "btn_fetch_expenses", "title": "Fetch Expenses"}},
                    {"type": "reply", "reply": {"id": "btn_talk_agent", "title": "Talk to Agent"}}
                ]
            }
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)

    with open("messages.json", "a") as f:
        json.dump(f"{recipient_number}:{payload}", f)
    return r.json()

async def send_confirm_buttons(recipient_number, body_text):  # CHANGED: naya function, save/discard ke liye
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "btn_save_expense", "title": "Save"}},
                    {"type": "reply", "reply": {"id": "btn_discard_expense", "title": "Discard"}}
                ]
            }
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
    return r.json()