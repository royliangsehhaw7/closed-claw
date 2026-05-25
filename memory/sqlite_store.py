from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv

from core.logger import logger
from schemas.turn_record import TurnRecord

load_dotenv()

_DEFAULT_DB_PATH = os.getenv("SQLITE_PATH", "data/assistant.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS agent_turns (
    turn_id       TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    user_email    TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    user_input    TEXT NOT NULL,
    agent_output  TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL
);
"""


class SQLiteStore:
    """Append-only turn log backed by SQLite.

    Stage 1c: called directly by main.py.
    Stage 2+: called from the gateway webhook handler. Same interface, no changes.
    Stage 3: APScheduler job store uses the same SQLite file (different table).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        logger.debug("SQLiteStore | db_path=%s", self._db_path)

    async def initialise(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()
        logger.info("SQLiteStore.initialise | ready | path=%s", self._db_path)

    async def write_turn(self, record: TurnRecord) -> None:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO agent_turns
                        (turn_id, user_id, user_email, agent_name, user_input,
                         agent_output, model, input_tokens, output_tokens, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.turn_id,
                        record.user_id,
                        record.user_email,
                        record.agent_name,
                        record.user_input,
                        record.agent_output,
                        record.model,
                        record.input_tokens,
                        record.output_tokens,
                        record.timestamp.isoformat(),
                    ),
                )
                await db.commit()
            logger.debug(
                "SQLiteStore.write_turn | turn_id=%s | user=%s | email=%s",
                record.turn_id, record.user_id, record.user_email,
            )
        except Exception:
            logger.exception(
                "SQLiteStore.write_turn | FAILED | turn_id=%s", record.turn_id
            )