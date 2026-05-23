"""Stage 1b — Google Tasks agent verification.

Run with:
    python -m tests.test_mcp_tasks

What this proves:
- The LLM can discover the Tasks MCP tools automatically
- The LLM correctly maps a plain English instruction to the right tool call
- The LLM constructs valid arguments without being told the tool name or schema
- The result lands in real Google Tasks

Each step sends a natural language instruction to a minimal agent and asks you
to verify the result in the Google Tasks app before proceeding. The agent handles
all tool selection and argument construction — your code never mentions tool names.

Each step logs the agent response to logs/assistant.log.
"""

# from __future__ import annotations

import asyncio
from pydantic_ai import Agent

from core.deps import AgentDeps
from core.logger import logger
from core.llm_factory import LLMFactory
from mcps.google import google_workspace_server



_factory = LLMFactory()

_SYSTEM_PROMPT = (
)


async def run() -> None:
    agent = Agent(
        model=_factory.get_model(),
        mcp_servers=[google_workspace_server(['tasks'])],
        system_prompt="""
            You are a task management assistant.
            Carry out the user's instruction exactly using the available tools.
            Confirm what you did in one sentence.
        """
    )

    logger.info("TEST | tasks | step=1 | create")
    result = await agent.run(
        "Create a task called '[1b test] MCP verification task' due tomorrow. "
        "Add to the 'Development' list"
        "Add a note: Created by test_mcp_tasks.py — safe to delete."
    )
 
    logger.info("TEST | tasks | step=1 | response=%r", result.output)
    print(f"\nStep 1 — Create\n  Agent: {result.output}")
    print("  → Open Google Tasks and confirm the task appears.")
    input("  Press Enter when confirmed...\n")


    # async with agent.run_mcp_servers():

    #     # ── Step 1: Create ──────────────────────────────────────────────────
    #     logger.info("TEST | tasks | step=1 | create")
    #     result = await agent.run(
    #         "Create a task called '[1b test] MCP verification task' due tomorrow. "
    #         "Add a note: Created by test_mcp_tasks.py — safe to delete."
    #     )
    #     logger.info("TEST | tasks | step=1 | response=%r", result.output)
    #     print(f"\nStep 1 — Create\n  Agent: {result.output}")
    #     print("  → Open Google Tasks and confirm the task appears.")
    #     input("  Press Enter when confirmed...\n")

    #     # ── Step 2: Update ──────────────────────────────────────────────────
    #     logger.info("TEST | tasks | step=2 | update")
    #     result = await agent.run(
    #         "Find the task called '[1b test] MCP verification task' "
    #         "and update its title to '[1b test] MCP verification task — updated' "
    #         "and move the due date to next Friday."
    #     )
    #     logger.info("TEST | tasks | step=2 | response=%r", result.output)
    #     print(f"Step 2 — Update\n  Agent: {result.output}")
    #     print("  → Confirm the task title and due date updated in Google Tasks.")
    #     input("  Press Enter when confirmed...\n")

    #     # ── Step 3: Delete ──────────────────────────────────────────────────
    #     logger.info("TEST | tasks | step=3 | delete")
    #     result = await agent.run(
    #         "Delete the task called '[1b test] MCP verification task — updated'."
    #     )
    #     logger.info("TEST | tasks | step=3 | response=%r", result.output)
    #     print(f"Step 3 — Delete\n  Agent: {result.output}")
    #     print("  → Confirm the task is gone from Google Tasks.")
    #     input("  Press Enter when confirmed...\n")

    #     print("✓ Google Tasks agent — all steps passed.\n")
    #     logger.info("TEST | tasks | ALL PASS")


asyncio.run(run())