import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_FILE


@contextmanager
def _db():
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize():
    with _db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                title TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            """
        )


def current_session_id():
    initialize()
    with _db() as db:
        row = db.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return int(row["id"])
        cur = db.execute(
            "INSERT INTO sessions(created_at, title) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), "Aero clean-slate chat"),
        )
        return int(cur.lastrowid)


def save_message(session_id, role, content):
    with _db() as db:
        db.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (int(session_id), str(role), str(content), datetime.now(timezone.utc).isoformat()),
        )


def recent_messages(session_id, limit):
    with _db() as db:
        rows = db.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(session_id), int(limit)),
        ).fetchall()
    rows = list(reversed(rows))
    return [{"role": row["role"], "content": row["content"]} for row in rows]
