from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import interrupt, Command
from langgraph.prebuilt import ToolNode, tools_condition  # CHANGED: tools ke liye
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from typing import Any, cast, Optional, Literal  # CHANGED: Literal add kiya
from pydantic import Field, BaseModel  # CHANGED: BaseModel add kiya

import json, asyncio, os
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from dotenv import load_dotenv
load_dotenv()

from repository.jomoai import jomoai
from services.image_files import ExpenseDetails
from utils.basics import ExpenseDetailsData, user_taxonomy_prompt, get_text, format_expense_summary, DecissionNode, get_dynamic_taxonomy_prompt
        
from repository.helper import send_confirm_buttons  # CHANGED: buttons bhejne ke liye
from utils.tools import get_current_date, convert_currency, record_expense, fetch_expenses_by_date, fetch_all_expenses, fetch_expenses_by_record_date, fetch_expenses_by_type, fetch_expenses_by_source, fetch_expenses_by_currency # type: ignore # 
#=================================================================
#====================  ENV VARIABLE SETUP  =======================
DBConnection = os.getenv("DATA_BASE_URL")
if not DBConnection:
    raise ValueError("DATA_BASE_URL environment variable is not set")

async_pool = AsyncConnectionPool(
        conninfo=DBConnection,
        max_size=20,
        min_size=1,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False
    )

async def memory_saver_state():
    try:
        await async_pool.open()          
        saver = AsyncPostgresSaver(conn=cast(Any, async_pool))
        await saver.setup()             
        return saver
    except Exception as e:
        raise ValueError(f"Error creating memory saver state: {e}")

#=================================================================
#=======================  TOOLS SETUP =============================
TOOLS = [get_current_date, convert_currency, record_expense, fetch_expenses_by_date, fetch_all_expenses, fetch_expenses_by_record_date, fetch_expenses_by_type, fetch_expenses_by_source, fetch_expenses_by_currency]
llm_with_tools = jomoai.bind_tools(TOOLS)  # CHANGED

#=================================================================
#=========================  Graph State ===========================
class ExpenseState(MessagesState):
    text: Optional[dict]
    extracted_expense: Optional[list]
    decision: Optional[str]
    correction_text: Optional[str]
    date_and_time: Optional[str]

#=================================================================
#=========================  Chat State ===========================
async def chat_node(state: ExpenseState, config: RunnableConfig):
    last_human_idx = 0
    for i in range(len(state['messages']) - 1, -1, -1):
        if isinstance(state['messages'][i], HumanMessage):
            last_human_idx = i
            break

    #--------------- Gather and Config User Info -------------------
    import datetime
    user_id = config['configurable']['thread_id'] # type: ignore
    user_taxonomy = await user_taxonomy_prompt(user_id)
    current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
    sys_config = {"name": "jomoAI", "role": "A Expense Record and Track System AI", 
                  "version": 'v-01', "established": "15 August 2026", "trained by": "Ankush Gautam",
                  "user_expense": 'Fetch Recordof user Expense via tools call',
                  "available_tools": 'get_current_date, convert_currency, record_expense, fetch_expenses_by_date, fetch_all_expenses, fetch_expenses_by_record_date, fetch_expenses_by_type, fetch_expenses_by_source, fetch_expenses_by_currency',
                  "user_current_records": user_taxonomy,
                  "current_date": current_date_str}
    sys_msg = SystemMessage(content=f"{str(sys_config)}")
    
    #------------- Sliding Window + Unified Truncation --------------
    current_turn_messages = state['messages'][last_human_idx:]
    past_messages = state['messages'][:last_human_idx]
    # Ab ye picchli 30 baatein yaad rakhega
    recent_past = past_messages[-40:] if past_messages else []
    recent_messages = recent_past + current_turn_messages

    safe_messages = []
    for msg in recent_messages:
        text_content = get_text(msg.content)
        if text_content and len(text_content) > 1000:
            truncated_text = text_content[:1000] + "\n\n...[Context truncated]"
            safe_messages.append(msg.model_copy(update={"content": truncated_text}))
        else:
            safe_messages.append(msg)

    #------------------- API CRASH PROTECTION -----------------------
    while len(safe_messages) > 0 and not isinstance(safe_messages[0], HumanMessage):
        safe_messages.pop(0)
        
    if len(safe_messages) == 0:
        safe_messages = [HumanMessage(content="Continue.")]

    #------------------- INTENT CHECK (Via DecissionNode) -----------------------
    history_string = "\n".join(f"{m.type}: {get_text(m.content)}" for m in safe_messages)
    is_expense_related = await DecissionNode(
        query=get_text(current_turn_messages[0].content), 
        model=jomoai, 
        history=history_string
    )
    
    if not is_expense_related:
        return {'messages': [AIMessage(content="I am here to help you with expense and finance related only. Kindly ask only related to your Expense only!")]}

    #------------------------ FINAL CALL -----------------------------
    response = await llm_with_tools.ainvoke([sys_msg] + safe_messages, config)
    
    state_updates = {'messages': [response]}
    
    if hasattr(response, 'tool_calls') and response.tool_calls:
        if response.tool_calls[0]['name'] == 'record_expense':
            state_updates['correction_text'] = response.tool_calls[0]['args']['description']
            
    return state_updates # type: ignore

