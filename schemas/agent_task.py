from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from schemas.message import Message


# Purpose: Unit of work placed on the per-user asyncio.Queue (Stage 2).
# The Gateway wraps every inbound Message in an AgentTask before enqueuing it.
# The Heartbeat engine (Stage 3) also produces AgentTasks — with source="heartbeat" —
# so the agent loop treats deadline alerts identically to user messages.
# The drain coroutine dequeues one AgentTask at a time per user, ensuring
# messages are processed in order with no concurrency per user.
class AgentTask(BaseModel):
    task_id: str
    user_id: str
    message: Message
    source: str = "user"           # "user" | "heartbeat"
    created_at: datetime = Field(default_factory=datetime.now)