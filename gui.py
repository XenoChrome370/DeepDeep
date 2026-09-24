"""Optional standard-library desktop interface."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from brain import DeepDeepBrain


class DeepDeepWindow:
    def __init__(self, brain: DeepDeepBrain, user_id: str):
        self.brain = brain
        self.user_id = user_id
        self.root = tk.Tk()
        self.root.title("DeepDeep — private local AI")
        self.root.geometry("760x600")
        self.results: queue.Queue = queue.Queue()
        self.loaded = False
        self.busy = False

        self.status = tk.StringVar(value="Loading local model…")
        tk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x", padx=12, pady=(12, 4))
        self.display = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, state="disabled", font=("Arial", 12))
        self.display.pack(fill="both", expand=True, padx=12, pady=4)
        row = tk.Frame(self.root)
        row.pack(fill="x", padx=12, pady=12)
        self.entry = tk.Entry(row, font=("Arial", 12), state="disabled")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _event: self.send())
        self.button = tk.Button(row, text="Send", command=self.send, state="disabled")
        self.button.pack(side="right", padx=(8, 0))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)
        threading.Thread(target=self._load, daemon=True).start()

    def _on_close(self) -> None:
        try:
            self.brain.close()
        finally:
            self.root.destroy()

    def _append(self, speaker: str, text: str) -> None:
        self.display.configure(state="normal")
        self.display.insert(tk.END, f"{speaker}: {text}\n\n")
        self.display.configure(state="disabled")
        self.display.see(tk.END)

    def _load(self) -> None:
        try:
            if self.brain.model is None or self.brain.tokenizer is None:
                self.brain.load_model()
            self.results.put(("loaded", None))
        except Exception as exc:
            self.results.put(("load_error", str(exc)))

    def send(self) -> None:
        if not self.loaded or self.busy:
            return
        message = self.entry.get().strip()
        if not message:
            return
        self.entry.delete(0, tk.END)
        self._append("You", message)
        self.busy = True
        self.entry.configure(state="disabled")
        self.button.configure(state="disabled")
        threading.Thread(target=self._answer, args=(message,), daemon=True).start()

    def _answer(self, message: str) -> None:
        try:
            self.results.put(("reply", self.brain.chat(self.user_id, message)))
        except Exception as exc:
            self.results.put(("reply_error", str(exc)))

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.results.get_nowait()
                if kind == "loaded":
                    self.loaded = True
                    self.status.set("DeepDeep is ready — fully local")
                    self.button.configure(state="normal")
                    self.entry.configure(state="normal")
                    self.entry.focus_set()
                    self._append("DeepDeep", "hey — what would you like to work on?")
                elif kind == "reply":
                    self.busy = False
                    self._append("DeepDeep", value)
                    self.button.configure(state="normal")
                    self.entry.configure(state="normal")
                    self.entry.focus_set()
                elif kind == "reply_error":
                    self.busy = False
                    self._append("DeepDeep", f"[error] {value}")
                    self.button.configure(state="normal")
                    self.entry.configure(state="normal")
                    self.entry.focus_set()
                else:
                    self.status.set("Could not load the model")
                    self.loaded = False
                    self.button.configure(state="disabled")
                    self.entry.configure(state="disabled")
                    messagebox.showerror("DeepDeep", value)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def run(self) -> None:
        self.root.mainloop()


def run_gui(brain: DeepDeepBrain, user_id: str) -> None:
    window = DeepDeepWindow(brain, user_id)
    window.run()

