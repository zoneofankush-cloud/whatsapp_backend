import os
import httpx
import json
from dotenv import load_dotenv
from services.meta.payloads import build_document_payload, build_interactive_payload

load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
BASE_URL = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}"

# ===========================================================
# ================== 1. Text Message ========================
async def send_message(to: str, text: str):
    url = f"{BASE_URL}/messages"
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


    return r.json()

# =================================================================
# ===== 2. Interactive Message (Auto-switches Button/List) ========
async def send_interactive_message(recipient_number: str, body_text: str, options: list, menu_title: str = "Select Option"):
    payload = build_interactive_payload(recipient_number, body_text, options, menu_title)
    url = f"{BASE_URL}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
    return r.json()

# ====================================================================
# =========== 3. Document Sender (Single or Multiple) ================
async def send_document(recipient_number: str, documents: dict | list):
    """
    'documents' me single dict bhej, ya dicts ki list bhej:
    [{"media_id": "123", "filename": "a.pdf", "caption": "cap"}, ...]
    """
    if isinstance(documents, dict):
        documents = [documents]
        
    url = f"{BASE_URL}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    results = []
    async with httpx.AsyncClient() as client:
        for doc in documents:
            payload = build_document_payload(recipient_number, doc["media_id"], doc["filename"], doc.get("caption", ""))
            r = await client.post(url, headers=headers, json=payload)
            results.append(r.json())
            
    return results[0] if len(results) == 1 else results

# ===============================================================
# ========== 4. Media Upload (Single or Multiple) ===============
async def upload_document(files: str | list, mime_type: str = "application/pdf"):
    """
    'files' me single path (str) bhej ya list of paths bhej.
    """
    if isinstance(files, str):
        files = [files]
        
    url = f"{BASE_URL}/media"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"messaging_product": "whatsapp"}
    
    results = []
    async with httpx.AsyncClient() as client:
        for file_path in files:
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                upload_files = {"file": (filename, f, mime_type)}
                response = await client.post(url, headers=headers, data=data, files=upload_files)
                
                if response.status_code == 200:
                    results.append(response.json().get("id"))
                else:
                    print(f"[META UPLOAD ERROR]: {response.status_code} - {response.text}")
                    results.append(None)
    return results[0] if len(results) == 1 else results
