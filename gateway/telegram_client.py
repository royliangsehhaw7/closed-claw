from __future__ import annotations

import os

import httpx

from core.logger import logger

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BASE = f"https://api.telegram.org/bot{_TOKEN}"


async def send_message(chat_id: int, text: str) -> None:
    """Send a plain-text message to a Telegram chat.

    Telegram enforces a 4096-character message limit. Messages exceeding this
    are truncated with a notice rather than crashing.
    """
    if len(text) > 4096:
        text = text[:4050] + "\n\n[message truncated]"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )

    if response.status_code != 200:
        logger.error(
            "telegram_client.send_message | FAILED | status=%d | body=%s",
            response.status_code, response.text,
        )
    else:
        logger.debug("telegram_client.send_message | ok | chat_id=%d", chat_id)