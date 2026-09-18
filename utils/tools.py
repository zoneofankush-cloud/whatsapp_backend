import asyncio, requests
from datetime import date
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from fastapi import HTTPException
from typing import Optional

@tool
async def get_current_date() -> str:
    """Use this tool whenever the question depends on today's date — 'aaj kitna kharch hua', 'is mahine ka total', 'kal', 'last week' jaisa kuch bhi relative-date related. Returns today's date."""
    return date.today().strftime("%A, %B %d, %Y")

@tool
async def convert_currency(base_currency: str, target_currency: str, base_currency_value: float = 1.0):
    """Convert an amount from one currency to another using live exchange rates. Use for e.g. '500 rupaye kitne dollar honge'."""
    def convert():
        url = f"https://open.er-api.com/v6/latest/{base_currency.upper()}"
        response = requests.get(url)
        data = response.json()
        target = data["rates"][target_currency.upper()]
        return {
            "base_currency": base_currency.upper(),
            "target_currency": target_currency.upper(),
            "conversion_factor": target,
            "converted_value": base_currency_value * target,
        }
    try:
        return await asyncio.to_thread(convert)
    except Exception as e:
        return {"error": f"Currency conversion failed: {e}"}

@tool
async def record_expense(description: str) -> str:
    """User NAYA expense record/log karna chahta hai. Uska poora expense description yahan daalo jaisa usne bola."""
    return description

@tool
async def fetch_expenses_by_date(config: RunnableConfig, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list:
    """Fetch this user's recorded expenses strictly between start_date and end_date (YYYY-MM-DD format). Use for any query like 'is mahine kitna kharcha', 'aaj ka kharcha'."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT type, amount, currency, payment_mode, date, description, source
            FROM expenses 
            WHERE user_id = %s AND date >= %s AND date <= %s
            ORDER BY date DESC
            """, (user_id, start_date, end_date))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
    
@tool
async def fetch_all_expenses(config: RunnableConfig) -> list:
    """Fetch ALL of this user's recorded expenses. Use ONLY when the user explicitly asks for all their expenses without any filter or time range."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT * FROM expenses 
            WHERE user_id = %s
            ORDER BY date DESC
            """, (user_id,))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
    
@tool
async def fetch_expenses_by_record_date(config: RunnableConfig, record_date: Optional[str] = None) -> list:
    """Fetch expenses based on when they were recorded into the database (created_at). record_date must be in YYYY-MM-DD format."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT * FROM expenses 
            WHERE user_id = %s AND DATE(created_at) = %s
            ORDER BY date DESC
            """, (user_id, record_date, ))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
    
@tool
async def fetch_expenses_by_type(config: RunnableConfig, type: str) -> list:
    """Fetch user's expenses filtered by a specific category/type (e.g. 'Food', 'Travel', 'Shopping')."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT * FROM expenses 
            WHERE user_id = %s AND type = %s
            ORDER BY date DESC
            """, (user_id, type, ))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
    
@tool
async def fetch_expenses_by_source(config: RunnableConfig, source: str) -> list:
    """Fetch user's expenses filtered by the source of entry (e.g., 'image', 'audio', 'document', 'text')."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT * FROM expenses 
            WHERE user_id = %s AND source = %s
            ORDER BY date DESC
            """, (user_id, source, ))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
    
@tool
async def fetch_expenses_by_currency(config: RunnableConfig, currency: str) -> list:
    """Fetch user's expenses filtered by a specific currency (e.g. 'INR', 'USD')."""
    from apps.graph import async_pool
    user_id = config['configurable']['thread_id'] # type: ignore
    try:
        async with async_pool.connection() as conn:
            cur = await conn.execute("""SELECT * FROM expenses 
            WHERE user_id = %s AND currency = %s
            ORDER BY date DESC
            """, (user_id, currency, ))
            rows = await cur.fetchall()
            clean_rows = [{k: str(v) for k, v in row.items()} for row in rows]
            return clean_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch data, Error:{str(e)}")
