from __future__ import annotations
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """All agents inherit from this class."""

    # def __init__(self, name: str) -> None:
    #     self._name = name
    def __init__(self, name) -> None:
        self._name = name
            
    @abstractmethod
    async def run(self, user_input: str, deps: object, *args, **kwargs) -> object:
        """Run the agent and return its structured output schema."""
        ...