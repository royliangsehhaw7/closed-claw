from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict
import yaml

from core.logger import logger

@dataclass
class AgentRegistration:
    """The clean interface layer consumed directly by specialist.py and supervisor.py."""
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""


# Pure, decoupled memory mapping
AGENT_REGISTRY: Dict[str, AgentRegistration] = {}


def load_registry_from_disk(skills_dir: str = "skills") -> None:
    """Explicitly clears and re-reads all SKILLS.md file targets from disk."""
    global AGENT_REGISTRY
    AGENT_REGISTRY.clear()

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
            key = meta.get("key")
            name = meta.get("name")

            if not key or not name:
                continue

            AGENT_REGISTRY[key] = AgentRegistration(
                key=key,
                name=name,
                services=meta.get("services", []),
                owns=meta.get("owns", ""),
                description=meta.get("description", "")
            )
            logger.info("registry | compiled skill configuration target: %s", key)

        except Exception as e:
            logger.error("registry | structural parse failure at %s | error=%s", file_path, e)


def build_registry_prompt() -> str:
    """Compiles the dynamic layout string for injection into the supervisor prompt string."""
    if not AGENT_REGISTRY:
        return "Available Specialists:\n- None configured."

    lines = ["Available Specialists:"]
    for key, reg in AGENT_REGISTRY.items():
        lines.append(f"- [{key}]: {reg.name} -> {reg.description} (Owns: {reg.owns})")
    return "\n".join(lines)


def build_specialist(key: str, user_email: str):
    """Instantiates a stable SpecialistAgent using clean dependency injection."""
    from agents.specialist import SpecialistAgent

    registration = AGENT_REGISTRY.get(key)
    if not registration:
        raise ValueError(f"Specialist agent '{key}' is missing from runtime registry.")

    return SpecialistAgent(key=key, registration=registration, user_email=user_email)