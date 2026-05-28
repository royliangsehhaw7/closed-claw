from __future__ import annotations

import os
import uuid
import httpx
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from agents.supervisor import SupervisorAgent
from core.deps import AgentDeps
from core.logger import logger
from gateway.telegram_client import send_message
from memory.sqlite_store import SQLiteStore
from schemas.turn_record import TurnRecord


#
# CMD: uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload
#


# ── application state ─────────────────────────────────────────────────────────
 
_supervisor: SupervisorAgent
_store: SQLiteStore
_agent_lock = asyncio.Lock()


# ── environment ───────────────────────────────────────────────────────────────

_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
_USER_ID = os.getenv("USER_ID", "local_user")
_USER_EMAIL = os.getenv("USER_GOOGLE_EMAIL", "")
_LLM_MODEL = os.getenv("LLM_MODEL", "")

# ── application state ─────────────────────────────────────────────────────────

_supervisor: SupervisorAgent
_store: SQLiteStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic.
 
    Runs once when the process starts. Validates required config, initialises
    the SQLite store, and builds the SupervisorAgent. All three are reused
    across every request — not rebuilt per message.
 
    Raises RuntimeError on missing config so the process fails fast with a
    clear error rather than silently mishandling messages.
    """
    global _supervisor, _store
 
    if not _USER_EMAIL:
        raise RuntimeError("USER_GOOGLE_EMAIL is not set")
    if not _WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is not set")
    if not _ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
 
    _store = SQLiteStore()
    await _store.initialise()
 
    _supervisor = SupervisorAgent()
 
    logger.info(
        "gateway | started | user=%s | email=%s | allowed_chat_id=%d",
        _USER_ID, _USER_EMAIL, _ALLOWED_CHAT_ID,
    )
    yield
    logger.info("gateway | shutdown")
 
 
app = FastAPI(lifespan=lifespan)


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """Health check endpoint. Returns 200 when the gateway is ready."""
    return {"status": "ok"}



# ── basic apis ────────────────────────────────────────────────────────────────────
app.get("/basic1")
async def get_info(request: Request):
    # Access client IP
    client_host = request.client.host    
    # Access headers
    user_agent = request.headers.get("user-agent")    
    # Access cookies
    all_cookies = request.cookies
    
    return {
        "ip": client_host, 
        "user_agent": user_agent,
        "cookies": all_cookies
    }
@app.get("/basic2")           # ?param1=1&param2=2
async def get_data(param1: int, param2: int):
    return {
        "param1": param1,
        "param2": param2,
        "sum": param1 + param2
    }
@app.get("/basic3")          # ?name=john&age=30&role=admin
async def read_all_queries(request: Request):
    # Converts all query parameters into a standard Python dictionary
    query_params = dict(request.query_params)
    return {"all_params": query_params}
@app.get("/basic4/{value1}/param2/{value2}")
async def get_path_data(value1: int, value2: int):
    return {
        "param1_value": value1,
        "param2_value": value2,
        "product": value1 * value2
    }
@app.post("/post")
async def get_raw_body(request: Request):
    # Access raw body as bytes
    raw_body = await request.body()
    # Access body parsed as JSON (if content-type is application/json)
    json_body = await request.json()
    
    return {"raw": raw_body, "json": json_body}



# ── assistant ────────────────────────────────────────────────────────────────────
@app.post("/assistant/id/{chat_id}/msg/{chat}")
async def assistant(chat_id: int, chat: str) -> dict:
    deps = AgentDeps(
        user_id=_USER_ID,
        user_email=_USER_EMAIL,
    )

    # # 6. Run agent loop synchronously — Stage 3 moves this to a Redis queue
    try:
        response = await _supervisor.run(chat, deps)
    except Exception:
        logger.exception("webhook | agent loop failed | chat_id=%d", chat_id)
        await send_message(chat_id, "Something went wrong. Please try again.")
        return {"ok": True}

    # 7. Reply
    return {'message': response.message}



# ── webhook ───────────────────────────────────────────────────────────────────
## THIS WILL BE THE ENDPOINT FOR TELEGRAM BOT MESSAGES ##
@app.post("/webhook/{secret}")
async def webhook(
    secret: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Receive a Telegram Update and return 200 immediately.
 
    All agent work is offloaded to a background task so Telegram receives its
    200 OK in milliseconds — before any LLM or MCP work begins. This prevents
    Telegram from retrying delivery on slow agent runs, which would cause
    concurrent agent runs competing for the same MCP connection.
 
    Always returns 200 for non-403 responses — even for ignored messages —
    so Telegram never retries unnecessarily.
    """
    # 1. Validate secret — reject unknown callers immediately
    if secret != _WEBHOOK_SECRET:
        logger.warning("webhook | invalid secret | received=%r", secret)
        raise HTTPException(status_code=403, detail="Forbidden")
 
    update = await request.json()
    logger.debug("webhook | update=%r", update)
 
    # 2. Extract message — ignore edits, reactions, and other non-message updates
    message = update.get("message")
    if not message:
        return {"ok": True}
 
    chat_id: int = message.get("chat", {}).get("id", 0)
    text: str = message.get("text", "").strip()
 
    # 3. Allowlist check — only your chat_id is permitted this stage
    if chat_id != _ALLOWED_CHAT_ID:
        logger.warning("webhook | unauthorised chat_id=%d | ignoring", chat_id)
        return {"ok": True}
 
    # 4. Handle commands; ignore empty messages
    if not text:
        return {"ok": True}
    if text.startswith("/"):
        if text == "/start":
            await send_message(chat_id, "Assistant ready. Send me a message.")
        return {"ok": True}
 
    logger.info("webhook | chat_id=%d | text=%r", chat_id, text)
 
    # 5. Return 200 immediately — agent work runs after this response is sent.
    # Telegram gets its 200 in milliseconds and never retries.
    background_tasks.add_task(_process, chat_id, text)
    return {"ok": True}
 
 
async def _process(chat_id: int, text: str) -> None:
    """Process a message after 200 has already been returned to Telegram.
 
    Protected by _agent_lock so only one agent run executes at a time.
    Rapid messages or any startup flush queue here and run in order rather
    than racing for the same MCP connection.
    """
    async with _agent_lock:
 
        # 6. Build deps — identity resolved here, never inside agents
        deps = AgentDeps(
            user_id=_USER_ID,
            user_email=_USER_EMAIL,
        )
 
        # 7. Run agent loop — Stage 3 moves this to a Redis queue
        try:
            response = await _supervisor.run(text, deps)
        except Exception:
            logger.exception("webhook | agent loop failed | chat_id=%d", chat_id)
            await send_message(chat_id, "Something went wrong. Please try again.")
            return
 
        # 8. Reply
        await send_message(chat_id, response.message)
 
        # 9. Write turn record
        record = TurnRecord(
            turn_id=str(uuid.uuid4()),
            user_id=_USER_ID,
            user_email=_USER_EMAIL,
            agent_name="supervisor",
            user_input=text,
            agent_output=response.message,
            model=_LLM_MODEL,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await _store.write_turn(record)