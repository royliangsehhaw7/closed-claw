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
        
        # return f"""
        #     You are the entry point for all user requests.
        #     Your system prompt always reflects exactly what specialists are available on disk.

        #     {registry_manifest}

        #     Guidelines:
        #     - Determine if the user's request requires tool actions or can be answered directly.
        #     - If tool execution is required, select the correct specialist keys and delegate tasks.
        #     - Never attempt to resolve user credentials or call MCP platforms directly.

        #     REPAIR PROTOCOL:
        #     - If a user flags a previous action as incorrect (e.g., wrong recipient, wrong task), you must:
        #     - Retrieve the context of the last executed action.
        #     - Re-evaluate the parameters (like email address or target list) based on the correction.
        #     - Re-delegate the same task to the same specialist with the corrected parameters.
        #     - Do not treat corrections as mere conversation.

        #     COMMUNICATION PROTOCOL:
        #     - When the tool 'delegate_to_specialists' returns results, you MUST use that information to populate the 'message' field in your final response. 
        #     - Never return an empty 'message' if a specialist has returned data.
        #     - Do not consider the task finished until you have filled the 'message' field with the content derived from the specialists.
            
        #     OUTPUT REQUIREMENTS:
        #     - You are the sole interface for the user.
        #     - You MUST NOT end your execution until you have presented the specialist's findings back to the user in a natural, conversational response.
        #     - If a specialist provides information (like an email summary), you must paraphrase that information in your reply. Do not simply state "I have checked" or "Action completed."                 
        # """
        return f"""
            You are the entry point for all user requests.
            {registry_manifest}

            Guidelines:
            1. Determine if the user's request requires tool actions or can be answered directly.
            2. If tool execution is required, select the correct specialist keys and delegate tasks.
            3. Never attempt to resolve user credentials or call MCP platforms directly.
            4. If a specialist output contains "Missing Info", you MUST set 'requires_followup' to TRUE and ask the user to provide the missing details.

            [FLOW CONTROL RULES]
            - IF a specialist returns 'missing_info', YOU ARE NOT FINISHED.
            - You must set 'requires_followup' = True.
            - You must draft a response that explicitly asks the user for the specific missing information 
            returned by the specialist.            
        """


    async def run(
            self, 
            user_prompt: str, 
            deps: AgentDeps,
            message_history: list | None = None
        ) -> tuple[SupervisorResponse, list]:
        
        logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
        result = await self.agent.run(user_prompt, deps=deps)

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
            
            # Build the specialist instance explicitly using the verified registry row
            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            
            # Direct execution pass down to the target specialist loop
            res = await specialist.run(sub_task, deps=ctx.deps)
            print(f"DEBUG: Specialist returned {len(results)} results")
            results.append(res)

        logger.warning(f"DEBUG: Final results list count: {len(results)}")
        return results
