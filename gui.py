"""Flask web interface for DeepDeep."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from html import escape
import threading
from typing import Any

import markdown  # pyright: ignore[reportMissingModuleSource]
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

from brain import DeepDeepBrain


BG = "#f7f7f4"
SIDEBAR = "#efefeb"
PANEL = "#ffffff"
INK = "#262522"
MUTED = "#79766e"
LINE = "#deded7"
ACCENT = "#d86f55"
ACCENT_DARK = "#b95540"


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DeepDeep - your private local companion</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: {{ bg }}; color: {{ ink }}; min-height: 100vh; }
    button, input, textarea { font: inherit; }
    button, .button { cursor: pointer; }
    button:focus-visible, a:focus-visible, textarea:focus-visible { outline: 3px solid #efb3a3; outline-offset: 2px; }
    .app { display: grid; grid-template-columns: 286px minmax(0, 1fr); min-height: 100vh; }
    aside { display: flex; flex-direction: column; background: {{ sidebar }}; border-right: 1px solid {{ line }}; padding: 26px 18px 18px; }
    main { display: flex; flex-direction: column; width: min(100%, 1040px); min-height: 100vh; padding: 28px 42px 25px; margin: 0 auto; }
    .brand { display: flex; align-items: center; gap: 11px; margin: 0 8px 29px; }
    .mark { display: grid; place-items: center; flex: 0 0 auto; width: 38px; height: 38px; border-radius: 13px; background: {{ ink }}; color: #ffd5c7; font-size: 21px; font-weight: 700; box-shadow: 0 5px 12px #26252218; }
    .brand strong { display: block; font-size: 17px; letter-spacing: -.2px; }
    .brand .caption { display: block; margin-top: 3px; }
    .muted, .caption { color: {{ muted }}; }
    .caption { font-size: 12px; }
    .eyebrow { color: {{ muted }}; font-size: 10px; font-weight: 800; letter-spacing: 1.4px; }
    .new-chat, .send { border: 0; color: white; background: {{ ink }}; font-weight: 700; border-radius: 11px; transition: transform .18s ease, background .18s ease, box-shadow .18s ease; }
    .new-chat { width: 100%; padding: 12px 14px; text-align: left; margin-bottom: 28px; box-shadow: 0 4px 10px #26252210; }
    .new-chat:hover { background: #3c3a35; }
    .new-chat:active, .send:active { transform: translateY(1px); }
    .conversation-list { display: grid; gap: 3px; margin-top: 10px; max-height: calc(100vh - 190px); overflow-y: auto; }
    .conversation { display: flex; align-items: center; gap: 3px; min-width: 0; border-radius: 10px; transition: background .18s ease; }
    .conversation:hover { background: #e4e4de; }
    .conversation a { flex: 1; min-width: 0; color: #56544e; text-decoration: none; border-radius: 10px; padding: 10px 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
    .conversation a::before { content: ""; display: inline-block; width: 5px; height: 5px; margin: 0 8px 2px 0; border-radius: 50%; background: #c8c8c0; }
    .conversation a:hover, .conversation.active a { color: {{ ink }}; font-weight: 700; }
    .conversation.active { background: {{ panel }}; box-shadow: 0 3px 10px #2625220b; }
    .conversation.active a::before { background: {{ accent }}; }
    .conversation form { display: none; gap: 1px; margin-right: 5px; }
    .conversation:hover form, .conversation:focus-within form { display: flex; }
    .conversation form button { border: 0; background: transparent; color: {{ muted }}; padding: 5px; border-radius: 5px; }
    .conversation form button:hover { color: {{ ink }}; background: #d8d8d2; }
    .topbar { display: flex; align-items: center; gap: 9px; margin-bottom: 24px; }
    .breadcrumb { display: flex; align-items: center; gap: 9px; }
    .page-title { font-size: 18px; font-weight: 750; letter-spacing: -.25px; }
    .topbar-slash { color: #b7b4ac; }
    .status { display: inline-flex; align-items: center; gap: 7px; margin-left: auto; padding: 7px 11px; border: 1px solid {{ line }}; border-radius: 999px; background: #fbfbf9; color: {{ muted }}; font-size: 11px; font-weight: 700; }
    .status::first-letter { color: {{ accent }}; }
    .status.ready { color: #4f8a61; }
    .hero, .composer { background: {{ panel }}; border: 1px solid {{ line }}; border-radius: 20px; }
    .hero { position: relative; overflow: hidden; padding: 34px 36px 31px; box-shadow: 0 14px 36px #26252208; }
    .hero::after { content: "✦"; position: absolute; right: 35px; top: 15px; color: #f0d7ce; font-size: 84px; line-height: 1; transform: rotate(12deg); pointer-events: none; }
    .hero-intro { display: flex; gap: 18px; align-items: flex-start; position: relative; z-index: 1; }
    .hero .mark { width: 57px; height: 57px; border-radius: 18px; font-size: 28px; }
    .hero-kicker { margin: 2px 0 9px; color: {{ accent }}; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; }
    h1 { max-width: 650px; margin: 0 0 8px; font-size: clamp(29px, 4vw, 42px); line-height: 1.08; letter-spacing: -1.45px; }
    .hero p { max-width: 660px; margin: 0; color: {{ muted }}; font-size: 15px; line-height: 1.65; }
    .hero-note { display: flex; align-items: center; gap: 8px; margin-top: 19px; color: {{ muted }}; font-size: 12px; }
    .hero-note .dot, .privacy-dot { width: 6px; height: 6px; border-radius: 50%; background: {{ accent }}; box-shadow: 0 0 0 4px #f7e3dc; }
    hr { border: 0; border-top: 1px solid {{ line }}; margin: 27px 0 21px; }
    .suggestions-header { display: flex; align-items: baseline; justify-content: space-between; }
    .suggestions-header .caption { font-size: 11px; }
    .suggestions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 11px; }
    .suggestion { display: flex; align-items: center; gap: 10px; min-height: 65px; border: 1px solid {{ line }}; border-radius: 13px; background: {{ panel }}; padding: 12px 13px; text-align: left; color: {{ ink }}; font-size: 13px; line-height: 1.35; transition: border-color .18s ease, background .18s ease, transform .18s ease; }
    .suggestion:hover { border-color: {{ accent }}; background: #fffaf8; transform: translateY(-2px); }
    .suggestion-icon { display: grid; place-items: center; flex: 0 0 auto; width: 25px; height: 25px; border-radius: 8px; background: #f4ddd5; color: {{ accent_dark }}; font-size: 13px; }
    .suggestion .arrow { margin-left: auto; color: #b4b0a8; font-size: 16px; transition: transform .18s ease; }
    .suggestion:hover .arrow { color: {{ accent }}; transform: translate(2px, -2px); }
    .messages { flex: 1; overflow-y: auto; padding: 13px 4px 23px; }
    .message { margin: 0 0 25px; line-height: 1.62; animation: rise-in .24s ease both; }
    .message p { margin: 0 0 11px; }
    .message p:last-child { margin-bottom: 0; }
    .message.user { display: flex; justify-content: flex-end; }
    .message.user .bubble { max-width: min(80%, 700px); padding: 13px 16px; border: 1px solid #efd0c5; border-radius: 16px 16px 4px 16px; background: #f4ddd5; color: #55352d; box-shadow: 0 4px 12px #d86f5510; }
    .assistant { display: flex; gap: 12px; align-items: flex-start; }
    .assistant-avatar { display: grid; place-items: center; flex: 0 0 auto; width: 28px; height: 28px; margin-top: 1px; border: 1px solid #efc5b8; border-radius: 10px; background: #fff8f5; color: {{ accent }}; font-size: 15px; }
    .message-content { max-width: 760px; min-width: 0; }
    .speaker { margin: 1px 0 4px; color: #8a867e; font-size: 10px; font-weight: 800; letter-spacing: .8px; }
    .composer { padding: 13px 14px 12px; box-shadow: 0 8px 25px #26252212; transition: border-color .18s ease, box-shadow .18s ease; }
    .composer:focus-within { border-color: #cdbab2; box-shadow: 0 10px 30px #26252218; }
    .composer-meta { display: flex; align-items: center; justify-content: space-between; padding: 0 4px 4px; color: {{ muted }}; font-size: 11px; }
    .privacy-mini { display: inline-flex; align-items: center; gap: 7px; }
    .composer-row { display: flex; gap: 10px; align-items: flex-end; }
    textarea { min-height: 50px; max-height: 170px; flex: 1; resize: none; border: 0; outline: 0; padding: 10px 4px 6px; color: {{ ink }}; background: transparent; line-height: 1.45; }
    textarea::placeholder { color: #aaa69d; }
    .send { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-width: 76px; height: 43px; align-self: flex-end; padding: 0 13px; background: {{ accent }}; font-size: 13px; }
    .send:hover { background: {{ accent_dark }}; }
    .send:disabled { cursor: wait; opacity: .75; }
    .send-arrow { font-size: 18px; line-height: 1; }
    .hint { text-align: center; color: #a19e96; font-size: 11px; margin: 11px 0 0; }
    pre { overflow-x: auto; padding: 12px 14px; border: 1px solid #e4ddd7; border-radius: 10px; background: #f5f3f1; white-space: pre-wrap; }
    code { font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; background: #f3f0ee; border-radius: 5px; padding: 1px 4px; }
    pre code { background: transparent; padding: 0; }
    @keyframes rise-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
    @media (max-width: 900px) { .app { grid-template-columns: 230px minmax(0, 1fr); } main { padding-left: 28px; padding-right: 28px; } .suggestions { grid-template-columns: 1fr; } }
    @media (max-width: 700px) { .app { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid {{ line }}; padding: 16px 14px 14px; } .brand { margin-bottom: 17px; } .new-chat { margin-bottom: 17px; } .conversation-list { max-height: 142px; } main { min-height: auto; padding: 19px 14px 20px; } .topbar { margin-bottom: 17px; } .topbar .muted, .topbar-slash { display: none; } .hero { padding: 25px 21px 22px; border-radius: 17px; } .hero::after { right: 17px; top: 8px; font-size: 63px; } .hero-intro { gap: 13px; } .hero .mark { width: 45px; height: 45px; border-radius: 14px; font-size: 22px; } h1 { font-size: 31px; } .hero p { font-size: 14px; } .suggestions { grid-template-columns: 1fr; } .message.user .bubble { max-width: 90%; } .composer { border-radius: 17px; } .send { min-width: 45px; width: 45px; padding: 0; } .send-label { display: none; } }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand"><span class="mark">✦</span><div><strong>DeepDeep</strong><span class="caption">private local AI</span></div></div>
      <form method="post" action="{{ url_for('new_conversation') }}"><button class="new-chat" type="submit">＋ &nbsp; New conversation</button></form>
      <div class="eyebrow">CHATS</div>
      <div class="conversation-list">
        {% for conversation in conversations %}
          <div class="conversation {% if conversation.conversation_id == current_id %}active{% endif %}">
            <a href="{{ url_for('index', conversation_id=conversation.conversation_id) }}">{{ conversation.title }}</a>
            <form method="post" action="{{ url_for('rename_conversation', conversation_id=conversation.conversation_id) }}" onsubmit="return renameConversation(this);"><input type="hidden" name="title"><button title="Rename" type="button" onclick="this.form.requestSubmit()">✎</button></form>
            <form method="post" action="{{ url_for('delete_conversation', conversation_id=conversation.conversation_id) }}" onsubmit="return confirm('Delete this conversation and its messages?');"><button title="Delete" type="submit">×</button></form>
          </div>
        {% endfor %}
      </div>
    </aside>
    <main>
      <div class="topbar"><div class="breadcrumb"><span class="page-title">Your thinking space</span><span class="topbar-slash">/</span><span class="muted">DeepDeep</span></div><span id="status" class="status {% if loaded %}ready{% endif %}" aria-live="polite">● &nbsp;{{ status }}</span></div>
      {% if not messages %}
        <section class="hero">
          <div class="hero-intro"><span class="mark" aria-hidden="true">✦</span><div><div class="hero-kicker">PRIVATE LOCAL COMPANION</div><h1>A little space for big thoughts.</h1><p>Think out loud, make something, or find your way through a tricky problem. I’m here to help you find the next clear step.</p><div class="hero-note"><span class="dot"></span><span>Quiet, local, and ready when you are.</span></div></div></div>
          <hr><div class="suggestions-header"><div class="eyebrow">A PLACE TO START</div><span class="caption">Choose a prompt or make your own</span></div>
          <div class="suggestions">
            {% for prompt in prompts %}<button class="suggestion" type="button" onclick="usePrompt({{ prompt|tojson }})"><span class="suggestion-icon">✦</span><span>{{ prompt }}</span><span class="arrow">↗</span></button>{% endfor %}
          </div>
        </section>
      {% endif %}
      <section id="messages" class="messages">
        {% for message in messages %}
          <article class="message {% if message.role == 'user' %}user{% else %}assistant{% endif %}">
            {% if message.role == 'user' %}<div class="bubble">{{ markdown(message.content)|safe }}</div>
            {% else %}<div class="assistant-avatar" aria-hidden="true">✦</div><div class="message-content"><div class="speaker">DEEPDEEP</div>{{ markdown(message.content)|safe }}</div>{% endif %}
          </article>
        {% endfor %}
      </section>
      <form id="chat-form" class="composer" method="post" action="{{ url_for('chat', conversation_id=current_id) }}">
        <div class="composer-meta"><span>What’s on your mind?</span><span class="privacy-mini"><span class="privacy-dot"></span> Stays on this device</span></div>
        <div class="composer-row"><textarea id="message" name="message" placeholder="Start anywhere..." rows="1" required {% if not loaded %}disabled{% endif %}></textarea><button id="send" class="send" type="submit" {% if not loaded %}disabled{% endif %}><span class="send-label">Send</span><span class="send-arrow">↑</span></button></div>
      </form>
      <div class="hint">Enter to send · Shift + Enter for a new line</div>
    </main>
  </div>
  <script>
    const status = document.getElementById("status");
    const input = document.getElementById("message");
    const send = document.getElementById("send");
    function resizeInput() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 170) + "px"; }
    async function refreshStatus() {
      try {
        const response = await fetch("{{ url_for('status') }}");
        const data = await response.json();
        status.textContent = "●  " + data.status;
        status.classList.toggle("ready", data.loaded);
        input.disabled = !data.loaded;
        send.disabled = !data.loaded;
      } catch (_) { /* The local server may be briefly busy while the model starts. */ }
    }
    function usePrompt(prompt) { input.value = prompt; resizeInput(); input.focus(); }
    function renameConversation(form) { const title = prompt("Conversation name:"); if (title === null) return false; form.title.value = title; return Boolean(title.trim()); }
    document.getElementById("chat-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!input.value.trim() || send.disabled) return;
      send.disabled = true; input.disabled = true; status.textContent = "●  Thinking locally..."; send.querySelector(".send-label").textContent = "Thinking";
      const response = await fetch(event.target.action, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message: input.value}) });
      const data = await response.json();
      if (response.ok) window.location.href = data.redirect;
      else { alert(data.error || "Could not send message."); send.disabled = false; input.disabled = false; send.querySelector(".send-label").textContent = "Send"; await refreshStatus(); }
    });
    input.addEventListener("input", resizeInput);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.getElementById("chat-form").requestSubmit(); }
    });
    setInterval(refreshStatus, 2000);
    resizeInput();
    document.getElementById("messages").scrollTop = document.getElementById("messages").scrollHeight;
  </script>
</body>
</html>
"""


