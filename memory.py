"""Small, transparent SQLite memory store."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_CONVERSATION_TITLE = "New conversation"
AUTO_TITLE_LIMIT = 60


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def synchronized(method):
    """Serialize access to the connection, which is shared by the GUI threads."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Memory:
    def __init__(self, db_path: Path, auto_rename_chats: bool = True):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.auto_rename_chats = auto_rename_chats
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    @synchronized
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
                conversation_id TEXT,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id, id);
            """
        )
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(messages)")}
        if "conversation_id" not in columns:
            self.conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id, id)"
        )
        legacy_users = self.conn.execute(
            "SELECT DISTINCT user_id FROM messages WHERE conversation_id IS NULL"
        ).fetchall()
        for (user_id,) in legacy_users:
            conversation_id = self.create_conversation(user_id, commit=False)
            self.conn.execute(
                "UPDATE messages SET conversation_id=? WHERE user_id=? AND conversation_id IS NULL",
                (conversation_id, user_id),
            )
        self.conn.commit()

    @synchronized
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

    @synchronized
    def create_conversation(
        self,
        user_id: str,
        title: str = DEFAULT_CONVERSATION_TITLE,
        commit: bool = True,
    ) -> str:
        conversation_id = uuid.uuid4().hex
        timestamp = now()
        self.conn.execute(
            """INSERT INTO conversations(conversation_id, user_id, title, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, user_id, title, timestamp, timestamp),
        )
        if commit:
            self.conn.commit()
        return conversation_id

    @synchronized
    def list_conversations(self, user_id: str) -> List[Dict[str, str]]:
        rows = self.conn.execute(
            """SELECT conversation_id, title, created_at, updated_at
               FROM conversations WHERE user_id=? ORDER BY updated_at DESC, created_at DESC""",
            (user_id,),
        ).fetchall()
        return [
            {"conversation_id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}
            for row in rows
        ]

    @synchronized
    def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> None:
        title = " ".join(title.split()).strip()
        if not title:
            raise ValueError("Conversation title cannot be empty")
        self.conn.execute(
            """UPDATE conversations SET title=?, updated_at=?
               WHERE conversation_id=? AND user_id=?""",
            (title[:120], now(), conversation_id, user_id),
        )
        self.conn.commit()

    @staticmethod
    def conversation_title_from_message(content: str) -> str:
        """Create a short, readable title without sending chat content anywhere."""
        title = " ".join(content.split()).strip()
        if title.startswith("/web "):
            title = title[5:].strip()
        if len(title) <= AUTO_TITLE_LIMIT:
            return title or DEFAULT_CONVERSATION_TITLE
        shortened = title[: AUTO_TITLE_LIMIT - 1].rsplit(" ", 1)[0].rstrip(" .,!?;:")
        return f"{shortened}…" if shortened else f"{title[:AUTO_TITLE_LIMIT - 1]}…"

    @synchronized
    def conversation_messages(self, conversation_id: str, limit: int) -> List[Dict[str, str]]:
        rows = self.conn.execute(
            """SELECT role, content FROM messages
               WHERE conversation_id=? ORDER BY id DESC LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    @synchronized
    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: Optional[str] = None,
        content: Optional[str] = None,
    ) -> None:
        if content is None:
            content = role
            role = conversation_id
            conversations = self.list_conversations(user_id)
            conversation_id = (
                conversations[0]["conversation_id"]
                if conversations
                else self.create_conversation(user_id)
            )
        if role not in {"user", "assistant"} or content is None:
            raise ValueError("role must be 'user' or 'assistant', and content is required")
        if not self.conversation_belongs_to_user(user_id, conversation_id):
            raise ValueError("Conversation does not belong to this user")
        self.conn.execute(
            "INSERT INTO messages(user_id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, conversation_id, role, content, now()),
        )
        if role == "user":
            if self.auto_rename_chats:
                self.conn.execute(
                    """UPDATE conversations
                       SET title=CASE WHEN title='New conversation' THEN ? ELSE title END,
                           updated_at=? WHERE conversation_id=? AND user_id=?""",
                    (self.conversation_title_from_message(content), now(), conversation_id, user_id),
                )
            else:
                self.conn.execute(
                    "UPDATE conversations SET updated_at=? WHERE conversation_id=? AND user_id=?",
                    (now(), conversation_id, user_id),
                )
        else:
            self.conn.execute(
                "UPDATE conversations SET updated_at=? WHERE conversation_id=? AND user_id=?",
                (now(), conversation_id, user_id),
            )
        self.conn.commit()

    @synchronized
    def recent_messages(self, user_id: str, limit: int) -> List[Dict[str, str]]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    @synchronized
    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        self.conn.execute(
            "DELETE FROM messages WHERE user_id=? AND conversation_id=?",
            (user_id, conversation_id),
        )
        self.conn.execute(
            "DELETE FROM conversations WHERE user_id=? AND conversation_id=?",
            (user_id, conversation_id),
        )
        self.conn.commit()

    @synchronized
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

    @synchronized
    def set_fact(self, user_id: str, key: str, value: str) -> None:
        facts = self.facts(user_id)
        facts[key.strip()] = value.strip()
        self.conn.execute(
            "UPDATE users SET facts=?, last_seen=? WHERE user_id=?",
            (json.dumps(facts, ensure_ascii=False), now(), user_id),
        )
        self.conn.commit()

    @synchronized
    def conversation_belongs_to_user(self, user_id: str, conversation_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM conversations WHERE conversation_id=? AND user_id=?",
            (conversation_id, user_id),
        ).fetchone()
        return row is not None

    @synchronized
    def clear_history(self, user_id: str, conversation_id: Optional[str] = None) -> None:
        if conversation_id is None:
            self.conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
        else:
            self.conn.execute(
                "DELETE FROM messages WHERE user_id=? AND conversation_id=?",
                (user_id, conversation_id),
            )
        self.conn.commit()

    @synchronized
    def close(self) -> None:
        self.conn.close()
