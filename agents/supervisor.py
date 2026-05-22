from __future__ import annotations

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger

_factory = LLMFactory()


class SupervisorAgent(BaseAgent):
    """Entry point for all user requests.

    Stage 1a: responds directly, no delegation.
    Stage 1c: classifies intent and delegates to Concierge or Comms.
    """

    def __init__(self) -> None:
        # Build the agent AFTER super().__init__ so self._persona is available
        super().__init__(name="supervisor")          # persona loaded here
        agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),  # safe to call now
        )
        self._agent = agent
        self._history = []


    def _build_system_prompt(self) -> str:
        base = (f"""
                You are a personal assistant.
                You help the user manage their tasks, calendar, and email.
                Be concise and helpful.
            """
        )
        return f"{base}\n\n{self._persona}".strip() if self._persona else base

    async def run(self, user_input: str, deps: AgentDeps) -> str:
        logger.info("SupervisorAgent.run | user=%s | input=%r", deps.user_id, user_input)

        result = await self._agent.run(
            user_prompt=user_input,
            deps=deps,
            message_history=self._history
        )
        # 2. Update your local history with the NEW messages
        # result.new_messages contains only the messages added in this turn
        self._history = result.all_messages()
        
        response = result.output
        logger.info(f"""
            SupervisorAgent.run | response= {response}
            Thinking : {str(result.response.thinking).strip()}
        """)

        return response