from __future__ import annotations

from pydantic import BaseModel, Field


class SupervisorResponse(BaseModel):
    """
    Structured response returned by SupervisorAgent to the caller.

    Stage 1c: main.py prints message, ignores requires_followup.
    Stage 2+: Gateway sends message to Telegram; uses requires_followup
              to hold the conversation open or close it after delivery.
    """

    message: str = Field(
        description=(
            "The response to deliver to the user. Plain text, natural tone. "
            "Not a verbatim repeat of the Executor's summary."
        )
    )
    requires_followup: bool = Field(
        default=False,
        description=(
            "True if the assistant is waiting for the user to supply missing "
            "information before an action can proceed. False otherwise."
        ),
    )