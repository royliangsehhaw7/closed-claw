from __future__ import annotations

from datetime import date
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from agents.base import BaseAgent
from mcps.google import google_workspace_server
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.executor_result import ExecutorResult

_factory = LLMFactory()


class ExecutorAgent(BaseAgent):
    """Single specialist agent for one user, with full MCP tool surface.

    Instantiated per request inside delegate_to_executor. The MCP server is
    started and stopped within each run() call via `async with self._agent`.

    The LLM decides which tools to call. This class never specifies tool names,
    service names, or routing logic of any kind.

    Adding a new integration means appending its MCP server to toolsets=[].
    No other code changes anywhere.
    """

    def __init__(self, user_email: str) -> None:
        super().__init__(name="executor")
        self._user_email = user_email

        self._agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),
            output_type=ExecutorResult,
            deps_type=AgentDeps,
            # No tools= here — log_decision has been removed.
            # Logging is done in Python after agent.run() returns.
            toolsets=[
                # One server for all services. Passing all three names to a
                # single MCPServerStdio avoids tool name collisions that occur
                # when workspace-mcp is split into multiple server instances.
                # To add Trello: append trello_mcp_server(user_email) here.
                google_workspace_server(
                    ["calendar", "tasks", "gmail"],
                    user_email=user_email,
                ),
            ],
        )

    def _build_system_prompt(self) -> str:
        # Inject today's date so the LLM doesn't guess when computing
        # "this week", "next Friday", etc. Without this it defaults to its
        # training cutoff, producing wrong dates.
        today = date.today().isoformat()
        return (
            f"Today's date is {today}.\n\n"
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

    @staticmethod
    def _log_messages(user_id: str, messages: list[Any]) -> None:
        """Walk the completed message list and log every tool call and result.

        Called after agent.run() returns. Never runs during the LLM loop,
        so it has zero effect on context or token consumption.

        PydanticAI message types used here:
          ModelResponse  — what the LLM returned (may contain ToolCallPart)
          ModelRequest   — what was sent to the LLM (may contain ToolReturnPart)
          ToolCallPart   — one tool call the LLM requested
          ToolReturnPart — the result of that tool call
        """
        for msg in messages:
            if isinstance(msg, ModelResponse):
                # Log each tool call the LLM made
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        logger.warning(
                            "ExecutorAgent.tool_call | user=%s | tool=%s | args=%r",
                            user_id, part.tool_name, part.args,
                        )
            elif isinstance(msg, ModelRequest):
                # Log each tool result returned to the LLM
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        logger.warning(
                            "ExecutorAgent.tool_result | user=%s | tool=%s | content=%r",
                            user_id, part.tool_name, part.content,
                        )

    async def run(self, sub_task: str, deps: AgentDeps) -> ExecutorResult:
        logger.critical(
            "ExecutorAgent.run | user=%s | email=%s | sub_task=%r",
            deps.user_id, self._user_email, sub_task,
        )

        # async with self._agent ensures the MCP subprocess is started before
        # any tool listing or calls, and cleanly stopped when the block exits.
        # Without this, tool listing is lazy and may race with the first call.
        async with self._agent:
            result = await self._agent.run(
                user_prompt=sub_task,
                deps=deps,
            )

        # Log all tool calls and results from the completed run.
        # This happens after agent.run() returns — never inside the LLM loop.
        self._log_messages(deps.user_id, result.all_messages())

        # Log token usage for the full executor run.
        usage = result.usage
        logger.critical(
            "ExecutorAgent.usage | user=%s | input=%s | output=%s | total=%s",
            deps.user_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )

        output: ExecutorResult = result.output
        logger.info(
            "ExecutorAgent.result | user=%s | actions=%r | missing=%r",
            deps.user_id, output.actions_taken, output.missing_info,
        )
        return output