def _markdown_html(text: str) -> str:
    escaped = escape(str(text))
    return markdown.markdown(escaped, extensions=["fenced_code", "nl2br", "tables"], output_format="html5")


def create_app(brain: DeepDeepBrain, user_id: str) -> Flask:
    app = Flask(__name__)
    state: dict[str, Any] = {"loaded": brain.model is not None and brain.tokenizer is not None, "error": None}
    model_lock = threading.Lock()
    memory_lock = threading.Lock()
    executor = ThreadPoolExecutor(max_workers=1)

    def conversations() -> list[dict[str, str]]:
        with memory_lock:
            return brain.memory.list_conversations(user_id)

    def ensure_conversation() -> str:
        existing = conversations()
        if existing:
            return existing[0]["conversation_id"]
        with memory_lock:
            return brain.memory.create_conversation(user_id)

    def load_model() -> None:
        try:
            brain.load_model()
            state["loaded"] = True
        except Exception as exc:
            state["error"] = str(exc)

    if not state["loaded"]:
        executor.submit(load_model)

    @app.get("/")
    def index() -> str:
        all_conversations = conversations()
        if not all_conversations:
            current_id = ensure_conversation()
            all_conversations = conversations()
        else:
            current_id = request.args.get("conversation_id") or all_conversations[0]["conversation_id"]
        if not any(item["conversation_id"] == current_id for item in all_conversations):
            return redirect(url_for("index"))
        with memory_lock:
            messages = brain.memory.conversation_messages(current_id, 1000)
        return render_template_string(
            PAGE, conversations=conversations(), current_id=current_id, messages=messages,
            loaded=state["loaded"], status="Local · ready" if state["loaded"] else ("Could not load the model" if state["error"] else "Warming up local model..."),
            prompts=["Help me think through an idea", "Turn these notes into a clear plan", "Explain this simply: "],
            markdown=_markdown_html, bg=BG, sidebar=SIDEBAR, panel=PANEL, ink=INK, muted=MUTED,
            line=LINE, accent=ACCENT, accent_dark=ACCENT_DARK,
        )

    @app.get("/status")
    def status() -> Any:
        return jsonify(loaded=state["loaded"], status="Local · ready" if state["loaded"] else ("Could not load the model" if state["error"] else "Warming up local model..."), error=state["error"])

    @app.post("/conversations/new")
    def new_conversation() -> Any:
        with memory_lock:
            conversation_id = brain.memory.create_conversation(user_id)
        return redirect(url_for("index", conversation_id=conversation_id))

    @app.post("/conversations/<conversation_id>/delete")
    def delete_conversation(conversation_id: str) -> Any:
        with memory_lock:
            brain.memory.delete_conversation(user_id, conversation_id)
        return redirect(url_for("index"))

    @app.post("/conversations/<conversation_id>/rename")
    def rename_conversation(conversation_id: str) -> Any:
        try:
            with memory_lock:
                brain.memory.rename_conversation(user_id, conversation_id, request.form.get("title", ""))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return redirect(url_for("index", conversation_id=conversation_id))

    @app.post("/chat/<conversation_id>")
    def chat(conversation_id: str) -> Any:
        payload = request.get_json(silent=True) or request.form
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify(error="Message cannot be empty"), 400
        if not state["loaded"]:
            return jsonify(error=state["error"] or "The model is still warming up"), 503
        try:
            with model_lock:
                brain.chat(user_id, conversation_id, message)
        except Exception as exc:
            return jsonify(error=str(exc)), 500
        return jsonify(redirect=url_for("index", conversation_id=conversation_id))

    @app.teardown_appcontext
    def close_executor(_exception: BaseException | None) -> None:
        # Flask's development server keeps the process alive, so the executor is
        # intentionally not shut down for each request.
        return None

    return app


def run_gui(brain: DeepDeepBrain, user_id: str) -> None:
    """Run the local web interface."""
    app = create_app(brain, user_id)
    try:
        app.run(host="127.0.0.1", port=5000, threaded=True)
    finally:
        brain.close()
