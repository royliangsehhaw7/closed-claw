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

    The Supervisor reads the registry at startup. Its system prompt always reflects exactly what 
    specialists are available. Adding a new specialist to the registry is immediately visible 
    to the Supervisor — no code changes here.

    Never resolves user identity — AgentDeps arrives fully populated.
    Never calls MCP tools directly — that is the specialists' job.
    """

    def __init__(self) -> None:
        super().__init__(name="supervisor")

        # EXPLICIT STEP: Re-scan the skills directory straight from disk on initialization
        self._registry = AgentRegistry()

        self._registry.load_from_disk(skills_dir="skills")

        # Retained your precise framework keywords: output_type and deps_type
        self.agent = Agent(
            model=_factory.get_model(os.getenv("SUPERVISOR_MODEL")),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        # Register the delegation tool explicitly
        self.agent.tool(self.delegate_to_specialists)

    def _build_system_prompt(self) -> str:
        """Dynamically pulls the instructions straight out of the loaded registry map."""
        registry_manifest = self._registry.build_prompt()
        
        return f"""
            You are the entry point for all user requests.
            Your system prompt always reflects exactly what specialists are available on disk.

            {registry_manifest}

            Guidelines:
            1. Determine if the user's request requires tool actions or can be answered directly.
            2. If tool execution is required, select the correct specialist keys and delegate tasks.
            3. Never attempt to resolve user credentials or call MCP platforms directly.
        """

    async def run(self, user_prompt: str, deps: AgentDeps) -> SupervisorResponse:
        logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
        result = await self.agent.run(user_prompt, deps=deps)

        return result.output

    async def delegate_to_specialists(
        self, 
        ctx: RunContext[AgentDeps], 
        specialist_keys: list[str], 
        sub_tasks: list[str]
    ) -> str:
        """Executes sequential handoffs to the dynamically verified disk specialists."""
        results: list[SpecialistResult] = []

        for key, sub_task in zip(specialist_keys, sub_tasks):
            if not self._registry.has_specialist(key):
                logger.error("SupervisorAgent | validation failed | unknown specialist key: %s", key)
                continue

            logger.warning("SupervisorAgent | delegating control | specialist=%s | task=%r", key, sub_task)
            
            # Build the specialist instance explicitly using the verified registry row
            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            
            # Direct execution pass down to the target specialist loop
            res = await specialist.run(sub_task, deps=ctx.deps)
            results.append(res)

        return self._format_specialist_results(results)

    def _format_specialist_results(self, results: list[SpecialistResult]) -> str:
        """
        The Supervisor's LLM receives this string as the tool return value.
        It uses the merged summary to compose the final user-facing message.

        Format:
        - Single result: return summary + actions directly.
        - Multiple results: prefix each block with the specialist index so the
          Supervisor can tell which actions came from which specialist.
        """
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

        # Multiple specialists — label each block cleanly
        blocks = []
        for i, r in enumerate(results, start=1):
            lines = [f"[Specialist {i}] Summary: {r.summary}"]
            if r.actions_taken:
                lines.append("Actions:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)