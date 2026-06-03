from __future__ import annotations

import os

from pydantic_ai import Agent, RunContext, UsageLimits

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistry
from schemas.specialist_result import SpecialistResult
from schemas.supervisor_response import SupervisorResponse

_factory = LLMFactory()


class SupervisorAgent(BaseAgent):

    def __init__(self) -> None:
        super().__init__(name="supervisor")

        self._registry = AgentRegistry()
        self._registry.load_from_disk(skills_dir="skills")

        self.agent = Agent(
            model=_factory.get_model(os.getenv("SUPERVISOR_MODEL")),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        self.agent.tool(self.delegate_to_specialists)

    def _build_system_prompt(self) -> str:
        registry_manifest = self._registry.build_prompt()
        return f"""
            You are the entry point for all user requests.
            Your responsibility is to map user intent to the available specialists.

            {registry_manifest}

            CRITICAL CONSTRAINT: The Available Specialists list above is the ONLY source
            of truth for what this system can do. You MUST NOT delegate to any key that
            does not appear verbatim in that list. Do not infer, guess, or assume that a
            capability exists because it is common or logical. If it is not listed, it does
            not exist in this system.

            Guidelines:
            1. Analyze user intent first.
            2. If the intent maps to a specialist key that EXISTS in the list above,
               call 'delegate_to_specialists' with that exact key.
            3. If the user's intent is ambiguous or conversational, DO NOT delegate.
               Set 'requires_followup' to True and ask the user to clarify.
            4. Never attempt to resolve credentials or call MCP platforms directly.

            [FLOW CONTROL RULES]
            - CASE A: If the request is ambiguous or missing required detail:
              * DO NOT delegate.
              * Set 'requires_followup' = True.
              * Populate 'message' asking for the missing information.

            - CASE B: If a specialist returns a successful summary, YOU ARE FINISHED.
              * Set 'requires_followup' = False.
              * Summarize the outcome in 'message'.

            - CASE C: If the user's intent is clear but NO specialist in the list above
              covers it:
              * DO NOT delegate. DO NOT fabricate an answer from memory.
              * Set 'requires_followup' = False.
              * Set 'message' to inform the user that capability is not available,
                e.g. "I don't have access to a calendar tool right now."
        """

    async def run(
        self,
        user_prompt: str,
        deps: AgentDeps,
        message_history: list | None = None,
    ) -> tuple[SupervisorResponse, list]:
        logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
        logger.warning("SupervisorAgent.run | BEFORE agent.run")   # ADD THIS
        result = await self.agent.run(
            user_prompt,
            deps=deps,
            message_history=message_history or [],
            usage_limits=UsageLimits(request_limit=None),
        )
        logger.warning("SupervisorAgent.run | AFTER agent.run")    # ADD THIS
        logger.warning("SupervisorAgent reply: %s", result.output)
        return result.output, result.all_messages()

    async def delegate_to_specialists(
        self,
        ctx: RunContext[AgentDeps],
        specialist_keys: list[str],
        sub_tasks: list[str],
    ) -> list[SpecialistResult]:
        """Executes sequential handoffs to the dynamically verified disk specialists."""
        results: list[SpecialistResult] = []

        logger.warning("delegate_to_specialists | CALLED | keys=%s", specialist_keys)

        for key, sub_task in zip(specialist_keys, sub_tasks):
            if not self._registry.has_specialist(key):
                logger.error("SupervisorAgent | validation failed | unknown specialist key: %s", key)
                results.append(SpecialistResult(
                    actions_taken=[],
                    summary=f"Specialist '{key}' is not available in this configuration.",
                    missing_info=f"No specialist registered for key '{key}'. Do not retry this key.",
                ))
                continue

            logger.warning(
                "SupervisorAgent | delegating control | specialist=%s | task=%r", key, sub_task
            )

            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            res = await specialist.run(sub_task, deps=ctx.deps)
            results.append(res)

        return results