from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


# Purpose: Internal representation of a Google Task.
# The Concierge agent (Stage 1c) maps raw Google Tasks API responses into
# this shape before working with them or returning them to the user.
# list_id and list_name together support the Kanban-style movement of tasks
# between lists without a separate lookup. The status field mirrors the
# Google Tasks API values exactly to avoid translation errors.
class TaskItem(BaseModel):
    task_id: str
    title: str
    list_id: str
    list_name: str
    due: datetime | None = None
    status: str = "needsAction"    # "needsAction" | "completed"
    notes: str | None = None