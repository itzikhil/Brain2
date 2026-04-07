"""Reminders service — store, query, and fire reminders in Postgres."""
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.database import get_db_context

logger = logging.getLogger(__name__)


async def init_reminders_table():
    """Create the reminders table if it doesn't exist."""
    async with get_db_context() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                fired BOOLEAN DEFAULT FALSE
            );
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(fired, remind_at);"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_reminders_chat ON reminders(chat_id, fired);"
        ))


async def add_reminder(chat_id: int, reminder_text: str, remind_at: datetime) -> int:
    """Store a reminder and return its id."""
    async with get_db_context() as db:
        result = await db.execute(
            text("""
                INSERT INTO reminders (chat_id, text, remind_at)
                VALUES (:chat_id, :text, :remind_at)
                RETURNING id
            """),
            {"chat_id": chat_id, "text": reminder_text, "remind_at": remind_at},
        )
        row = result.fetchone()
        return row[0]


async def get_pending_reminders() -> list[dict]:
    """Return all unfired reminders whose time has come."""
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT id, chat_id, text, remind_at
            FROM reminders
            WHERE fired = FALSE AND remind_at <= NOW()
            ORDER BY remind_at
        """))
        return [
            {"id": r[0], "chat_id": r[1], "text": r[2], "remind_at": r[3]}
            for r in result.fetchall()
        ]


async def mark_fired(reminder_id: int):
    """Mark a reminder as fired."""
    async with get_db_context() as db:
        await db.execute(
            text("UPDATE reminders SET fired = TRUE WHERE id = :id"),
            {"id": reminder_id},
        )


async def list_reminders(chat_id: int) -> list[dict]:
    """List all active (unfired) reminders for a chat."""
    async with get_db_context() as db:
        result = await db.execute(
            text("""
                SELECT id, text, remind_at
                FROM reminders
                WHERE chat_id = :chat_id AND fired = FALSE
                ORDER BY remind_at
            """),
            {"chat_id": chat_id},
        )
        return [
            {"id": r[0], "text": r[1], "remind_at": r[2]}
            for r in result.fetchall()
        ]


async def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by id. Returns True if a row was deleted."""
    async with get_db_context() as db:
        result = await db.execute(
            text("DELETE FROM reminders WHERE id = :id AND fired = FALSE"),
            {"id": reminder_id},
        )
        return result.rowcount > 0
