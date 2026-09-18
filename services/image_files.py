from repository.jomoai import jomoai
import asyncio, base64, httpx
from io import BytesIO
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from typing import Optional, List 
from utils.basics import file_saver, ExpenseDetailsData
from pydantic import BaseModel, Field
from PIL import Image

class ExpenseDetails(BaseModel):
    is_expense: bool = Field(..., description="Does this image contain expense-related details? True or False")
    expense_details: Optional[List[ExpenseDetailsData]] = Field(None, description="List of individual expense line items found in the image. Fill only if is_expense is True, else leave null")  # CHANGED: single object ki jagah List

async def read_image(user_id:str, image_path: str, user_query: Optional[str] = None) -> ExpenseDetails:
    def _encode():
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    try:
        img_base64 = await asyncio.to_thread(_encode)

        parser = PydanticOutputParser(pydantic_object=ExpenseDetails)
        import datetime
        current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")

        from utils.basics import get_dynamic_taxonomy_prompt
        rules = await get_dynamic_taxonomy_prompt(user_id)
                
        template = PromptTemplate(
            template='First determine if this image contains expense-related details (is_expense). \
                    If it does, identify EACH individual expense item separately in expense_details as a list — \
                    do not combine multiple items into one entry. \
                    For each item give out_put as per \n{format_instruction}\nand user_query:\n{query_line}; if not, \
                    leave expense_details null.'
                    f'just for information today is {current_date_str}'
                    f'{rules}',  # CHANGED: "as a list", "do not combine" explicitly bola
            input_variables=['query_line'],
            partial_variables={'format_instruction': parser.get_format_instructions()})
        
        query_line = f"\nAdditional instruction: {user_query}" if user_query else ""
        
        message = HumanMessage(
            content=[
                {"type": "text", "text": template.format(query_line= query_line)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
                },
            ]
        )
        
        chain = jomoai | parser
        result = await chain.ainvoke([message])
        return result
    except Exception as e:
        raise RuntimeError(f"[ERROR reading image]: {str(e)}") from e

async def image_process(message, ACCESS_TOKEN, phone_number):
    image_id = message["image"]["id"]
    filename = message["image"]["mime_type"].split("/")[-1] 
    caption_text = message["image"].get("caption", "")
    media_url_endpoint = f"https://graph.facebook.com/v25.0/{image_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url_endpoint, headers=headers)
        media_data = response.json()
        image_download_url = media_data["url"]
        if image_download_url is not None:
            img_response = await client.get(image_download_url, headers=headers)
            print(f"Image response yaha hai dekh loo: {img_response}")
    if img_response.status_code == 200:
        path = await asyncio.to_thread(file_saver, img_response.content, filename, phone_number)
        return path, caption_text
    return None, caption_text