# from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


# Purpose: Internal representation of a Google Calendar event.
# Every task deadline is reflected as a CalendarEvent — the Concierge agent
# creates or updates one whenever a task is created or its deadline changes.
# task_id links the event back to its originating TaskItem so the two stay
# in sync. The Heartbeat engine (Stage 3) reads CalendarEvents to determine
# which deadlines are approaching and need a Telegram alert.
class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    task_id: str | None = None     # links back to the originating TaskItem