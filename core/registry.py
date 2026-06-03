from __future__ import annotations

import yaml
import importlib
from pathlib import Path
from typing import Dict
from dataclasses import dataclass
from agents.protocol import SpecialistProtocol

from core.logger import logger
from schemas.agent_registration import AgentRegistration

class AgentRegistry:
    """Encapsulates the state and logic for available specialist agents."""
    
    # def __init__(self):
    #     self._agents: Dict[str, AgentRegistration] = {}
    
    # =============== S I N G L E T O N ==============#
    # 1. Hold the single private instance at the class level
    # 1. Declare the type at the class level (like a C# property)
    _instance: AgentRegistry | None = None
    _agents: Dict[str, AgentRegistration]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentRegistry, cls).__new__(cls)            
            # 2. Assign the value WITHOUT the inline type hint
            cls._instance._agents = {}
            
        return cls._instance
    

    def load_from_disk(self, skills_dir: str = "skills") -> None:
        """Clears and re-reads all SKILLS.md file targets from disk."""
        self._agents.clear()

        skills_path = Path(skills_dir)
        if not skills_path.exists():
            logger.warning("registry | target directory not found: %s", skills_dir)
            return

        for file_path in skills_path.glob("**/SKILL.md"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.startswith("---"):
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue

                meta = yaml.safe_load(parts[1]) or {}
                # --- NEW: Skip if explicitly marked as not available ---
                if meta.get("available", True) is False:
                    logger.debug("registry | skipping unavailable skill at %s", file_path)
                    continue


                key = meta.get("key")
                name = meta.get("name")

                if not key or not name:
                    continue

                # Get values, defaulting to standard agents if missing/empty
                raw_module = meta.get("module_path")
                module_path = raw_module if (raw_module and raw_module.strip()) else "agents.specialist"

                raw_class = meta.get("agent_class")
                agent_class = raw_class if (raw_class and raw_class.strip()) else "SpecialistAgent"

                self._agents[key] = AgentRegistration(
                    key=key,
                    name=name,
                    services=meta.get("services", []),
                    owns=meta.get("owns", ""),
                    description=meta.get("description", ""),
                    system_instructions=parts[2].strip(),
                    agent_class=agent_class,
                    module_path=module_path,
                    server_type=meta.get("server_type", "google"),
                    available=meta.get("available", False)
                )               
                logger.info("registry | compiled skill configuration target: %s", key)

            except Exception as e:
                logger.error("registry | structural parse failure at %s | error=%s", file_path, e)

    def get(self, key: str) -> AgentRegistration | None:
        """Safely retrieves an agent registration by key."""
        return self._agents.get(key)

    def has_specialist(self, key: str) -> bool:
        """Checks if a specialist exists in the registry."""
        return key in self._agents

    def build_prompt(self) -> str:
        """Compiles the dynamic layout string for injection into the supervisor prompt."""
        if not self._agents:
            return "Available Specialists:\n- None configured."

        lines = ["Available Specialists:"]
        for key, reg in self._agents.items():
            lines.append(f"- [{key}]: {reg.name} -> {reg.description} (Owns: {reg.owns})")
        return "\n".join(lines)

    def build_specialist(self, key: str, user_email: str) -> SpecialistProtocol:
        registration = self.get(key)
        if not registration:
            raise ValueError(f"Agent '{key}' missing.")

        # 1. Dynamic Import
        module = importlib.import_module(registration.module_path)
        agent_cls = getattr(module, registration.agent_class)
        
        # 2. Every agent is guaranteed to accept these two arguments
        # If an agent doesn't need user_email, it simply ignores it in __init__
        return agent_cls(key=key,registration=registration, user_email=user_email)

    # # core/registry.py

    # def build_specialist(self, key: str, user_email: str) -> SpecialistProtocol:
    #         registration = self.get(key)
    #         if not registration:
    #             raise ValueError(f"Agent '{key}' missing.")

    #         # 1. Dynamic Import
    #         module = importlib.import_module(registration.module_path)
    #         agent_cls = getattr(module, registration.agent_class)
            
    #         # --- FIX: ADD YOUR AGENT TO THIS LIST ---
    #         # If your agent ONLY takes 'registration' in __init__, add it here.
    #         registration_only_agents = {"RemindersAgent", "PersonalNoteAgent"}
            
    #         if registration.agent_class in registration_only_agents:
    #             # This instantiates it correctly without the extra arguments
    #             return agent_cls(registration=registration)
            
    #         # Default behavior for standard MCP agents (SpecialistAgent)
    #         return agent_cls(key=key, registration=registration, user_email=user_email)
