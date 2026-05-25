from __future__ import annotations

from pydantic_ai import Agent, RunContext

from agents.base import BaseAgent
from agents.executor_pool import ExecutorPool
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
    the correct ExecutorAgent via the pool.

    Never decides which tool, which service, or which action to take.
    Never resolves user identity — AgentDeps arrives fully populated.

    Stage 1c: pool has one entry, loaded from .env by main.py.
    Stage 2+: pool grows as users authenticate. No code changes here.
    """

    def __init__(self, executor_pool: ExecutorPool) -> None:
        super().__init__(name="supervisor")

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
            executor = executor_pool.get(ctx.deps.user_email)
            return await executor.run(sub_task, ctx.deps)

        self._agent = agent
        self._history = []

    def _build_system_prompt(self) -> str:
        base = (
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
        return f"{base}\n\n{self._persona}".strip() if self._persona else base

    async def run(self, user_input: str, deps: AgentDeps) -> SupervisorResponse:
        logger.info(
            "SupervisorAgent.run | user=%s | email=%s | input=%r",
            deps.user_id, deps.user_email, user_input,
        )

        result = await self._agent.run(
            user_prompt=user_input,
            deps=deps,
            message_history=self._history,
        )
        self._history = result.all_messages()

        output: SupervisorResponse = result.output
        logger.info(
            "SupervisorAgent.run | user=%s | requires_followup=%r | message=%r",
            deps.user_id, output.requires_followup, output.message,
        )
        return output