from dataclasses import dataclass, field
from typing import List

@dataclass
class AgentRegistration:
    """
    Unified Data Contract for Agent Configurations.
    Maintains a 12-field memory structure even if older SKILL.md files 
    only define 8 fields, ensuring strict backwards compatibility.
    """
    # --- Stage 3a Core Identity Fields ---
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""
    system_instructions: str = ""
    agent_class: str = "SpecialistAgent"
    module_path: str = "agents.specialist"

    # --- Polymorphic MCP Configuration Routing Overlays ---
    # Allowed routing targets: 'google', 'stdio', or 'none'
    server_type: str = "google"  
    
    # Executable definition for standard I/O isolation (e.g., 'uvx')
    mcp_command: str = ""
    
    # Subprocess execution flags and initialization tokens
    mcp_args: List[str] = field(default_factory=list)
    
    # White-listed environment variables extracted from host OS for data privacy
    mcp_env_keys: List[str] = field(default_factory=list)