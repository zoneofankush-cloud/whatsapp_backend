import httpx
import os

async def upload_pdf_to_meta(pdf_path: str, access_token: str, phone_number_id: str):
    """
    Local PDF file ko Meta ke server par upload karega aur media_id return karega.
    """
    url = f"https://graph.facebook.com/v25.0/{phone_number_id}/media"
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    data = {
        "messaging_product": "whatsapp"
    }
    
    filename = os.path.basename(pdf_path)
    
    async with httpx.AsyncClient() as client:
        with open(pdf_path, "rb") as f:
            files = {
                "file": (filename, f, "application/pdf")
            }
            
            response = await client.post(url, headers=headers, data=data, files=files)
            
            if response.status_code == 200:
                result = response.json()
                media_id = result.get("id")
                print(f"[SUCCESS] PDF Uploaded to Meta. Media ID: {media_id}")
                return media_id
            else:
                print(f"[ERROR] Meta Upload Failed: {response.status_code} - {response.text}")
                return None
