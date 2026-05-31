import os
from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart
from core.deps import AgentDeps
from schemas.specialist_result import SpecialistResult
from tools.personal_note_tools import save_as_txt
from core.llm_factory import LLMFactory

_factory = LLMFactory()

class PersonalNoteAgent:
    def __init__(self, key: str, registration, user_email=None):
        print(f"!!! CRITICAL: LOADING AGENT FROM: {__file__}")
        self._registration = registration
        self.agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),            
            system_prompt=f"You are a note-taking assistant. {registration.system_instructions}",
            deps_type=AgentDeps,
            tools=[save_as_txt],
            output_type=str  # Corrected: output_type instead of result_type            
        )

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        result = await self.agent.run(sub_task, deps=deps)
        
        tool_called = any(
            isinstance(part, ToolCallPart)
            for msg in result.all_messages()
            for part in msg.parts
        )
        
        return SpecialistResult(
            summary=result.output, 
            actions_taken=[f"Tool called: {tool_called}"]
        )