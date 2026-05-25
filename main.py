"""Entry point for Stage 1c.

Responsibilities:
- Resolve user identity from .env (USER_ID, USER_GOOGLE_EMAIL).
- Build AgentDeps — fully populated before any agent is called.
- Initialise SupervisorAgent and SQLiteStore once at startup.
- Run the input loop: read → run → print → log.

Stage 2 replaces this file with a FastAPI Gateway. The identity resolution
moves from .env to a user store keyed by Telegram chat_id. The supervisor.run()
call and store.write_turn() call are identical — Stage 2 wraps them, not rewrites.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

from agents.supervisor import SupervisorAgent
from core.deps import AgentDeps
from core.logger import logger
from memory.sqlite_store import SQLiteStore
from schemas.turn_record import TurnRecord

load_dotenv()

# Identity resolved at startup from .env.
# In Stage 2 this moves to the Gateway webhook handler, keyed by Telegram chat_id.
USER_ID           = os.getenv("USER_ID", "local_user")
USER_GOOGLE_EMAIL = os.getenv("USER_GOOGLE_EMAIL", "")


async def main() -> None:
    if not USER_GOOGLE_EMAIL:
        raise RuntimeError("USER_GOOGLE_EMAIL is not set in .env")

    # Initialise once. SupervisorAgent holds conversation history across turns.
    supervisor = SupervisorAgent()
    store = SQLiteStore()
    await store.initialise()

    logger.info("Assistant started | user=%s | email=%s", USER_ID, USER_GOOGLE_EMAIL)
    logger.info("-" * 50)
    print("Assistant ready. Type your message. Ctrl+C to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            logger.info("********** Assistant stopped by user **********")
            break

        if not user_input:
            continue

        # AgentDeps built here — fully populated before any agent is called.
        # In Stage 2 this is built in the Gateway webhook handler instead.
        deps = AgentDeps(
            user_id=USER_ID,
            user_email=USER_GOOGLE_EMAIL,
        )

        response = await supervisor.run(user_input, deps)
        print(f"Assistant: {response.message}\n")

        # Token counts come from SupervisorAgent.run() which logs them via
        # result.usage(). TurnRecord fields default to 0 here — wire them
        # from result.usage() in Stage 3 when token budgeting matters.
        record = TurnRecord(
            turn_id=str(uuid.uuid4()),
            user_id=USER_ID,
            user_email=USER_GOOGLE_EMAIL,
            agent_name="supervisor",
            user_input=user_input,
            agent_output=response.message,
            model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
            timestamp=datetime.now(tz=timezone.utc),
        )
        await store.write_turn(record)


asyncio.run(main())