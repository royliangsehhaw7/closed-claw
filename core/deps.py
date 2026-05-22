# from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentDeps:
    user_id: str
    session_history: list[dict[str, str]] = field(default_factory=list)

    # Wired in Stage 3
    redis_client: Any | None = None
    sqlite_conn: Any | None = None

    # Shared state across agents in a single request
    blackboard: Any | None = None