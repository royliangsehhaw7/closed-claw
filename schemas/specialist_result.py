from __future__ import annotations

from pydantic import BaseModel, Field


class SpecialistResult(BaseModel):
    """
    Structured result returned by any specialist agent to the Supervisor.

    The Supervisor uses `summary` to compose the final user-facing message.
    `actions_taken` is an audit trail of every tool call made.
    `missing_info` is non-None only when the specialist could not act because
    required information was absent — in which case no action was taken.
    """

    summary: str = Field(
        description=(
            "Plain-language description of what was done. Be specific: include "
            "task titles, due dates, recipient addresses, subjects. If nothing "
            "was done because information was missing, state what was missing."
        )
    )
    actions_taken: list[str] = Field(
        description=(
            "One entry per tool call completed. Empty if nothing was done. "
            "Examples: 'Listed 3 tasks', 'Created task: Review report (due Friday)', "
            "'Created calendar event: Review report (Friday)', "
            "'Sent email to george@example.com: subject Meeting at 3pm'."
        )
    )
    missing_info: str | None = Field(
        default=None,
        description=(
            "If the request could not be completed because required information "
            "was missing, describe exactly what is needed — one item only. "
            "None if the request was fully completed."
        ),
    )