"""Terminal interface for DeepDeep."""

from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

from brain import DeepDeepBrain
from colorama import Fore, Style, init


init()

TYPE_DELAY = 0.015


HELP = """Commands:
  /help                         show this help
  /clear                        clear conversation history
  /remember KEY=VALUE           save a fact for this user
  /add PATH                     index a local text/markdown/code file
  /sources                      list indexed document sources
  /quit                         exit DeepDeep
"""


def type_response(text: str, delay: float = TYPE_DELAY) -> None:
    """Print an assistant response with color and a typewriter effect."""
    sys.stdout.write(f"{Fore.CYAN}DeepDeep: {Style.RESET_ALL}")
    sys.stdout.flush()
    for character in text:
        sys.stdout.write(character)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n\n")
    sys.stdout.flush()


def run_cli(brain: DeepDeepBrain, user_id: str) -> None:
    print(f"{Fore.GREEN}DeepDeep is ready.{Style.RESET_ALL} Type /help for commands; /quit to exit.\n")
    conversations = brain.memory.list_conversations(user_id)
    conversation_id = (
        conversations[0]["conversation_id"]
        if conversations
        else brain.memory.create_conversation(user_id)
    )
    try:
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text == "/quit":
                break
            if text == "/help":
                print(HELP)
                continue
            if text == "/clear":
                brain.memory.clear_history(user_id)
                print("DeepDeep: conversation history cleared.\n")
                continue
            if text == "/sources":
                sources = brain.rag.sources()
                print("\n".join(sources) if sources else "No local documents indexed.")
                print()
                continue
            if text.startswith("/remember "):
                payload = text[len("/remember ") :]
                if "=" not in payload:
                    print("Use /remember key=value\n")
                    continue
                key, value = payload.split("=", 1)
                brain.remember_fact(user_id, key, value)
                print("DeepDeep: remembered.\n")
                continue
            if text.startswith("/add "):
                try:
                    path = Path(shlex.split(text[len("/add ") :])[0]).expanduser().resolve()
                    count = brain.rag.add_file(path)
                    print(f"DeepDeep: indexed {count} chunk(s) from {path}.\n")
                except (IndexError, OSError, ValueError) as exc:
                    print(f"DeepDeep: could not index that file: {exc}\n")
                continue
            try:
                type_response(brain.chat(user_id, conversation_id, text))
            except Exception as exc:
                print(f"DeepDeep: I hit an error: {exc}\n")
    finally:
        brain.close()
