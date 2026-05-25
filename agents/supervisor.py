from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ModelRequest, ToolCallPart, ToolReturnPart

from agents.base import BaseAgent
from agents.executor import ExecutorAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.executor_result import ExecutorResult
from schemas.supervisor_response import SupervisorResponse

_factory = LLMFactory()


class SupervisorAgent(BaseAgent):
    """Entry point for all user requests.

    Makes one decision: does this request require tool use, or can it be
    answered directly? If tool use is needed, delegates the full request to
    a fresh ExecutorAgent via delegate_to_executor.

    Never decides which tool, which service, or which action to take.
    Never resolves user identity — AgentDeps arrives fully populated.
    """

    def __init__(self) -> None:
        super().__init__(name="supervisor")

        # Build the agent with NO tools= argument.
        # delegate_to_executor is registered below via @agent.tool.
        # log_decision has been removed — see Section 10.
        agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        @agent.tool
        async def delegate_to_executor(
            ctx: RunContext[AgentDeps], sub_task: str
        ) -> ExecutorResult:
            """Delegate any request that requires taking an action to the Executor.

            Use this tool whenever the user wants something done. Do not use
            for general conversation or questions answerable directly.

            Pass the full user request as sub_task. Do not summarise, filter,
            or decide what kind of action is needed — the Executor determines
            that from the tools it can see. Include every detail the user provided.

            Args:
                sub_task: Complete description of what the user wants done.
                          The Executor sees only this string.
            """
            logger.info(
                "SupervisorAgent | tool=delegate_to_executor | user=%s | sub_task=%r",
                ctx.deps.user_id, sub_task,
            )
            # Fresh ExecutorAgent per request — MCP server bound to user_email
            # at construction time. All calls on this instance act on that
            # user's Google account.
            executor = ExecutorAgent(ctx.deps.user_email)
            return await executor.run(sub_task, ctx.deps)

        self._agent = agent
        # Conversation history persists across turns within one session.
        # Cleared when SupervisorAgent is re-instantiated (i.e. on app restart).
        self._history: list = []

    def _build_system_prompt(self) -> str:
        return (
            "You are a personal assistant. You have one specialist tool: "
            "delegate_to_executor.\n\n"
            "When to delegate:\n"
            "- The user wants something done — any action involving their data, "
            "services, or accounts → delegate_to_executor.\n"
            "- Pass the full request as-is. Do not decide what kind of action "
            "it is or which service it involves. The Executor handles that.\n\n"
            "When NOT to delegate:\n"
            "- General conversation, greetings, or questions you can answer "
            "directly → respond without calling any tool.\n\n"
            "After the Executor returns:\n"
            "- Use result.summary to compose a natural, conversational message.\n"
            "- If result.missing_info is set, relay that question to the user "
            "and set requires_followup=True.\n"
            "- If all actions completed, set requires_followup=False.\n"
            "- Do not repeat the summary verbatim. Rewrite for tone."
        )

    @staticmethod
    def _log_messages(user_id: str, messages: list[Any]) -> None:
        """Log supervisor-level tool calls (i.e. delegate_to_executor calls).

        Same pattern as ExecutorAgent._log_messages. Logs only what the
        Supervisor's LLM called — not the Executor's internal tool calls,
        which are logged by ExecutorAgent separately.
        """
        for msg in messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        logger.warning(
                            "### SupervisorAgent.tool_call | user=%s | tool=%s",
                            user_id, part.tool_name,
                        )

    async def run(self, user_input: str, deps: AgentDeps) -> SupervisorResponse:
        logger.critical(
            "SupervisorAgent.run | user=%s | email=%s | input=%r",
            deps.user_id, deps.user_email, user_input,
        )

        result = await self._agent.run(
            user_prompt=user_input,
            deps=deps,
            message_history=self._history,
        )
        # Persist history for the next turn in this session
        self._history = result.all_messages()

        # Log supervisor tool calls (delegate_to_executor calls)
        self._log_messages(deps.user_id, result.all_messages())

        # Log token usage for the supervisor run.
        # Note: this does NOT include tokens consumed by the Executor —
        # those are logged separately in ExecutorAgent.run().
        usage = result.usage
        logger.critical(
            "SupervisorAgent.usage | user=%s | input=%s | output=%s | total=%s",
            deps.user_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )

        output: SupervisorResponse = result.output
        logger.info(
            "SupervisorAgent.result | user=%s | requires_followup=%r | message=%r",
            deps.user_id, output.requires_followup, output.message,
        )
        return output