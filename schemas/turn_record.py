from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: One agent exchange written to the SQLite agent_turns table (Stage 1c).
# Written after every Supervisor run — captures input, output, which agent
# handled it, which model was used, and token counts for cost tracking.
# Append-only. Never updated after writing. Queryable for debugging and
# reviewing conversation history without relying on Redis.
class TurnRecord(BaseModel):
    turn_id: str
    user_id: str
    agent_name: str
    user_input: str
    agent_output: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)