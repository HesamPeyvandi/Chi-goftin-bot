"""
SQLite storage layer.

Two tables are used:

- groups: one row per Telegram group the bot has seen, tracking its title
  and whether the admin has marked it for permanent message retention.
- messages: chat history, stored per group as pre-formatted lines so the
  summarization prompt receives exactly the same input shape as before.

Groups that are NOT marked permanent automatically get their oldest
messages pruned down to DEFAULT_MESSAGE_HISTORY_LIMIT after every insert.
"""

import sqlite3
import threading
from contextlib import contextmanager

import config

_LOCAL_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(config.DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _cursor():
    """Provide a thread-safe cursor that commits on success and rolls back on error."""
    with _LOCAL_LOCK:
        connection = _connect()
        try:
            yield connection.cursor()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def init_db() -> None:
    """Create tables on first run. Safe to call every startup."""
    with _cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                is_permanent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                formatted_text TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)"
        )


def upsert_group(chat_id: int, title: str) -> None:
    """Register a group or refresh its stored title."""
    with _cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO groups (chat_id, title, is_permanent)
            VALUES (?, ?, 0)
            ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title
            """,
            (chat_id, title),
        )


def get_all_groups() -> list[tuple[int, str, bool]]:
    """Return all known groups as (chat_id, title, is_permanent) tuples."""
    with _cursor() as cursor:
        cursor.execute(
            "SELECT chat_id, title, is_permanent FROM groups ORDER BY title"
        )
        rows = cursor.fetchall()
    return [(chat_id, title, bool(is_permanent)) for chat_id, title, is_permanent in rows]


def group_exists(chat_id: int) -> bool:
    with _cursor() as cursor:
        cursor.execute("SELECT 1 FROM groups WHERE chat_id = ?", (chat_id,))
        return cursor.fetchone() is not None


def set_group_permanent(chat_id: int, is_permanent: bool) -> bool:
    """Toggle permanent retention for a group. Returns False if the group is unknown."""
    if not group_exists(chat_id):
        return False
    with _cursor() as cursor:
        cursor.execute(
            "UPDATE groups SET is_permanent = ? WHERE chat_id = ?",
            (1 if is_permanent else 0, chat_id),
        )
    if not is_permanent:
        _trim_group_history(chat_id)
    return True


def is_group_permanent(chat_id: int) -> bool:
    with _cursor() as cursor:
        cursor.execute("SELECT is_permanent FROM groups WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
    return bool(row[0]) if row else False


def add_message(chat_id: int, formatted_text: str) -> None:
    """Store one formatted message line and prune old history if needed."""
    with _cursor() as cursor:
        cursor.execute(
            "INSERT INTO messages (chat_id, formatted_text) VALUES (?, ?)",
            (chat_id, formatted_text),
        )
    if not is_group_permanent(chat_id):
        _trim_group_history(chat_id)


def _trim_group_history(chat_id: int, keep_limit: int = None) -> None:
    """Delete the oldest messages beyond keep_limit for a single group."""
    keep_limit = keep_limit or config.DEFAULT_MESSAGE_HISTORY_LIMIT
    with _cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM messages
            WHERE chat_id = ? AND id NOT IN (
                SELECT id FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (chat_id, chat_id, keep_limit),
        )


def has_messages(chat_id: int) -> bool:
    with _cursor() as cursor:
        cursor.execute("SELECT 1 FROM messages WHERE chat_id = ? LIMIT 1", (chat_id,))
        return cursor.fetchone() is not None


def get_recent_messages(chat_id: int, limit: int) -> list[str]:
    """Return up to `limit` most recent formatted messages, oldest first."""
    with _cursor() as cursor:
        cursor.execute(
            """
            SELECT formatted_text FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        )
        rows = cursor.fetchall()
    return [row[0] for row in reversed(rows)]


def get_all_messages(chat_id: int) -> list[str]:
    """Return every stored formatted message for a group, oldest first.

    Used by the /export admin command, which needs the full history
    regardless of DEFAULT_MESSAGE_HISTORY_LIMIT.
    """
    with _cursor() as cursor:
        cursor.execute(
            "SELECT formatted_text FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        )
        rows = cursor.fetchall()
    return [row[0] for row in rows]


def get_group_title(chat_id: int) -> str | None:
    """Return the stored title for a group, or None if it isn't known."""
    with _cursor() as cursor:
        cursor.execute("SELECT title FROM groups WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
    return row[0] if row else None
