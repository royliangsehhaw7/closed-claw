from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic_ai import Agent

from core.logger import logger


class BaseAgent(ABC):
    """All agents inherit from this class.

    Responsibilities:
    - Loads its persona from memory/agents/<name>.md at construction time.
    - Wraps pydantic-ai Agent.
    - Enforces a consistent run() interface across all agents.
    """

    def __init__(self, name: str) -> None:   # agent no longer passed in here
        self._name = name
        self._persona = self._load_persona()  # safe — self._name exists
        self._agent: Agent | None = None      # set by subclass after super().__init__
        logger.debug("BaseAgent | %s initialised", self._name)
        
    @property
    def name(self) -> str:
        return self._name

    def _load_persona(self) -> str:
        """Load system prompt from memory/agents/<name>.md.

        Returns empty string if the file does not exist — agent falls
        back to its hardcoded instruction string.
        """
        memory_dir = os.getenv("MEMORY_DIR", "memory/")
        path = Path(memory_dir) / "agents" / f"{self._name}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.debug("BaseAgent | persona loaded from %s", path)
            return content
        logger.warning("BaseAgent | no persona file found at %s", path)
        return ""

    @abstractmethod
    async def run(self, user_input: str, deps: object) -> str:
        """Run the agent and return a plain text response."""
        ...