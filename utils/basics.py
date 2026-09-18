from pydantic import BaseModel, Field
from typing import Optional
import uuid, os

def file_saver(file, filename, phone_number):
    prefix = uuid.uuid4().hex
    unique_filename = f"{prefix}.{filename}"
    user_upload_dir = os.path.join("app", "uploads", f"{phone_number}")
    os.makedirs(user_upload_dir, exist_ok=True)
    new_file_path = os.path.join(user_upload_dir, unique_filename)
    with open(new_file_path, "wb") as f:
        f.write(file)
    return new_file_path

def get_text(content):
    if isinstance(content, list):
        return "".join(x.get("text", "") for x in content if isinstance(x, dict))
    else:
        return content

def format_expense_summary(expense_list: list) -> str:
    if not expense_list:
        return "I couldn't detect any expense details in your message. If you'd like to log an expense, please type the details, or click 'Discard' to cancel."
        
    formatted_text = "Please confirm the following *Extracted Expense* details:\n\n"
    
    for i, exp in enumerate(expense_list, 1):
        if len(expense_list) > 1:
            formatted_text += f"*Item {i}:*\n"
            
        formatted_text += f"• *Type:* {exp.get('type', 'N/A')}\n"
        formatted_text += f"• *Amount:* {exp.get('amount', 'N/A')}\n"
        formatted_text += f"• *Amount In Words:* {exp.get('amount_in_words', 'N/A')}\n"
        formatted_text += f"• *Date:* {exp.get('date', 'N/A')}\n"
        formatted_text += f"• *Description:* {exp.get('description', 'N/A')}\n"
        formatted_text += f"• *Currency:* {exp.get('currency', 'N/A')}\n"
        formatted_text += f"• *Payment Mode:* {exp.get('payment_mode', 'N/A')}\n\n"
        
    formatted_text += "*Click:*\n*Save:* To record\n*Discard:* To cancel\n\n*Or,* simply reply with any changes you want to make."
    return formatted_text

class ExpenseDetailsData(BaseModel):
    type: str = Field(..., description="What type of Expenditure is it?")
    amount: str = Field(..., description="The Amount of Expenditure is?")
    amount_in_words: str = Field(..., description="The Amount of Expenditure in Words is?", )
    date: str = Field(..., description="The exact Date of Expenditure. MUST be in strict YYYY-MM-DD format (e.g. 2026-09-14). Calculate exact date from context if words like yesterday/tomorrow are used.", pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: str = Field(..., description="The Description of Expenditure is?")
    currency: Optional[str] = Field("INR", description="Currency of the amount — infer from context/symbols (₹, $, etc.) if mentioned, else default INR")  # CHANGED
    payment_mode: Optional[str] = Field(None, description="How the payment was made — cash, UPI, credit card, debit card. Infer from receipt/context if mentioned, else null")  # CHANGED

import os
import uuid
from datetime import datetime
from fpdf import FPDF

def create_expense_pdf(expense_list: list, phone_number: str) -> str:
    """
    Kharche ki list leta hai aur ek saaf PDF banakar path return karta hai.
    """
    # Folder banao agar nahi hai
    output_dir = os.path.join("app", "uploads", str(phone_number))
    os.makedirs(output_dir, exist_ok=True)
    
    # Unique file name
    filename = f"Expense_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    pdf = FPDF()
    pdf.add_page()
    
    # Title (Arial ki jagah Helvetica)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(200, 10, text="Extracted Expense Report", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    
    total_amount = 0.0
    
    # Loop for each expense item
    for i, exp in enumerate(expense_list, 1):
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 8, text=f"Item {i}:", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("Helvetica", size=11)
        pdf.cell(0, 6, text=f"Type: {exp.get('type', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        
        # Calculate Total Amount
        amount_str = str(exp.get('amount', '0')).replace(',', '').strip()
        try:
            total_amount += float(amount_str)
        except ValueError:
            pass
            
        pdf.cell(0, 6, text=f"Amount: {exp.get('currency', 'INR')} {exp.get('amount', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, text=f"Amount in Words: {exp.get('amount_in_words', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, text=f"Date: {exp.get('date', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, text=f"Description: {exp.get('description', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, text=f"Payment Mode: {exp.get('payment_mode', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5) # Space between items
        
    # Print Total
    pdf.ln(5)
    pdf.set_font("Helvetica", 'B', 14)
    pdf.cell(0, 10, text=f"Total Detected Amount: {total_amount}", new_x="LMARGIN", new_y="NEXT")
    
    # Save PDF
    pdf.output(filepath)
    return filepath
class IntentCheck(BaseModel):
    is_valid: bool = Field(description="True if It is related to Expense and related user's Query else False")

async def DecissionNode(query: str, model, history: str):
    structured_model = model.with_structured_output(IntentCheck)
    prompt = f""" 
    You are Expense Tracker expert to judge and answer the following:\n
    you are being provided following History of chat and user's new query
    User Question:  {query}\n
    Chat History:   {history}\n
    Judge how to answer this:
    - True:   If user's query and History are closely related to Expense mark it as True\n
    - False: if you really think the question do not realteted to Expense mark it as False
    """
    decision = (await structured_model.ainvoke(prompt)).is_valid 
    return decision

from fastapi import HTTPException

async def fetch_user_expense_details(user_id) -> dict:
    from apps.graph import async_pool
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""
                SELECT 
                    array_agg(DISTINCT currency) as currency_types,
                    array_agg(DISTINCT source) as source_types,
                    array_agg(DISTINCT type) as type_list,
                    array_agg(DISTINCT payment_mode) as payment_types
                FROM expenses 
                WHERE user_id = %s
            """, (user_id,))
            
            row = await cur.fetchone()
            
            if not row:
                return {}
                
            alls = {
                'currency_types': [c for c in row['currency_types'] if c] if row['currency_types'] else [], 
                'source_type': [s for s in row['source_types'] if s] if row['source_types'] else [], 
                'type_list': [t for t in row['type_list'] if t] if row['type_list'] else [],
                'payment_type': [p for p in row['payment_types'] if p] if row['payment_types'] else []
            }
            return alls
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")

async def get_dynamic_taxonomy_prompt(user_id: str) -> str:
    """Fetches user categories and returns a formatted prompt constraint string."""
    user_categories = await fetch_user_expense_details(user_id)
    
    if not user_categories:
        return "" # Agar user ka naya account hai aur DB khali hai, toh prompt me kuch add mat karo
        
    taxonomy_prompt = f"""
        IMPORTANT RULE: 
        When categorizing a new expense, STRICTLY try to reuse the user's existing categories before inventing new ones:
        - Existing Types: {user_categories.get('type_list', [])}
        - Existing Payment Modes: {user_categories.get('payment_type', [])}
        - Existing Currencies: {user_categories.get('currency_types', [])}
        - Existing Source: {user_categories.get('source_type', [])}
        Only create a new category if the expense absolutely does not fit into the existing ones."""
    
    return taxonomy_prompt

async def user_taxonomy_prompt(user_id: str) -> str:
    """Fetches user categories and returns a formatted prompt constraint string."""
    user_categories = await fetch_user_expense_details(user_id)
    
    if not user_categories:
        return "" # Agar user ka naya account hai aur DB khali hai, toh prompt me kuch add mat karo
        
    taxonomy_prompt = f"""
        user's existing categories for expenses recorded:
        - Existing Types: {user_categories.get('type_list', [])}
        - Existing Payment Modes: {user_categories.get('payment_type', [])}
        - Existing Currencies: {user_categories.get('currency_types', [])}
        - Existing Source: {user_categories.get('source_type', [])}
        """
    
    return taxonomy_prompt
