"""Entry point for Stage 1a.

Run with:
    python main.py

Replaced by the FastAPI Gateway entry point in Stage 2. The agent loop
logic here mirrors what will run inside the per-user asyncio.Queue drain
coroutine in Stage 2 — kept intentionally simple.
"""

# from __future__ import annotations

import asyncio

from core.logger import logger
from core.deps import AgentDeps
from core.blackboard import Blackboard
from agents.supervisor import SupervisorAgent

USER_ID = "local_user"


async def main() -> None:
    supervisor = SupervisorAgent()

    logger.info("Assistant started | user=%s", USER_ID)
    print("Assistant ready. Type your message. Ctrl+C to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            logger.info("Assistant stopped by user")
            break

        if not user_input:
            continue

        deps = AgentDeps(
            user_id=USER_ID,
            blackboard=Blackboard(),
        )

        response = await supervisor.run(user_input, deps)
        print(f"Assistant: {response}\n")


asyncio.run(main())