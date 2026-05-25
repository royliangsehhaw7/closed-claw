from __future__ import annotations

from pydantic_ai import RunContext

from core.deps import AgentDeps
from core.logger import logger


async def log_decision(ctx: RunContext[AgentDeps], message: str) -> str:
    """Call this once to record your reasoning before returning your final result.

    Summarise your chain of thought: what the user asked, what you decided to do,
    which tools you called or chose not to call, and why. This is your thinking,
    not your final answer.
    """
    usage = ctx.usage
    logger.info(
        "log_decision | user=%s | %s | request_tokens=%s | response_tokens=%s | total=%s",
        ctx.deps.user_id,
        message,
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
    )
    return "logged"