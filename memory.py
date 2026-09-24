"""Small, transparent SQLite memory store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Memory:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                facts TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id, id);
            """
        )
        self.conn.commit()

    def upsert_user(self, user_id: str, name: Optional[str] = None) -> None:
        timestamp = now()
        self.conn.execute(
            """INSERT INTO users(user_id, name, facts, created_at, last_seen)
               VALUES (?, ?, '{}', ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 name=COALESCE(excluded.name, users.name), last_seen=excluded.last_seen""",
            (user_id, name or user_id, timestamp, timestamp),
        )
        self.conn.commit()

    def add_message(self, user_id: str, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages(user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, now()),
        )
        self.conn.commit()

    def recent_messages(self, user_id: str, limit: int) -> List[Dict[str, str]]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    def facts(self, user_id: str) -> Dict[str, str]:
        row = self.conn.execute(
            "SELECT facts FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row[0])
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def set_fact(self, user_id: str, key: str, value: str) -> None:
        facts = self.facts(user_id)
        facts[key.strip()] = value.strip()
        self.conn.execute(
            "UPDATE users SET facts=?, last_seen=? WHERE user_id=?",
            (json.dumps(facts, ensure_ascii=False), now(), user_id),
        )
        self.conn.commit()

    def clear_history(self, user_id: str) -> None:
        self.conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

