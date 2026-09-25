"""Offline document retrieval using a persisted TF-IDF index.

This avoids a second neural model and a vector database. It is intentionally
simple, inspectable, and works without internet after installation.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
import threading
from typing import Dict, List


TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_'-]*")


class LocalRAG:
    def __init__(self, index_path: Path, top_k: int = 4):
        self.index_path = index_path
        self.top_k = top_k
        self.documents: List[Dict] = []
        self._lock = threading.RLock()
        self._load()

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [token.lower() for token in TOKEN_RE.findall(text)]

    @staticmethod
    def _chunks(text: str, size: int = 1200, overlap: int = 160) -> List[str]:
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            chunk = " ".join(words[start : start + size // 6])
            if chunk.strip():
                chunks.append(chunk.strip())
            start += max(1, size // 6 - overlap // 10)
        return chunks

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.documents = [
                doc
                for doc in data
                if isinstance(doc, dict)
                and isinstance(doc.get("source"), str)
                and isinstance(doc.get("text"), str)
            ] if isinstance(data, list) else []
        except (OSError, ValueError, json.JSONDecodeError):
            self.documents = []

    def _save(self) -> None:
        with self._lock:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(
                json.dumps(self.documents, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def add_text(self, text: str, source: str = "manual") -> int:
        with self._lock:
            chunks = self._chunks(text)
            self.documents = [doc for doc in self.documents if doc.get("source") != source]
            for number, chunk in enumerate(chunks):
                self.documents.append({"source": source, "chunk": number, "text": chunk})
            self._save()
            return len(chunks)

    def add_file(self, path: Path) -> int:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return self.add_text(text, source=str(path))

    def add_folder(self, folder: Path) -> int:
        with self._lock:
            total = 0
            for path in sorted(folder.rglob("*")):
                if path.is_file() and path.suffix.lower() in {".txt", ".md", ".py", ".json", ".csv"}:
                    total += self.add_file(path)
            return total

    def search(self, query: str, k: int | None = None) -> List[Dict[str, str]]:
        with self._lock:
            if not self.documents:
                return []
            query_counts = Counter(self._tokens(query))
            if not query_counts:
                return []
            doc_counts = [Counter(self._tokens(doc["text"])) for doc in self.documents]
            document_frequency = Counter()
            for counts in doc_counts:
                document_frequency.update(counts.keys())
            total = len(doc_counts)

            def vector(counts: Counter) -> Dict[str, float]:
                return {
                    token: frequency * math.log((total + 1) / (document_frequency[token] + 1))
                    for token, frequency in counts.items()
                }

            query_vector = vector(query_counts)
            query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
            scored = []
            for doc, counts in zip(self.documents, doc_counts):
                doc_vector = vector(counts)
                doc_norm = math.sqrt(sum(value * value for value in doc_vector.values())) or 1.0
                score = sum(query_vector.get(key, 0.0) * value for key, value in doc_vector.items())
                score /= query_norm * doc_norm
                if score > 0:
                    scored.append((score, doc))
            scored.sort(key=lambda item: item[0], reverse=True)
            return [doc for _, doc in scored[: k or self.top_k]]

    def sources(self) -> List[str]:
        with self._lock:
            return sorted({str(doc.get("source", "")) for doc in self.documents})
