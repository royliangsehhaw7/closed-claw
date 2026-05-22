from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: Wraps the Redis message list for a single user (Stage 3).
# SessionMessage is one turn — role is either "user" or "assistant".
# SessionHistory holds the ordered list of SessionMessages for a user
# and is loaded from Redis at the start of each request, injected into
# AgentDeps, and passed as message_history to the agent so it has
# conversational context across separate Telegram messages.
# TTL is managed by Redis directly — no expiry logic needed here.
class SessionMessage(BaseModel):
    role: str                      # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class SessionHistory(BaseModel):
    user_id: str
    messages: list[SessionMessage] = Field(default_factory=list)