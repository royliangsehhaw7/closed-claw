# from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: Normalised inbound message from any channel.
# Every message entering the system — whether from Telegram, CLI, or the
# Heartbeat engine — is converted into this shape before anything else touches it.
# The Gateway (Stage 2) is responsible for the conversion. Agents never see
# raw Telegram Update objects; they only ever see a Message.
# Channel field distinguishes the source for logging and routing purposes.
class Message(BaseModel):
    message_id: str
    user_id: str
    text: str
    channel: str = "cli"           # "cli" | "telegram"
    timestamp: datetime = Field(default_factory=datetime.now)