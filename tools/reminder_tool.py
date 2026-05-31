import os
from datetime import datetime, timezone
from schemas.reminder import Reminder
import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "data/reminder.db")


async def create_reminder(text: str, remind_at: datetime) -> Reminder:
    """Store a new reminder. Returns the created record."""
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO reminders (text, remind_at, created_at, fired) VALUES (?, ?, ?, 0)",
            (text, remind_at.isoformat(), now.isoformat()),
        )
        await db.commit()
        row_id = cursor.lastrowid

    return Reminder(id=row_id, text=text, remind_at=remind_at, created_at=now, fired=False)


async def list_reminders(include_past: bool = False) -> list[Reminder]:
    """Return upcoming reminders (or all if include_past=True), ordered by remind_at."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_past:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired FROM reminders ORDER BY remind_at ASC"
            )
        else:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired "
                "FROM reminders WHERE remind_at >= ? AND fired = 0 ORDER BY remind_at ASC",
                (now_iso,),
            )
        rows = await cursor.fetchall()

    return [
        Reminder(
            id=row["id"],
            text=row["text"],
            remind_at=datetime.fromisoformat(row["remind_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            fired=bool(row["fired"]),
        )
        for row in rows
    ]


async def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by ID. Returns True if found and deleted, False otherwise."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await db.commit()
        return cursor.rowcount > 0