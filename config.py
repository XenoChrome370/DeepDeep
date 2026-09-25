"""Configuration for DeepDeep.

Runtime defaults are deliberately offline. Set DEEPDEEP_ALLOW_DOWNLOAD=1 only
for the one-time model download, then run DeepDeep without internet again.
"""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
DB_PATH = DATA_DIR / "deepdeep.db"
INDEX_PATH = DATA_DIR / "index.json"

MODEL_ID = os.environ.get("DEEPDEEP_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
MODEL_PATH = os.environ.get("DEEPDEEP_MODEL_PATH", "").strip()
DEVICE = os.environ.get("DEEPDEEP_DEVICE", "auto").lower()
ALLOW_DOWNLOAD = os.environ.get("DEEPDEEP_ALLOW_DOWNLOAD", "0") == "1"

MAX_NEW_TOKENS = int(os.environ.get("DEEPDEEP_MAX_NEW_TOKENS", "1024"))
TEMPERATURE = float(os.environ.get("DEEPDEEP_TEMPERATURE", "0.7"))
TOP_P = float(os.environ.get("DEEPDEEP_TOP_P", "0.9"))
REPETITION_PENALTY = float(os.environ.get("DEEPDEEP_REPETITION_PENALTY", "1.08"))
CONTEXT_TURNS = int(os.environ.get("DEEPDEEP_CONTEXT_TURNS", "8"))
RAG_TOP_K = int(os.environ.get("DEEPDEEP_RAG_TOP_K", "4"))

SYSTEM_PROMPT = """You are DeepDeep, a private local AI assistant.
You are friendly, direct, and honest. You help with everyday questions and
software development. Use the user's local documents when they are relevant,
but do not invent facts that are not in the conversation or documents. If you
are unsure, say so. Keep answers useful and reasonably concise. You have no
internet access during this conversation unless the user explicitly asks for
web search."""


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
