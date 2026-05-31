from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentRegistration:
    """The clean interface layer consumed directly by specialist.py and supervisor.py."""
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""

    # This will hold everything below the metadata '---'
    system_instructions: str = ""

    # Defaults allow older SKILL.md files to load without crashing
    agent_class: str = "SpecialistAgent"
    module_path: str = "agents.specialist"    