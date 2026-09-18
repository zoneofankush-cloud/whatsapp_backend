from repository.jomoai import jomoai
import asyncio, base64, httpx
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from typing import Optional, List
from utils.basics import file_saver, ExpenseDetailsData
from pydantic import BaseModel, Field

class ExpenseDetails(BaseModel):
    is_expense: bool = Field(..., description="Does this audio contain expense-related details? True or False")
    expense_details: Optional[List[ExpenseDetailsData]] = Field(None, description="List of individual expense line items mentioned in the audio. Fill only if is_expense is True, else leave null")

async def read_audio(user_id: str, audio_path: str, mime_type: str, user_query: Optional[str] = None) -> ExpenseDetails:  # CHANGED: mime_type param zaroori hai, kyunki Gemini ko batana padta hai audio ka format
    """
    Use this tool to analyze a local audio file, determine if it mentions expense-related details,
    and extract expense fields if it does.
    Args:
        audio_path (str): The absolute or relative path to the audio file.
        mime_type (str): The audio MIME type (e.g. audio/ogg, audio/mp3, audio/wav).
    Returns:
        ExpenseDetails: is_expense bool, and expense_details filled only if is_expense is True.
    """

    def _encode():
        with open(audio_path, "rb") as f:  # CHANGED: image ki tarah PIL se decode-reencode nahi, audio raw bytes hi bhejna hai
            return base64.b64encode(f.read()).decode("utf-8")

    try:
        audio_b64 = await asyncio.to_thread(_encode)

        parser = PydanticOutputParser(pydantic_object=ExpenseDetails)
        import datetime
        current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")

        from utils.basics import get_dynamic_taxonomy_prompt
        rules = await get_dynamic_taxonomy_prompt(user_id)
        
        template = PromptTemplate(
            template='Listen to this audio and first determine if it mentions expense-related details (is_expense). \
                    If it does, identify EACH individual expense item separately in expense_details as a list — \
                    do not combine multiple items into one entry. \
                    For each item give out_put as per \n{format_instruction}\nand user_query:\n{query_line}; if not, \
                    leave expense_details null.' \
                    f'just for information today is {current_date_str}' \
                    f'{rules}',
            input_variables=['query_line'],
            partial_variables={'format_instruction': parser.get_format_instructions()})

        query_line = f"\nAdditional instruction: {user_query}" if user_query else ""

        message = HumanMessage(
            content=[
                {"type": "text", "text": template.format(query_line=query_line)},
                {
                    "type": "media",  # CHANGED: audio ke liye "media" block, "image_url" nahi
                    "mime_type": mime_type,  # CHANGED
                    "data": audio_b64,  # CHANGED
                },
            ]
        )
        chain = jomoai | parser
        result = await chain.ainvoke([message])
        return result
    except Exception as e:
        raise RuntimeError(f"[ERROR reading audio]: {str(e)}") from e

async def audio_process(message, ACCESS_TOKEN, phone_number):
    audio_id = message["audio"]["id"]
    filename = message["audio"]["mime_type"].split("/")[-1]
    media_url_endpoint = f"https://graph.facebook.com/v25.0/{audio_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url_endpoint, headers=headers)
        media_data = response.json()
        audio_download_url = media_data["url"]
        if audio_download_url is not None:
            audio_response = await client.get(audio_download_url, headers=headers)
    if audio_response.status_code == 200:
        path = await asyncio.to_thread(file_saver, audio_response.content, filename, phone_number)
        return path
    return None