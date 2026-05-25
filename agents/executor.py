from __future__ import annotations

from pydantic_ai import Agent

from .base_agent import BaseAgent
from mcps.google import google_workspace_server
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.executor_result import ExecutorResult

_factory = LLMFactory()


class ExecutorAgent(BaseAgent):
    """Single specialist agent for one user, with full MCP tool surface.

    Constructed once per user by ExecutorPool and reused across that user's
    requests. The MCP server is bound to user_email at construction time —
    all calls on this instance act on that user's account.

    The LLM decides which tools to call. This class never specifies tool names,
    service names, or routing logic of any kind.

    Adding a new integration means appending its MCP server to mcp_servers.
    No other code changes anywhere.

    Stage 1c: one instance, one user, Google Workspace only.
    Stage 2+: one instance per authenticated user, MCP list grows.
    """

    def __init__(self, user_email: str) -> None:
        super().__init__(name="executor")            # loads memory/agents/executor.md
        self._user_email = user_email
        self._agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),
            output_type=ExecutorResult,
            toolsets=[
                # Credential file selected by user_email at construction time.
                # To add Trello: append trello_mcp_server(user_email) here.
                google_workspace_server(
                    ["tasks", "calendar", "gmail"],
                    user_email=user_email,
                ),
            ],
        )

    def _build_system_prompt(self) -> str:
        base = (
            "You are an execution specialist. You carry out actions on behalf "
            "of the user using whatever tools are available to you.\n\n"
            "Rules:\n"
            "- Use all tools necessary to fully complete the request in one "
            "response. You may call multiple tools.\n"
            "- When you create a task that has a deadline, always create a "
            "matching calendar event in the same response. Do not wait to be asked.\n"
            "- Act immediately using the information provided. Do not ask for "
            "confirmation before acting.\n"
            "- Only pause if something required is genuinely missing — recipient, "
            "subject, body, or task title. If so, set missing_info to describe "
            "exactly what is needed and do not call any action tools.\n"
            "- Populate actions_taken with one specific entry per tool call: "
            "include titles, dates, recipients.\n"
            "- Never invent IDs, email addresses, or task names. If a lookup "
            "returns nothing, say so in summary."
        )
        return f"{base}\n\n{self._persona}".strip() if self._persona else base

    async def run(self, sub_task: str, deps: AgentDeps) -> ExecutorResult:
        logger.info(
            "ExecutorAgent.run | user=%s | email=%s | sub_task=%r",
            deps.user_id, self._user_email, sub_task,
        )

        async with self._agent.run_sync():
            result = await self._agent.run(
                user_prompt=sub_task,
                deps=deps,
            )

        output: ExecutorResult = result.output
        logger.info(
            "ExecutorAgent.run | user=%s | actions=%r | missing=%r",
            deps.user_id, output.actions_taken, output.missing_info,
        )
        return output