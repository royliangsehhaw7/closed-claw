from __future__ import annotations

import os
from typing import Any, List

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart

from agents.base import BaseAgent

from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistry

from schemas.specialist_result import SpecialistResult
from schemas.supervisor_response import SupervisorResponse


_factory = LLMFactory()


class SupervisorAgent(BaseAgent):
    """
    Entry point for all user requests.

    Makes two decisions:
    1. Does this request require tool use, or can it be answered directly?
    2. If tool use is needed, which specialists should handle it?
    """

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
            Your responsibility is to map user intent to specialist tools.

            {registry_manifest}

            Guidelines:
            1. Analyze user intent first.
            2. If a specific tool is required, select the specialist key and use 'delegate_to_specialists'.
            3. If the user's intent is ambiguous, conversational, or does not clearly map to any registered specialist:
               - DO NOT delegate.
               - Set 'requires_followup' to True.
               - Populate 'message' with a response that asks the user to clarify their intent.
            4. Never attempt to resolve credentials or call MCP platforms directly.

            [FLOW CONTROL RULES]
            - CASE A: If the request is unresolvable or 'missing_info' is returned, YOU ARE NOT FINISHED.
              * Set 'requires_followup' = True.
              * Draft a 'message' that clarifies the ambiguity.
            
            - CASE B: If a specialist execution returns a successful summary, YOU ARE FINISHED.
              * Set 'requires_followup' = False.
              * Summarize the outcome in the 'message' field.
        """
        
        # return f"""
        #     You are the entry point for all user requests.
        #     Your primary responsibility is to isolate the user's intent for each specialist. When delegating, 
        #     you must pass ONLY the specific sub-task relevant to that specialist's domain. 
        #     Extract and refine the instructions for each specialist so they contain exactly the information 
        #     required for their specific toolset."
            
        #     {registry_manifest}

        #     Guidelines:
        #     1. Determine if the user's request requires tool actions or can be answered directly.
        #     2. If tool execution is required, select the correct specialist keys and delegate via 
        #     'delegate_to_specialists'. The sub_task for each specialist MUST be the user's original 
        #     request verbatim. Do not rephrase, summarise, or extract from it.            
        #     3. Never attempt to resolve user credentials or call MCP platforms directly.

        #     [FLOW CONTROL RULES]
        #     - CASE A: If a specialist execution returns 'missing_info', YOU ARE NOT FINISHED.
        #       * You must set 'requires_followup' = True.
        #       * You must draft a 'message' that explicitly asks the user for the specific missing information.
            
        #     - CASE B: If a specialist execution returns a successful summary and actions, YOU ARE FINISHED.
        #       * You must set 'requires_followup' = False.
        #       * You must cleanly summarize what was accomplished in your final response 'message' field.
        #       * DO NOT call 'delegate_to_specialists' again for the same task once confirmed.
        # """

    async def run(self, user_prompt: str, deps: AgentDeps, message_history: list | None = None) -> tuple[SupervisorResponse, list]:
        result = await self.agent.run(user_prompt, deps=deps, message_history=message_history or [])
        logger.warning("SupervisorAgent reply: %s", result.output)
 
        return result.output, result.all_messages()

    async def delegate_to_specialists(
        self, 
        ctx: RunContext[AgentDeps], 
        specialist_keys: list[str], 
        sub_tasks: list[str]
    ) -> list[SpecialistResult]:

        """Executes sequential handoffs to the dynamically verified disk specialists."""
        results: list[SpecialistResult] = []

        for key, sub_task in zip(specialist_keys, sub_tasks):
            if not self._registry.has_specialist(key):
                logger.error("SupervisorAgent | validation failed | unknown specialist key: %s", key)
                continue

            logger.warning("SupervisorAgent | delegating control | specialist=%s | task=%r", key, sub_task)
            
            # Instantiates specific or generic specialist based on registration metadata configuration
            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            
            res = await specialist.run(sub_task, deps=ctx.deps)
            results.append(res)

        return results



    # def _format_specialist_results(self, results: list[SpecialistResult]) -> str:
        if not results:
            return "No specialists returned results."

        if len(results) == 1:
            r = results[0]
            parts = [f"Summary: {r.summary}"]
            if r.actions_taken:
                parts.append("Actions taken:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            if r.missing_info:
                parts.append(f"Missing info: {r.missing_info}")
            return "\n".join(parts)

        blocks = []
        for i, r in enumerate(results, start=1):
            lines = [f"[Specialist {i}] Summary: {r.summary}"]
            if r.actions_taken:
                lines.append("Actions:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            if r.missing_info:
                lines.append(f"Missing info: {r.missing_info}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)