def route_after_chat(state: ExpenseState, config: RunnableConfig):
    last_msg = state['messages'][-1]
    tool_calls = getattr(last_msg, 'tool_calls', None) or []
    if not tool_calls:
        return END
    if tool_calls[0]['name'] == 'record_expense':
        return 'correction_node'
    return 'tool_node'

#=================================================================
#=======================  DOCUMENTS STATE ========================
from services.image_files import image_process, read_image
from services.audio import read_audio, audio_process
from services.files import files_process, process_files
from dotenv import load_dotenv
import os
load_dotenv()
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

async def image_node(state: ExpenseState, config: RunnableConfig):
    user_id = config['configurable']['thread_id']  # type: ignore
    message = state['text']
    phone_number = config['configurable']['user_id'] # type: ignore
    path, caption = await image_process(message, ACCESS_TOKEN, phone_number)
    if path is None:
        return {"messages": [AIMessage(content="Image process karne mein dikkat aayi, dobara try karo.")]}
    result = await read_image(user_id, path, caption or "")
    #await asyncio.to_thread(os.remove, path)
    if not result.is_expense:
        return {"messages": [AIMessage(content="Image mein koi expense detail nahi mila.")]}
    expense_list = [x.model_dump() for x in result.expense_details] # type: ignore
    return {
        "messages": [HumanMessage(content=f"[Image received] Extracted: {expense_list}")],
        "extracted_expense": expense_list,
    }

async def audio_node(state: ExpenseState, config: RunnableConfig):
    user_id = config['configurable']['thread_id'] # type: ignore
    message = state['text']
    phone_number = config['configurable']['user_id'] # type: ignore
    path = await audio_process(message, ACCESS_TOKEN, phone_number)
    mime_type = message["audio"]["mime_type"] # type: ignore
    if path is None:
        return {"messages": [AIMessage(content="Audio process karne mein dikkat aayi, dobara try karo.")]}
    result = await read_audio(user_id, path, mime_type=mime_type)
    await asyncio.to_thread(os.remove, path)
    if not result.is_expense:
        return {"messages": [AIMessage(content="Audio mein koi expense detail nahi mila.")]}
    expense_list = [x.model_dump() for x in result.expense_details] # type: ignore
    return {
        "messages": [HumanMessage(content=f"[Audio received] Extracted: {expense_list}")],
        "extracted_expense": expense_list,
    }


