from __future__ import annotations

import os
from datetime import date
from typing import Any

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.agent_registration import AgentRegistration
from mcps.mcp_pool import get_pool_server
from schemas.specialist_result import SpecialistResult

_factory = LLMFactory()


class SpecialistAgent(BaseAgent):

    def __init__(self, key: str, registration: AgentRegistration, user_email: str) -> None:
        super().__init__(name=key)
        self._key = key
        self._user_email = user_email

        server = get_pool_server(registration, user_email)
        toolsets = [server] if server is not None else []

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            toolsets=toolsets,
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Validation First: BEFORE calling any tool, verify the request provides all parameters necessary for your domain-specific tools to perform a deterministic action.
            3. Ambiguity & Missing Information:
            - If the request is vague, speculative, or lacks the precise details required for tool invocation, DO NOT attempt to interpret or resolve the intent.
            - If you cannot extract a 100% clear instruction mapping to a specific tool, DO NOT call any tools.
            - If any required parameter is missing, DO NOT call any tools.
            - IMMEDIATELY populate 'missing_info' with a clear request for the specific missing item and return.
            4. Execution: Only call tools if you have 100% of the required parameters.
            5. Output: Log one actions_taken entry per tool call. Provide a concise summary of results.
        """

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
                        logger.warning(
                            "RAW_TOOL_DEBUG | tool=%s | raw_content=%s",
                            part.tool_name, part.content,
                        )
                        logger.debug(
                            "SpecialistAgent[%s].tool_result | tool=%s | content=%r",
                            self._key, part.tool_name, part.content,
                        )

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "SpecialistAgent[%s].run | user=%s | email=%s | sub_task=%r",
            self._key, deps.user_id, self._user_email, sub_task,
        )

        result = await self._agent.run(
            user_prompt=sub_task,
            deps=deps,
            usage_limits=UsageLimits(request_limit=None),
        )

        self._log_messages(result.all_messages())

        usage = result.usage
        logger.warning(
            "SpecialistAgent[%s].usage | user=%s | input=%s | output=%s | total=%s",
            self._key, deps.user_id,
            usage.input_tokens, usage.output_tokens, usage.total_tokens,
        )

        output: SpecialistResult = result.output
        logger.warning(
            "SpecialistAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output