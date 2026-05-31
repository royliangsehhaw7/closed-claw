from __future__ import annotations

import os
from datetime import date
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistration

from mcps.google import google_workspace_server
from mcps.mcp_pool import get_pool_server
from schemas.specialist_result import SpecialistResult

_factory = LLMFactory()


class SpecialistAgent(BaseAgent):
    """
    Generic specialist agent constructed from a registry entry.

    The registry entry supplies everything needed to build a functioning agent:
    - services   → which MCP tools to load (narrow tool surface)
    - owns       → injected into system prompt so the LLM knows its domain

    This class never changes when new agents are added. Only the registry
    entry and (if needed) the MCP server wiring change.

    For agents that require custom logic — non-MCP tools, multi-step workflows,
    unusual error handling — write a dedicated class and set agent_class in the
    registry entry. This class handles the common case.
    """

    def __init__(self, key: str, registration: AgentRegistration, user_email: str) -> None:
        super().__init__(name=key)
        self._key = key
        self._user_email = user_email

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            toolsets=[get_pool_server(registration.services, user_email)],
            retries=3
            # toolsets=[
            #     google_workspace_server(
            #         registration.services,
            #         user_email=user_email,
            #     ),
            # ],
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return (f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Context Isolation: You will receive compound prompts. Mentally isolate and extract ONLY the parameters, dates, and entities that directly pertain to your domain ({reg.owns}). 
            3. Filtering Logic: If input text contains data or constraints irrelevant to your domain (e.g., meeting times when you manage tasks, or email addresses when you manage boards), discard that information entirely. Do not map foreign parameters into your tool arguments.
            4. Execution: Use all tools necessary to complete your domain-specific tasks. Act immediately.
            5. Missing Information: If the instruction lacks critical details specific to YOUR domain, do not guess. Flag the missing parameter clearly and do not call tools.
            6. Validation: Never invent IDs, names, or addresses. Before modifying/completing, search for exact matches. If not found, report what exists and do not act.
            7. Output: Log one actions_taken entry per tool call. Provide a concise summary of results.
        """                
        )

    def _log_messages(self, messages: list[Any]) -> None:
        for msg in messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        logger.debug(
                            "SpecialistAgent[%s].tool_call | tool=%s | args=%r",
                            self._key, part.tool_name, part.args,
                        )
            elif isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        logger.debug(
                            "SpecialistAgent[%s].tool_result | tool=%s | content=%r",
                            self._key, part.tool_name, part.content,
                        )

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "SpecialistAgent[%s].run | user=%s | email=%s | sub_task=%r",
            self._key, deps.user_id, self._user_email, sub_task,
        )

        # async with self._agent: # DONT USE THIS ANYWORE, GETTING FROM POOL
        result = await self._agent.run(
            user_prompt=sub_task,
            deps=deps,
        )

        self._log_messages(result.all_messages())

        usage = result.usage
        logger.warning(
            "SpecialistAgent[%s].usage | user=%s | input=%s | output=%s | total=%s",
            self._key, deps.user_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
        output: SpecialistResult = result.output

        logger.warning(
            "SpecialistAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output