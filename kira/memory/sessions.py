"""Session database — SQLite + FTS5 for conversation history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionDB:
    """Persistent conversation storage with full-text search."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                channel TEXT DEFAULT 'cli',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                model TEXT,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(content, content=messages, content_rowid=id);

            CREATE TABLE IF NOT EXISTS skill_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                skill_name TEXT,
                outcome TEXT,
                criteria_results TEXT,
                user_feedback TEXT,
                tokens_used INTEGER,
                cost_usd REAL,
                iterations INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
            END;
            """
        )
        self._conn.commit()

    def create_session(
        self,
        channel: str = "cli",
        title: str | None = None,
        model: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, title, channel, created_at, updated_at, model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, title, channel, now, now, model),
        )
        self._conn.commit()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        tokens: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ):
        self._conn.execute(
            "INSERT INTO messages "
            "(session_id, role, content, tool_calls, tool_call_id, tool_name, "
            "tokens, cost_usd, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                tool_name,
                tokens,
                cost_usd,
                model,
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET message_count = message_count + 1, "
            "total_tokens = total_tokens + ?, "
            "total_cost_usd = total_cost_usd + ?, "
            "updated_at = datetime('now') "
            "WHERE id = ?",
            (tokens, cost_usd, session_id),
        )
        self._conn.commit()

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Full-text search across all messages."""
        rows = self._conn.execute(
            "SELECT m.*, s.title as session_title "
            "FROM messages_fts fts "
            "JOIN messages m ON m.id = fts.rowid "
            "JOIN sessions s ON s.id = m.session_id "
            "WHERE messages_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_session_title(self, session_id: str, title: str):
        self._conn.execute(
            "UPDATE sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()