async def document_node(state: ExpenseState, config: RunnableConfig):
    user_id = config['configurable']['thread_id'] # type: ignore
    message = state['text']
    phone_number = config['configurable']['user_id'] # type: ignore

    path, caption_text, mime_type = await files_process(message, ACCESS_TOKEN, phone_number)

    document_types = [
        "application/pdf", "text/plain", "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    if path is None:
        return {"messages": [AIMessage(content="Document process karne mein dikkat aayi, dobara try karo.")]}

    if mime_type not in document_types:
        await asyncio.to_thread(os.remove, path)
        return {"messages": [AIMessage(content="Is file type ko abhi support nahi kiya jaata.")]}

    expense_list = await process_files(user_id, mime_type, path, caption_text)
    #await asyncio.to_thread(os.remove, path)

    if not expense_list:
        return {"messages": [AIMessage(content="Document mein koi expense detail nahi mila.")]}

    return {
        "messages": [HumanMessage(content=f"[Document received] Extracted: {expense_list}")],
        "extracted_expense": expense_list,
    }

def route_by_type(state: ExpenseState, config: RunnableConfig):
    message = state.get('text')
    if message is None:
        return END
    msg_type = message.get('type')
    if msg_type == 'image':
        return 'image_node'
    if msg_type == 'audio':
        return 'audio_node'
    if msg_type == 'document':
        return 'document_node'
    if msg_type == 'text':
        return 'chat_node'
    return END

#==================================================================
#=======================  CONFIRM / CORRECTION / SAVE  ============
from utils.basics import create_expense_pdf
from services.meta.endpoints import upload_document, send_document
import asyncio

async def prompt_confirm_node(state: ExpenseState, config: RunnableConfig):  
    expense_list = state.get('extracted_expense')
    user_id = config['configurable']['user_id'] # type: ignore
    
    # --- TERA MASTERSTROKE LOGIC ---
    if not expense_list:
        summary_text = "I could not dedect any Expenses in your Media/Text." \
        "If there was any expense in your Media you may reply with text or just 'Discard'."

        return {"messages": [AIMessage(content=summary_text)]}
    else:
        summary_text = format_expense_summary(expense_list)
    # -------------------------------
    
    # CHARACTER LIMIT CHECK (Meta 1024 limit for interactive buttons)
    if len(summary_text) > 1000:
        print("[PDF] Text > 1000 chars. Generating PDF...")
        # 1. PDF Banao
        pdf_path = await asyncio.to_thread(create_expense_pdf, expense_list, user_id)
        # 2. Upload karo
        media_id = await upload_document(pdf_path)
        # 3. Document shoot kardo as a side-effect
        if media_id:
            doc_payload = {
                "media_id": media_id,
                "filename": "Expense_Report.pdf",
                "caption": "The Extraction of Exapense was exceeding the whatsapp text limit,\nSo the PDF is given, Kindly check!"
            }
            await send_document(user_id, doc_payload)
            
            # 4. Graph me short text update kardo taaki response() button bhej de
            return {"messages": [AIMessage(content="Kindly check extracted Expenses in above PDF.\n"\
                                           "*Click:*\n*Save:* To record\n*Discard:* To cancel\n\n*Or,* simply reply with any changes you want to make.")]}
            
    # Agar text chhota hai, toh direct original text jayega
    return {"messages": [AIMessage(content=summary_text)]}


class ConfirmDecision(BaseModel):  # CHANGED: naya model, free-text fallback classification ke liye
    decision: Literal["save", "cancel", "change"] = Field(..., description="User's intent: 'save' agar wo expense confirm/save karna chahta hai, 'cancel' agar discard/delete karna chahta hai, 'change' agar kisi field mein correction chahta hai")
    correction_text: Optional[str] = Field(None, description="Agar decision 'change' hai, to exact correction jo user ne bola. Warna null.")

async def wait_and_process_confirm_node(state: ExpenseState, config: RunnableConfig):
    user_id = config['configurable']['thread_id'] # type: ignore
    user_reply = interrupt("Waiting for user confirmation")
    reply_clean = user_reply.strip().lower()

    if reply_clean == "save":  # CHANGED: button-click ka exact title, LLM call nahi lagti
        return {"decision": "save"}
    if reply_clean == "discard":  # CHANGED
        return {"decision": "cancel"}
    if not reply_clean:
        return {"decision": "invalid", "messages": [AIMessage(content="Kindly Save or Discard the last Expense first! \
        or reply if You need any Changes in it.\n\n \
        *NOTE*: You have to sent this media again to record Expense.")]}
    
    parser = PydanticOutputParser(pydantic_object=ConfirmDecision)
    import datetime
    current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
    rules = await get_dynamic_taxonomy_prompt(user_id)
            
    template = PromptTemplate(
        template='User ko expense confirm karne ke liye Save/Discard buttons diye gaye the, lekin usne free text reply kiya: "{user_reply}"\n\n'
                 'Uska intent decide karo — save karna hai, cancel/discard karna hai, ya kuch change/correct karna hai. '
                 'Agar change hai to exact correction text bhi do.\n{format_instruction}'
                 f'just for information today is {current_date_str}'
                 f'{rules}',
        input_variables=['user_reply'],
        partial_variables={'format_instruction': parser.get_format_instructions()}
    )
    message = HumanMessage(content=template.format(user_reply=user_reply))
    result = await (jomoai | parser).ainvoke([message])

    if result.decision == "save":
        return {"decision": "save"}
    if result.decision == "cancel":
        return {"decision": "cancel"}
    return {"decision": "change", "correction_text": result.correction_text or user_reply}


def route_after_confirm(state: ExpenseState, config: RunnableConfig):
    decision = state.get("decision")
    if decision == "save":
        return "save_node"
    if decision == "cancel":
        return "cancel_node"
    if decision == "invalid":
        return "wait_and_process_confirm_node"  # <--- END ki jagah wapas purane node pe bhej diya!
    return "correction_node"

async def cancel_node(state: ExpenseState, config: RunnableConfig):
    return {"messages": [AIMessage(content="Indeed, Transaction was Discarded.\nSend your next Expenses if you want to record something.")]}

async def correction_node(state: ExpenseState, config: RunnableConfig):
    expense_list = state['extracted_expense']
    correction_text = state['correction_text']
    user_id = config['configurable']['thread_id'] # type: ignore
    rules = await get_dynamic_taxonomy_prompt(user_id)
    import datetime
    current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
    parser = PydanticOutputParser(pydantic_object=ExpenseDetails)
    template = PromptTemplate(
        template='Yahan expense list hai:\n{expense_list}\n\n \
            User ne ye correction bola: {correction}\n\n \
            Updated list do.\n{format_instruction}'
            f'just for information today is {current_date_str}'
            f'{rules}',
        input_variables=['expense_list', 'correction'],
        partial_variables={'format_instruction': parser.get_format_instructions()}
    )
    message = HumanMessage(content=template.format(expense_list=expense_list, correction=correction_text))
    result = await (jomoai | parser).ainvoke([message])

    if not result.expense_details:  # CHANGED: defensive check, crash se pehle
        return {
            "messages": [AIMessage(content="Could not get the last text, Kindly clearly tell what to change.")],
            "extracted_expense": expense_list,
        }

    updated_expenses = [x.model_dump() for x in result.expense_details] # type: ignore

    history_updates = [
        HumanMessage(content=f"[Correction Requested]: {correction_text}"),
        AIMessage(content=f"[Correction Applied]: {updated_expenses}")
    ]

    return {
        "extracted_expense": updated_expenses,
        "messages": history_updates
    }


import re
from dateutil import parser as date_parser  # CHANGED: pip install python-dateutil --break-system-packages agar nahi laga hai

def _clean_amount(raw) -> float:  # CHANGED: "Rs 500", "₹500.50" jaisa kuch bhi safely float banaye
    try:
        cleaned = re.sub(r"[^\d.]", "", str(raw))
        return float(cleaned) if cleaned else 0.0
    except Exception:
        return 0.0

def _clean_date(raw):  # CHANGED: kisi bhi format ka date string parse kare, fail hone pe aaj ki date
    try:
        return date_parser.parse(str(raw), dayfirst=True).date()
    except Exception:
        import datetime
        return datetime.date.today()

async def save_node(state: ExpenseState, config: RunnableConfig):
    thread_id = config['configurable']['thread_id']  # type: ignore
    user_id = config['configurable']['user_id']  # type: ignore
    expense_list = state.get('extracted_expense')

    if not expense_list:
        return {"messages": [AIMessage(content="Expense was not recorded because data was empty or what media you sent does not include any expense. Kindly try Again.")]}

    raw_message = state.get('text') or {}
    source = raw_message.get('type', 'unknown')  # CHANGED: image/audio/document/text — kahan se aaya
    async with async_pool.connection() as conn:
        for exp in expense_list: # type: ignore
            await conn.execute("""
                INSERT INTO expenses (user_id, type, amount, amount_in_words, currency, payment_mode, description, date, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (thread_id, exp.get('type'), _clean_amount(exp.get('amount')), exp.get('amount_in_words'), exp.get('currency', 'INR'),
                exp.get('payment_mode'), exp.get('description'), _clean_date(exp.get('date')), source,))
    return {"messages": [AIMessage(content="Your Expense have been saved!")]}

#=================================================================
#=======================  GRAPH STATE ============================
async def graph_state(checkpoint):
    graph = StateGraph(ExpenseState)

    graph.add_node('chat_node', chat_node) # type: ignore
    graph.add_node('tool_node', ToolNode(TOOLS))
    graph.add_node('image_node', image_node) # type: ignore
    graph.add_node('audio_node', audio_node) # type: ignore
    graph.add_node('document_node', document_node) # type: ignore
    graph.add_node('prompt_confirm_node', prompt_confirm_node)
    graph.add_node('wait_and_process_confirm_node', wait_and_process_confirm_node)
    graph.add_node('correction_node', correction_node)
    graph.add_node('save_node', save_node)
    graph.add_node('cancel_node', cancel_node)

    graph.add_conditional_edges(START, 
        route_by_type, 
        {"chat_node": "chat_node",
        "image_node": "image_node", 
        "audio_node": "audio_node", 
        "document_node": "document_node", 
        END: END})
    
    graph.add_edge('image_node', 'prompt_confirm_node')
    graph.add_edge('audio_node', 'prompt_confirm_node')
    graph.add_edge('document_node', 'prompt_confirm_node')
    
    graph.add_edge('prompt_confirm_node', 'wait_and_process_confirm_node')

    graph.add_conditional_edges('wait_and_process_confirm_node',
        route_after_confirm,
        {"save_node": "save_node", 
        "correction_node": "correction_node", 
        "cancel_node": "cancel_node", 
        "wait_and_process_confirm_node": "wait_and_process_confirm_node"})

    graph.add_edge('cancel_node', END)
    graph.add_edge('save_node', END)
    graph.add_edge('correction_node', 'prompt_confirm_node')

    graph.add_conditional_edges('chat_node', 
        route_after_chat, 
        {"tool_node": "tool_node", 
         "correction_node": "correction_node", 
         END: END})
    
    graph.add_edge('tool_node', 'chat_node')

    workflow = graph.compile(checkpointer=checkpoint)
    return workflow

#=================================================================
#=======================  Module Imports =========================
async def make_global():
    global workflow
    await async_pool.open()
    checkpointer = await memory_saver_state()
    workflow = await graph_state(checkpointer)

def extract_reply_text(message: dict) -> str:
    if message.get("type") == "text":
        return message["text"]["body"]
    if message.get("type") == "interactive":
        return message["interactive"]["button_reply"]["title"]
    return ""

async def response(message: dict, thread_id: str, user_id: str):
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    state = await workflow.aget_state(config) # type: ignore
    import datetime
    current_date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
    sys_msg = SystemMessage(content=f"current_date: {current_date_str}")

    try:
        if state.next:
            user_reply = extract_reply_text(message)
            result_state = await workflow.ainvoke(Command(resume=user_reply), config=config) # type: ignore
        else:
            if message['type'] == "text":
                clean_text = HumanMessage(content=message["text"]["body"] or "")
                initial_state = {"text": message, "messages":[clean_text], "extracted_expense": None, "decision": None, "correction_text": None, "date_and_time": str(sys_msg)}
            else:
                initial_state = {"text": message, "extracted_expense": None, "decision": None, "correction_text": None, "date_and_time": str(sys_msg)}

            result_state = await workflow.ainvoke(initial_state, config=config) # type: ignore

        new_state = await workflow.aget_state(config)  # type: ignore # CHANGED: invoke ke baad dekho kahan pause hua
        if new_state.next and 'wait_and_process_confirm_node' in new_state.next:  # CHANGED
            summary_text = get_text(result_state["messages"][-1].content) if result_state.get("messages") else "Confirm karo:"
            await send_confirm_buttons(user_id, summary_text)  # CHANGED: buttons seedha yahin se
            return None  # CHANGED: main.py dobara text na bheje

        if result_state and result_state.get("messages"):
            last_msg = result_state["messages"][-1]
            if last_msg.type == "ai" and last_msg.content:
                return get_text(last_msg.content)
        return None
    except Exception as e:
        raise ValueError(f"Error processing the request: {e}")

async def update_daily_tokens(user_id: str, tokens: int):
    async with async_pool.connection() as conn:
        await conn.execute("""
            INSERT INTO daily_usage (user_id, tokens, date)
            VALUES (%s, %s, CURRENT_DATE)
            ON CONFLICT (user_id, date)
            DO UPDATE SET tokens = daily_usage.tokens + EXCLUDED.tokens
        """, (user_id, tokens))
        await conn.commit()
        
async def save_silent_history(thread_id: str, user_id: str, human_text: str, ai_text: str):
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    await workflow.aupdate_state(config,{"messages": [HumanMessage(content=human_text), AIMessage(content=ai_text)]}) # type: ignore