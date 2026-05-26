from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AGENT_REGISTRY, build_registry_prompt, build_specialist
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

        agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        @agent.tool
        async def delegate_to_specialists( 
            ctx: RunContext[AgentDeps],
            sub_task: str,
            specialist_keys: list[str],
        ) -> str:
            """Delegate a request to one or more specialist agents.

            Use this tool whenever the user wants something done. Do not use for general conversation or 
            questions answerable directly.

            Select specialist_keys from the registry. For simple requests, one key is enough. 
            For cross-service requests, pass all keys that apply — each specialist will handle its own domain.

            The full sub_task string is passed to every specialist. Include every detail the user provided. 
            Do not filter or summarise.

            Args:
                sub_task:         Complete description of what the user wants done.
                specialist_keys:  One or more keys from the specialist registry.
                                  Must be non-empty. Example: ["tasks", "calendar"]
            """
            logger.info(
                "SupervisorAgent | tool=delegate_to_specialists | user=%s | keys=%r | sub_task=%r",
                ctx.deps.user_id, specialist_keys, sub_task,
            )

            # Validate all keys before instantiating anything
            unknown = [k for k in specialist_keys if k not in AGENT_REGISTRY]
            if unknown:
                logger.warning(
                    "SupervisorAgent | unknown specialist_keys=%r | user=%s", unknown, ctx.deps.user_id
                )
                specialist_keys = [k for k in specialist_keys if k in AGENT_REGISTRY]

            if not specialist_keys:
                return "No valid specialist keys provided. Cannot delegate."

            # Instantiate and run each specialist sequentially.
            # Sequential keeps logs readable and avoids MCP subprocess races.
            # Parallelism can be added in a later stage if latency demands it.
            results: list[SpecialistResult] = []
            for key in specialist_keys:
                specialist = build_specialist(key, ctx.deps.user_email)
                result = await specialist.run(sub_task, ctx.deps)
                results.append(result)

            return self._merge_results(results)

        self._agent = agent
        self._history: list = []

    def _build_system_prompt(self) -> str:
        registry_block = build_registry_prompt()
        return (f"""
            You are a personal assistant. You have one tool: delegate_to_specialists.
        
            {registry_block}

            When to delegate:
                - The user wants something done — any action involving their data,
                  services, or accounts → delegate_to_specialists.
                - Select specialist_keys based on the registry descriptions above.
                - For a task with a due date, always include both 'tasks' and 'calendar' 
                — a matching calendar event should always be created.
                - Pass the full request as sub_task. Include every detail. Do not filter or summarise.
                - When unsure which specialists apply, include all that could plausibly be needed.

            When NOT to delegate:
                - General conversation, greetings, or questions you can answer directly → respond without calling any tool.

            After specialists return:
                - Use the merged summary to compose a natural, conversational message.
                - If any specialist set missing_info, relay that question to the user and set requires_followup=True.
                - If all actions completed, set requires_followup=False.
                - Do not repeat summaries verbatim. Rewrite for tone.
            """
        )

    @staticmethod
    def _log_messages(user_id: str, messages: list[Any]) -> None:
        for msg in messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        logger.debug(
                            "SupervisorAgent.tool_call | user=%s | tool=%s",
                            user_id, part.tool_name,
                        )

    async def run(self, user_input: str, deps: AgentDeps) -> SupervisorResponse:
        logger.warning(
            "SupervisorAgent.run | user=%s | email=%s | input=%r",
            deps.user_id, deps.user_email, user_input,
        )

        result = await self._agent.run(
            user_prompt=user_input,
            deps=deps,
            message_history=self._history,
        )
        self._history = result.all_messages()

        self._log_messages(deps.user_id, result.all_messages())

        usage = result.usage
        logger.warning(
            "SupervisorAgent.usage | user=%s | input=%s | output=%s | total=%s",
            deps.user_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
        output: SupervisorResponse = result.output

        logger.warning(
            "SupervisorAgent.result | user=%s | requires_followup=%r | message=%r",
            deps.user_id, output.requires_followup, output.message,
        )
        return output


    def _merge_results(self, results: list[SpecialistResult]) -> str:
        """Merge one or more SpecialistResults into a single string for the Supervisor LLM.

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

        # Multiple specialists — label each block
        blocks = []
        all_missing: list[str] = []
        for i, r in enumerate(results, start=1):
            lines = [f"[Specialist {i}] Summary: {r.summary}"]
            if r.actions_taken:
                lines.append("Actions:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            if r.missing_info:
                all_missing.append(r.missing_info)
            blocks.append("\n".join(lines))

        merged = "\n\n".join(blocks)
        if all_missing:
            merged += "\n\nMissing info (ask user): " + "; ".join(all_missing)
        return merged