"""Application services shared by DeepDeep's interfaces.

The web and terminal interfaces should translate user input into calls to this
module, rather than each reimplementing conversation and command behavior.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import shlex
import threading
from typing import Any, Iterable

from brain import DeepDeepBrain


ATTACHMENT_EXTENSIONS = {".txt", ".md", ".py", ".json", ".csv"}
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_ATTACHMENT_FILES = 10
MAX_ATTACHMENT_TEXT_CHARS = 80_000


class ConversationNotFound(ValueError):
    """Raised when a conversation is not owned by the active user."""


class AttachmentError(ValueError):
    """Raised when an uploaded attachment cannot be accepted."""


class ModelUnavailable(RuntimeError):
    """Raised when a chat is requested before the local model is ready."""


@dataclass(frozen=True)
class Attachment:
    name: str
    text: str


def read_attachments(uploads: Iterable[Any]) -> list[Attachment]:
    """Validate and decode text uploads without depending on Flask."""
    attachments: list[Attachment] = []
    total_chars = 0
    for uploaded in uploads:
        filename = Path(getattr(uploaded, "filename", "") or "").name
        if not filename:
            continue
        if len(attachments) >= MAX_ATTACHMENT_FILES:
            raise AttachmentError(f"Too many attachments ({MAX_ATTACHMENT_FILES} maximum)")
        if Path(filename).suffix.lower() not in ATTACHMENT_EXTENSIONS:
            raise AttachmentError(f"Unsupported attachment type: {filename}")
        content = uploaded.read(MAX_ATTACHMENT_BYTES + 1)
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise AttachmentError(f"Attachment is too large (2 MB maximum): {filename}")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AttachmentError(f"Attachment must be UTF-8 text: {filename}") from exc
        total_chars += len(text)
        if total_chars > MAX_ATTACHMENT_TEXT_CHARS:
            raise AttachmentError(
                "Attachments contain too much text "
                f"({MAX_ATTACHMENT_TEXT_CHARS:,} characters maximum)"
            )
        attachments.append(Attachment(filename, text))
    return attachments


class ConversationService:
    """Own conversation workflows while interfaces remain presentation-only."""

    def __init__(self, brain: DeepDeepBrain, user_id: str):
        self.brain = brain
        self.user_id = user_id
        self.memory_lock = threading.RLock()
        self.model_lock = threading.Lock()
        self.state: dict[str, Any] = {
            "loaded": brain.model is not None and brain.tokenizer is not None,
            "error": None,
        }
        self._model_executor = ThreadPoolExecutor(max_workers=1)

    @property
    def loaded(self) -> bool:
        return bool(self.state["loaded"])

    @property
    def status(self) -> str:
        if self.loaded:
            return "Local · ready"
        if self.state["error"]:
            return "Could not load the model"
        return "Warming up local model..."

    def load_model(self) -> None:
        try:
            self.brain.load_model()
            self.state["loaded"] = True
        except Exception as exc:
            self.state["error"] = str(exc)

    def start_model_loading(self) -> None:
        if not self.loaded:
            self._model_executor.submit(self.load_model)

    def list_conversations(self) -> list[dict[str, str]]:
        with self.memory_lock:
            return self.brain.memory.list_conversations(self.user_id)

    def conversation_messages(self, conversation_id: str) -> list[dict[str, str]]:
        self.require_conversation(conversation_id)
        with self.memory_lock:
            return self.brain.memory.conversation_messages(conversation_id, 1000)

    def require_conversation(self, conversation_id: str) -> None:
        with self.memory_lock:
            belongs = self.brain.memory.conversation_belongs_to_user(
                self.user_id, conversation_id
            )
        if not belongs:
            raise ConversationNotFound("Conversation not found")

    def ensure_conversation(self) -> str:
        existing = self.list_conversations()
        if existing:
            return existing[0]["conversation_id"]
        with self.memory_lock:
            return self.brain.memory.create_conversation(self.user_id)

    def create_conversation(self) -> str:
        with self.memory_lock:
            return self.brain.memory.create_conversation(self.user_id)

    def delete_conversation(self, conversation_id: str) -> None:
        self.require_conversation(conversation_id)
        with self.memory_lock:
            self.brain.memory.delete_conversation(self.user_id, conversation_id)

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        self.require_conversation(conversation_id)
        with self.memory_lock:
            self.brain.memory.rename_conversation(self.user_id, conversation_id, title)

    def _record(self, conversation_id: str, role: str, content: str) -> None:
        with self.memory_lock:
            self.brain.memory.add_message(
                self.user_id, conversation_id, role, content
            )

    def handle_message(self, conversation_id: str, message: str, uploads: Iterable[Any] = ()) -> None:
        """Handle one user action, including built-in commands and model chat."""
        self.require_conversation(conversation_id)
        if message == "/clear":
            with self.memory_lock:
                self.brain.memory.clear_history(self.user_id, conversation_id)
            return
        if message == "/sources":
            sources = self.brain.rag.sources()
            reply = "\n".join(sources) if sources else "No local documents indexed."
            self._record(conversation_id, "user", message)
            self._record(conversation_id, "assistant", reply)
            return
        if message.startswith("/remember "):
            key, separator, value = message[len("/remember ") :].partition("=")
            if not separator or not key.strip() or not value.strip():
                raise ValueError("Use /remember key=value")
            self.brain.remember_fact(self.user_id, key.strip(), value.strip())
            self._record(conversation_id, "user", message)
            self._record(conversation_id, "assistant", "Remembered that for you.")
            return
        if message.startswith("/add "):
            try:
                path = Path(shlex.split(message[len("/add ") :])[0]).expanduser().resolve()
                count = self.brain.rag.add_file(path)
            except (IndexError, OSError, ValueError) as exc:
                raise ValueError(f"Could not index that file: {exc}") from exc
            self._record(conversation_id, "user", message)
            self._record(conversation_id, "assistant", f"Indexed {count} chunk(s) from {path}.")
            return
        if not self.loaded:
            raise ModelUnavailable(self.state["error"] or "The model is still warming up")

        attachments = read_attachments(uploads)
        payload = [{"name": item.name, "text": item.text} for item in attachments]
        with self.model_lock:
            self.brain.chat(self.user_id, conversation_id, message, attachments=payload)

    def close(self) -> None:
        self._model_executor.shutdown(wait=False, cancel_futures=True)
        self.brain.close()
