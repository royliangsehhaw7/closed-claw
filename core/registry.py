from __future__ import annotations

import importlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentRegistration:
    """Metadata for one specialist agent.

    description  — shown verbatim in the Supervisor's system prompt.
                   Write it as a capability statement: what this agent
                   can do, phrased so an LLM can match it to a user request.
    services     — MCP service names passed to google_workspace_server().
                   For non-Google MCP servers, wire the server inside
                   agent_class instead and leave this empty.
    owns         — one-line summary of what this specialist handles.
                   Injected into the specialist's system prompt.
    agent_class  — dotted import path to a hand-written agent class.
                   None means use SpecialistAgent (the common case).
                   Set this only when custom logic is required.
    """
    description: str
    services: list[str] = field(default_factory=list)
    owns: str = ""
    agent_class: str | None = None


# ── Registry ──────────────────────────────────────────────────────────────────
#
# Keys are the specialist_keys the Supervisor passes to delegate_to_specialists.
# Each key must match exactly one AgentRegistration.
#
# To add a new MCP-based agent:
#   1. Add one entry here. Done.
#
# To add an agent with custom logic:
#   1. Create agents/<name>_agent.py extending BaseAgent.
#   2. Add one entry here with agent_class="agents.<name>_agent.<ClassName>".
#
AGENT_REGISTRY: dict[str, AgentRegistration] = {
    "tasks": AgentRegistration(
        description=(
            "Google Tasks — list pending tasks, create tasks, mark tasks complete, "
            "update due dates. Use for any request about the user's task list."
        ),
        services=["tasks"],
        owns="Google Tasks — task creation, listing, completion, due date updates.",
    ),
    "calendar": AgentRegistration(
        description=(
            "Google Calendar — list upcoming events, create calendar events, "
            "check availability. Use whenever a request involves dates, times, "
            "deadlines, or scheduling. Always include when creating a task with "
            "a due date."
        ),
        services=["calendar"],
        owns="Google Calendar — event creation, listing, availability checks.",
    ),
    "email": AgentRegistration(
        description=(
            "Gmail — send emails, read inbox, search messages. Use for any "
            "request that involves sending or reading email."
        ),
        services=["gmail"],
        owns="Gmail — sending email, reading inbox, searching messages.",
    ),
}


def build_registry_prompt() -> str:
    """Return a formatted string describing all registered specialists.

    Injected into the Supervisor's system prompt at startup. When a new
    entry is added to AGENT_REGISTRY, it automatically appears here.
    """
    lines = ["Available specialists (use specialist_keys to select):"]
    for key, reg in AGENT_REGISTRY.items():
        lines.append(f'  "{key}": {reg.description}')
        
    return "\n".join(lines)


def build_specialist(key: str, user_email: str) -> object:
    """Instantiate the right agent for the given registry key.

    If the registration has agent_class set, that class is imported and
    instantiated with user_email. Otherwise SpecialistAgent is used.

    This is the only place in the codebase that decides which class to use.
    The Supervisor and delegation tool never import agent classes directly.
    """
    reg = AGENT_REGISTRY[key]

    if reg.agent_class is not None:
        # Hand-written class — import and instantiate
        module_path, class_name = reg.agent_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(user_email)

    # Generic case — build SpecialistAgent from registry entry
    from agents.specialist import SpecialistAgent
    return SpecialistAgent(key=key, registration=reg, user_email=user_email)