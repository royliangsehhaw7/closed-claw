import os
from datetime import date
from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from schemas.specialist_result import SpecialistResult
from tools.personal_notes_tools import save_as_txt

_factory = LLMFactory()


class PersonalNoteAgent(BaseAgent):
    """
    Custom specialist agent inheriting from BaseAgent.
    Handles persistent note-taking workflows with direct file system mutations.
    """

    def __init__(self, key: str, registration, user_email: str = None) -> None:
        # 1. Initialize the base agent with the specific registry skill key
        super().__init__(name=key)
        
        print(f"!!! CRITICAL: LOADING AGENT FROM: {__file__}")
        self._registration = registration
        self._key = key
        self._user_email = user_email
        
        # 2. Build the PydanticAI instance with plain text output to prevent tool conflicts.
        # We deliberately omit 'output_type' (defaulting to str) to eliminate the hidden 'final_result' tool.
        self.agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),            
            system_prompt=self._build_system_prompt(registration),
            deps_type=AgentDeps,
            output_type=SpecialistResult,
            tools=[save_as_txt]
        )

    def _build_system_prompt(self, reg) -> str:
        today = date.today().isoformat()
        return f"""
            Today's date is {today}.

            [IDENTITY]
            You are a note-taking assistant. {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Validation First: BEFORE calling any tool, verify you have all required information (such as the note 'content').
            3. Missing Information: If any required parameter is missing, DO NOT call any tools. Populate 'missing_info' with what is needed, 
               set 'summary' to describe what is missing, leave 'actions_taken' empty, and return immediately.
            4. Execution: Only call save_as_txt if you have 100% of the required parameters.
            5. Output: After save_as_txt completes successfully, call final_result with:
                - summary: plain description of what was saved
                - actions_taken: one entry describing the tool call that was made
                - missing_info: null        """

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        result = await self.agent.run(sub_task, deps=deps)
        return result.output  # result.output is already a SpecialistResult — return it directly