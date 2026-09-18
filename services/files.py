# files.py
#=================================================================
#=======================  Module Imports =========================
import json, asyncio, os
import httpx
import pandas as pd
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from typing import Optional, List
from pydantic import BaseModel, Field
from repository.jomoai import jomoai
from utils.basics import ExpenseDetailsData, file_saver

ALLOWED_UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "app", "uploads"))

# def _is_path_safe(user_path: str) -> bool:
#     if not user_path:
#         return False
#     real_path = os.path.realpath(user_path)
#     allowed_real = os.path.realpath(ALLOWED_UPLOAD_DIR)
#     return real_path == allowed_real or real_path.startswith(allowed_real + os.sep)

#=================================================================
#=======================  File Handler ===========================
async def read_document(file_path: str) -> str:
    """Extract and return all text content from a file (DOCX, or plain text)."""
    # if not _is_path_safe(file_path):
    #     return "[ERROR] Access denied: file_path is outside the allowed uploads directory"
    def _read():
        if file_path.endswith('.docx'):
            from docx import Document
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
    try:
        text = await asyncio.to_thread(_read)
        if len(text) > 8000:
            text = text[:8000] + "\n...[Content truncated due to length]"
        return text
    except Exception as e:
        return f"[ERROR reading file]: {str(e)}"


async def load_pdf_document(pdf_file: str) -> str:
    """ Load a .pdf document from a file path. to extract the text from .pdf file """
    def _load():
        file = PyMuPDF4LLMLoader(file_path=pdf_file)
        doc = file.load()
        return " ".join(x.page_content for x in doc)

    try:
        return await asyncio.to_thread(_load)
    except Exception as e:
        return f"[ERROR loading PDF File, File path is not Correct]: {str(e)}"


async def ipynb_file_reader(file: str):
    """ Read the IPYNB file and convert it to JSON format  """
    # if not _is_path_safe(file):
    #     return "[ERROR] Access denied: file_path is outside the allowed uploads directory"
    def _read():
        with open(file, 'r') as f:
            data = f.read()
        return json.loads(data)
    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        return f"[ERROR reading ipynb file]: {str(e)}"


async def read_excel_file(file: str) -> str:
    """
    Use this tool to read the contents of a local Excel file (.xlsx or .xls) and convert it into a JSON string format.
    Args:
        file (str): The absolute or relative system path to the Excel file.
    Returns:
        str: A JSON string representation of the Excel spreadsheet data, structured by columns or rows.
    """
    # if not _is_path_safe(file):
    #     return "[ERROR] Access denied: file_path is outside the allowed uploads directory"
    try:
        df = await asyncio.to_thread(pd.read_excel, file)
        return df.to_json()
    except Exception as e:
        return f"[ERROR reading excel file]: {str(e)}"


async def read_html_file(file: str) -> str:
    """
    Use this tool to read a local HTML file (.html) containing tables and convert the first table into a JSON string format.
    Args:
        file (str): The absolute or relative system path to the HTML file.
    Returns:
        str: A JSON string representation of the first table found in the HTML file, or "[]" if no tables exist.
    """
    # if not _is_path_safe(file):
    #     return "[ERROR] Access denied: file_path is outside the allowed uploads directory"
    try:
        dfs = await asyncio.to_thread(pd.read_html, file)
        return dfs[0].to_json() if dfs else "[]"
    except Exception as e:
        return f"[ERROR reading html file]: {str(e)}"


async def read_xml_file(file: str) -> str:
    """
    Use this tool to read the contents of a local XML file (.xml) and convert its structured data into a JSON string format.
    Args:
        file (str): The absolute or relative system path to the XML file.
    Returns:
        str: A JSON string representation of the XML data, or "[]" if the file is empty or invalid.
    """
    # if not _is_path_safe(file):
    #     return "[ERROR] Access denied: file_path is outside the allowed uploads directory"
    try:
        df = await asyncio.to_thread(pd.read_xml, file)
        return df.to_json()
    except Exception:
        return "[]"


#=================================================================
#=======================  Expense Extraction ======================
class ExpenseDetails(BaseModel):
    is_expense: bool = Field(..., description="Does this text/data contain expense-related details? True or False")
    expense_details: Optional[List[ExpenseDetailsData]] = Field(None, description="List of individual expense line items found in the text/data. Fill only if is_expense is True, else leave null")


async def read_files(user_id: str, user_query: Optional[str] = None) -> ExpenseDetails:
    """
    Use this tool to analyze extracted document text (PDF/DOCX/Excel/etc.), determine if it contains
    expense-related details, and extract expense fields if it does.
    Args:
        user_query (str, optional): The extracted document text plus any additional query, combined.
    Returns:
        ExpenseDetails: is_expense bool, and expense_details filled only if is_expense is True.
    """
    try:
        parser = PydanticOutputParser(pydantic_object=ExpenseDetails)
        import datetime
        current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        from utils.basics import get_dynamic_taxonomy_prompt
        rules = await get_dynamic_taxonomy_prompt(user_id)
                
        template = PromptTemplate(
            template='First determine if this text/data contains expense-related details (is_expense). \
                    If it does, identify EACH individual expense item separately in expense_details as a list — \
                    do not combine multiple items into one entry. \
                    For each item give out_put as per \n{format_instruction}\nand user_query:\n{query_line}; if not, \
                    leave expense_details null.' \
                    f'just for information today is {current_date_str}'
                    f'{rules}',
            input_variables=['query_line'],
            partial_variables={'format_instruction': parser.get_format_instructions()})

        query_line = f"{user_query}" if user_query else ""

        message = HumanMessage(content=[{"type": "text", "text": template.format(query_line=query_line)}])
        chain = jomoai | parser
        result = await chain.ainvoke([message])
        return result
    except Exception as e:
        return ExpenseDetails(is_expense=False, expense_details=None)


#=================================================================
#=======================  WhatsApp Document Intake =================
async def files_process(message, ACCESS_TOKEN, phone_number):
    file_id = message["document"]["id"]
    filename = message["document"].get("filename", f"file_{file_id}")  # CHANGED: mime_type ki jagah actual filename key, fallback ke saath
    mime_type = message["document"]["mime_type"]  # CHANGED: mime_type ab apne alag variable mein, filename se confuse nahi hoga
    caption_text = message["document"].get("caption", "")
    media_url_endpoint = f"https://graph.facebook.com/v25.0/{file_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url_endpoint, headers=headers)
        media_data = response.json()
        file_download_url = media_data["url"]
        if file_download_url is not None:
            file_response = await client.get(file_download_url, headers=headers)
    if file_response.status_code == 200:
        path = await asyncio.to_thread(file_saver, file_response.content, filename, phone_number)
        return path, caption_text, mime_type  # CHANGED: filename ki jagah mime_type return, process_files ko isi ki zaroorat hai
    return None, caption_text, mime_type

async def process_files(user_id: str, mime_type, files, query):
    text = None
    if mime_type == "application/pdf":
        text = await load_pdf_document(files)
    elif mime_type == "text/plain":
        text = await read_document(files)
    elif mime_type in (
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        text = await read_excel_file(files)
    elif mime_type in (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        text = await read_document(files)
    elif mime_type == "text/html":
        text = await read_html_file(files)
    elif mime_type in ("text/xml", "application/xml"):
        text = await read_xml_file(files)

    if text is None:
        return None

    combined = f"{text}\n{query}" if query else text

    res = await read_files(user_id, combined)
    if res.expense_details:
        return [x.model_dump() for x in res.expense_details]
    return None