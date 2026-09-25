"""Model loading and chat orchestration."""

from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Dict, List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from config import (
    ALLOW_DOWNLOAD,
    CONTEXT_TURNS,
    DEVICE,
    INDEX_PATH,
    MAX_NEW_TOKENS,
    MODEL_ID,
    MODEL_PATH,
    RAG_TOP_K,
    REPETITION_PENALTY,
    SYSTEM_PROMPT,
    TEMPERATURE,
    TOP_P,
    AUTO_RENAME_CHATS,
)
from memory import Memory
from rag import LocalRAG
from web_search import WebSearchUnavailable, bing_is_available, collect


class DeepDeepBrain:
    _RESEARCH_PATTERNS = (
        r"\b(?:latest|recent|current|today|tonight|tomorrow|yesterday|this week|this month|this year)\b",
        r"\b(?:news|headline|weather|forecast|stock price|share price|exchange rate)\b",
        r"\b(?:who is|what is|when is|where is)\s+(?:the\s+)?(?:current|new|latest)\b",
        r"\b(?:look up|search for|find out|research|browse|verify|fact[- ]check)\b",
        r"\b(?:recommend|recommendation|best|top|compare|comparison)\b",
        r"\b(?:release|version|pricing|availability|opening hours)\b",
    )

    def __init__(self, db_path: Path, index_path: Path):
        self.memory = Memory(db_path, auto_rename_chats=AUTO_RENAME_CHATS)
        self.rag = LocalRAG(index_path, top_k=RAG_TOP_K)
        self.tokenizer = None
        self.model = None
        self.device = self._choose_device()
        self.model_source = MODEL_PATH or MODEL_ID
        self.web_enabled = bing_is_available()
        os.environ["DEEPDEEP_ALLOW_WEB"] = "1" if self.web_enabled else "0"

    @staticmethod
    def _choose_device() -> str:
        if DEVICE in {"cpu", "cuda", "mps"}:
            if DEVICE == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("DEEPDEEP_DEVICE=cuda was requested, but CUDA is unavailable")
            mps_backend = getattr(torch.backends, "mps", None)
            if DEVICE == "mps" and (mps_backend is None or not mps_backend.is_available()):
                raise RuntimeError("DEEPDEEP_DEVICE=mps was requested, but MPS is unavailable")
            return DEVICE
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def load_model(self, allow_download: Optional[bool] = None) -> None:
        download = ALLOW_DOWNLOAD if allow_download is None else allow_download
        local_only = not download
        source = Path(self.model_source).expanduser() if MODEL_PATH else self.model_source
        if local_only and not MODEL_PATH:
            # Some transformers versions still hit the network with local_files_only
            # for repo ids; resolving to the cached snapshot path keeps loading offline.
            try:
                from huggingface_hub import snapshot_download

                source = Path(
                    snapshot_download(str(source), local_files_only=True)
                )
            except Exception:
                pass  # fall through: from_pretrained raises the descriptive error
        kwargs = {"local_files_only": local_only}
        if self.device == "cpu":
            kwargs["dtype"] = torch.float32
        else:
            kwargs["dtype"] = torch.float16

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(str(source), **kwargs)
            self.model = AutoModelForCausalLM.from_pretrained(str(source), **kwargs)
        except Exception as exc:
            mode = "offline" if local_only else "download"
            raise RuntimeError(
                f"Could not load {self.model_source!r} in {mode} mode. "
                "Download it once with `python main.py --download-model`, or set "
                "DEEPDEEP_MODEL_PATH to an already-downloaded model directory. "
                f"Original error: {exc}"
            ) from exc
        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _with_attachments(user_message: str, attachments: List[Dict[str, str]]) -> str:
        if not attachments:
            return user_message
        files = "\n\n".join(
            f"--- Attached file: {attachment['name']} ---\n{attachment['text']}\n--- End attached file ---"
            for attachment in attachments
        )
        return f"{user_message}\n\nAttached files:\n{files}"

    def _build_messages(self, user_id: str, conversation_id: str, user_message: str) -> List[Dict[str, str]]:
        system = SYSTEM_PROMPT
        facts = self.memory.facts(user_id)
        if facts:
            system += "\n\nKnown facts about the user:\n" + "\n".join(
                f"- {key}: {value}" for key, value in facts.items()
            )
        retrieved = self.rag.search(user_message, k=RAG_TOP_K)
        if retrieved:
            system += "\n\nRelevant local documents:\n" + "\n\n".join(
                f"[{doc['source']}]\n{doc['text']}" for doc in retrieved
            )
        messages = [{"role": "system", "content": system}]
        messages.extend(self.memory.conversation_messages(conversation_id, CONTEXT_TURNS * 2))
        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_web_messages(self, user_id: str, conversation_id: str, query: str) -> List[Dict[str, str]]:
        if not self.web_enabled:
            raise WebSearchUnavailable(
                "Bing is not reachable, so web search is disabled.", disable=True
            )
        try:
            results = collect(query)
        except OSError as exc:
            raise WebSearchUnavailable(
                "Bing is not reachable, so web search is disabled.", disable=True
            ) from exc
        if not results:
            raise WebSearchUnavailable("Web search returned no readable results.")
        sources = "\n\n".join(
            f"[{index}] {item['title']}\nURL: {item['url']}\n{item['text']}"
            for index, item in enumerate(results, 1)
        )
        system = (
            SYSTEM_PROMPT.replace("You have no internet access during this conversation.", "")
            + "\n\nWeb research results follow. Answer using only supported information, "
            "note uncertainty, cite sources inline as [1], [2], etc., and include a "
            "Sources section listing the URLs."
            + "\n\n" + sources
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(self.memory.conversation_messages(conversation_id, CONTEXT_TURNS * 2))
        messages.append({"role": "user", "content": query})
        return messages

    @torch.inference_mode()
    def generate(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        web: bool = False,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("The model is not loaded")
        messages = (
            self._build_web_messages(user_id, conversation_id, user_message)
            if web
            else self._build_messages(
                user_id,
                conversation_id,
                self._with_attachments(user_message, attachments or []),
            )
        )
        if web and attachments:
            messages[-1]["content"] = self._with_attachments(user_message, attachments)
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        output = self.model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=TEMPERATURE > 0,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        new_tokens = output[0, inputs["input_ids"].shape[1] :]
        reply = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        return reply or "I’m here — could you say that another way?"

    def _extract_facts(self, user_id: str, message: str) -> None:
        patterns = [
            (r"\bmy name is\s+([A-Za-z][A-Za-z -]{1,40})", "name"),
            (r"\bi (?:like|love|prefer)\s+(.{2,80})[.!?]?$", "preference"),
            (r"\bi use\s+(.{2,80})[.!?]?$", "tools"),
        ]
        for pattern, key in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .,!?")
                if value and len(value) <= 100:
                    self.memory.set_fact(user_id, key, value)
                    break

    @classmethod
    def _needs_web_research(cls, message: str) -> bool:
        """Return whether the request is likely to benefit from fresh web data."""
        normalized = " ".join(message.casefold().split())
        return any(re.search(pattern, normalized) for pattern in cls._RESEARCH_PATTERNS)

    def chat(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        self.memory.upsert_user(user_id)
        self._extract_facts(user_id, user_message)
        explicit_web = user_message.startswith("/web ")
        prompt = user_message[5:].strip() if explicit_web else user_message
        if not prompt:
            raise ValueError("Use /web followed by a search query.")
        if explicit_web:
            reply = self.generate(user_id, conversation_id, prompt, web=True, attachments=attachments)
        elif self.web_enabled and self._needs_web_research(prompt):
            try:
                reply = self.generate(user_id, conversation_id, prompt, web=True, attachments=attachments)
            except WebSearchUnavailable as exc:
                if exc.disable:
                    self.web_enabled = False
                    os.environ["DEEPDEEP_ALLOW_WEB"] = "0"
                reply = self.generate(user_id, conversation_id, prompt, attachments=attachments)
        else:
            reply = self.generate(user_id, conversation_id, prompt, attachments=attachments)
        self.memory.add_message(user_id, conversation_id, "user", user_message)
        self.memory.add_message(user_id, conversation_id, "assistant", reply)
        return reply

    def remember_fact(self, user_id: str, key: str, value: str) -> None:
        self.memory.upsert_user(user_id)
        self.memory.set_fact(user_id, key, value)

    def close(self) -> None:
        self.memory.close()
