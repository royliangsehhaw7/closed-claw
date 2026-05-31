from typing import Protocol, runtime_checkable
from schemas.specialist_result import SpecialistResult
from core.deps import AgentDeps

@runtime_checkable
class SpecialistProtocol(Protocol):
    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        ...