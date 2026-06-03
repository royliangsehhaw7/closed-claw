from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentRegistration:
    """
    Unified data contract for agent configurations.
    All fields map directly to SKILL.md frontmatter keys.
    """
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""
    system_instructions: str = ""
    agent_class: str = "SpecialistAgent"
    module_path: str = "agents.specialist"
    server_type: str = "google"         # "google_remote" | "stdio" | "none"
    mcp_command: str = ""
    mcp_args: List[str] = field(default_factory=list)
    mcp_env_keys: List[str] = field(default_factory=list)

    # a flag to load agent or to skip
    available: bool = False