"""Flask web interface for DeepDeep."""

from __future__ import annotations

from html import escape, unescape
import re
from typing import Any
from urllib.parse import urlsplit

import markdown  # pyright: ignore[reportMissingModuleSource]
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

from application import (
    AttachmentError,
    ConversationNotFound,
    ConversationService,
    ModelUnavailable,
)
from brain import DeepDeepBrain


BG = "#f7f7f4"
SIDEBAR = "#efefeb"
PANEL = "#ffffff"
INK = "#262522"
MUTED = "#79766e"
LINE = "#deded7"
ACCENT = "#d86f55"
ACCENT_DARK = "#b95540"

GUI_COMMANDS = [
    {"command": "/web", "template": "/web ", "description": "Search the web and summarize cited sources"},
    {"command": "/add", "template": "/add ", "description": "Index a local text, Markdown, or code file"},
    {"command": "/remember", "template": "/remember ", "description": "Save a fact about you for future chats"},
    {"command": "/sources", "template": "/sources", "description": "List the documents indexed locally"},
    {"command": "/clear", "template": "/clear", "description": "Clear this conversation's history"},
]


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DeepDeep</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: {{ bg }}; color: {{ ink }}; min-height: 100vh; }
    button, input, textarea { font: inherit; }
    button, .button { cursor: pointer; }
    button:focus-visible, a:focus-visible, textarea:focus-visible { outline: 3px solid #efb3a3; outline-offset: 2px; }
    .app { display: grid; grid-template-columns: 278px minmax(0, 1fr); height: 100vh; min-height: 100vh; }
    aside { position: sticky; top: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: linear-gradient(180deg, {{ sidebar }} 0%, {{ bg }} 100%); border-right: 1px solid {{ line }}; padding: 26px 18px 18px; }
    main { display: flex; flex-direction: column; width: min(100%, 1080px); height: 100vh; min-height: 0; overflow: hidden; padding: 28px 46px 25px; margin: 0 auto; }
    .brand { display: flex; align-items: center; gap: 11px; margin: 0 8px 31px; }
    .mark { display: grid; place-items: center; flex: 0 0 auto; width: 38px; height: 38px; border-radius: 13px; background: {{ ink }}; color: #ffd5c7; font-size: 21px; font-weight: 700; box-shadow: 0 5px 12px #26252218; }
    .brand strong { display: block; font-size: 17px; letter-spacing: -.2px; }
    .brand .caption { display: block; margin-top: 3px; }
    .muted, .caption { color: {{ muted }}; }
    .caption { font-size: 12px; }
    .eyebrow { color: {{ muted }}; font-size: 10px; font-weight: 800; letter-spacing: 1.4px; }
    .new-chat, .send { border: 0; color: white; background: {{ ink }}; font-weight: 700; border-radius: 11px; transition: transform .18s ease, background .18s ease, box-shadow .18s ease; }
    .new-chat { width: 100%; padding: 12px 14px; text-align: left; margin-bottom: 28px; box-shadow: 0 4px 10px #26252210; letter-spacing: -.1px; }
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
    .hero { position: relative; overflow: hidden; padding: 38px 39px 33px; background: linear-gradient(135deg, {{ panel }} 0%, #fffaf8 100%); box-shadow: 0 14px 36px #26252208; }
    .hero::before { content: ""; position: absolute; width: 260px; height: 260px; right: -95px; bottom: -155px; border-radius: 50%; background: #f4ddd588; pointer-events: none; }
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
    .messages { flex: 1; min-height: 0; overflow-y: auto; padding: 13px 4px 23px; }
    .message { margin: 0 0 25px; line-height: 1.62; animation: rise-in .24s ease both; }
    .message p { margin: 0 0 11px; }
    .message p:last-child { margin-bottom: 0; }
    .message.user { display: flex; justify-content: flex-end; }
    .message.user .bubble { max-width: min(80%, 700px); padding: 13px 16px; border: 1px solid #efd0c5; border-radius: 16px 16px 4px 16px; background: #f4ddd5; color: #55352d; box-shadow: 0 4px 12px #d86f5510; }
    .message.user .bubble.optimistic-bubble { white-space: pre-wrap; }
    .message-attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .message-attachment { display: inline-flex; align-items: center; gap: 5px; padding: 5px 8px; border: 1px solid #e7bfb2; border-radius: 7px; background: #fff7f3; color: #704338; font-size: 11px; white-space: normal; }
    .assistant { display: flex; gap: 12px; align-items: flex-start; }
    .assistant-avatar { display: grid; place-items: center; flex: 0 0 auto; width: 28px; height: 28px; margin-top: 1px; border: 1px solid #efc5b8; border-radius: 10px; background: #fff8f5; color: {{ accent }}; font-size: 15px; }
    .message-content { max-width: 760px; min-width: 0; padding-top: 1px; }
    .speaker { margin: 1px 0 4px; color: #8a867e; font-size: 10px; font-weight: 800; letter-spacing: .8px; }
    .thinking { display: none; gap: 12px; align-items: flex-start; margin: 0 0 25px; color: {{ muted }}; animation: rise-in .24s ease both; }
    .thinking.visible { display: flex; }
    .thinking-avatar { display: grid; place-items: center; flex: 0 0 auto; width: 28px; height: 28px; margin-top: 1px; border: 1px solid #efc5b8; border-radius: 10px; background: #fff8f5; color: {{ accent }}; }
    .thinking-body { min-width: 0; }
    .thinking-title { margin: 1px 0 6px; color: #8a867e; font-size: 10px; font-weight: 800; letter-spacing: .8px; }
    .thinking-stage { display: flex; align-items: center; gap: 8px; font-size: 13px; }
    .thinking-dots { display: inline-flex; gap: 3px; }
    .thinking-dots i { width: 4px; height: 4px; border-radius: 50%; background: {{ accent }}; animation: thinking-pulse 1.1s infinite ease-in-out; }
    .thinking-dots i:nth-child(2) { animation-delay: .15s; }
    .thinking-dots i:nth-child(3) { animation-delay: .3s; }
    .thinking-time { margin-top: 4px; color: #aaa69d; font-size: 11px; }
    .composer { padding: 13px 14px 12px; box-shadow: 0 8px 25px #26252212; transition: border-color .18s ease, box-shadow .18s ease; }
    .composer:focus-within { border-color: #cdbab2; box-shadow: 0 10px 30px #26252218; }
    .composer-meta { display: flex; align-items: center; justify-content: space-between; padding: 0 4px 4px; color: {{ muted }}; font-size: 11px; }
    .privacy-mini { display: inline-flex; align-items: center; gap: 7px; }
    .composer-wrap { position: relative; }
    .command-menu { position: absolute; right: 0; bottom: calc(100% + 10px); z-index: 5; display: none; width: min(390px, 100%); overflow: hidden; border: 1px solid {{ line }}; border-radius: 14px; background: {{ panel }}; box-shadow: 0 14px 35px #26252220; }
    .command-menu.open { display: block; }
    .command-menu-header { padding: 11px 13px 8px; color: {{ muted }}; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
    .command-option { display: flex; align-items: center; gap: 10px; width: 100%; border: 0; border-top: 1px solid #f0f0eb; background: transparent; padding: 10px 13px; text-align: left; color: {{ ink }}; }
    .command-option:hover, .command-option.active { background: #fff8f5; }
    .command-icon { display: grid; place-items: center; flex: 0 0 auto; width: 28px; height: 28px; border-radius: 9px; background: #f4ddd5; color: {{ accent_dark }}; font-size: 13px; }
    .command-copy { min-width: 0; }
    .command-name { display: block; font-size: 13px; font-weight: 750; }
    .command-description { display: block; margin-top: 2px; overflow: hidden; color: {{ muted }}; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
    .command-key { margin-left: auto; color: #aaa69d; font-family: "SFMono-Regular", Consolas, monospace; font-size: 11px; }
    .composer-row { display: flex; gap: 10px; align-items: flex-end; }
    .attachments { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 4px 5px; }
    .attachment { display: inline-flex; align-items: center; gap: 5px; padding: 5px 8px; border-radius: 7px; background: #f4ddd5; color: #704338; font-size: 11px; }
    .attachment button { border: 0; padding: 0; background: transparent; color: #9b6254; font-size: 15px; line-height: 1; }
    .attach { display: grid; place-items: center; flex: 0 0 auto; width: 43px; height: 43px; border: 1px solid {{ line }}; border-radius: 11px; color: {{ accent_dark }}; font-size: 22px; cursor: pointer; }
    .attach:hover { background: #fff8f5; border-color: {{ accent }}; }
    .attach input { display: none; }
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
    @keyframes thinking-pulse { 0%, 80%, 100% { opacity: .3; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }
    @media (max-width: 900px) { .app { grid-template-columns: 230px minmax(0, 1fr); } main { padding-left: 28px; padding-right: 28px; } .suggestions { grid-template-columns: 1fr; } }
    @media (max-width: 700px) { .app { grid-template-columns: 1fr; height: auto; } aside { position: static; height: auto; overflow: visible; border-right: 0; border-bottom: 1px solid {{ line }}; padding: 16px 14px 14px; } .brand { margin-bottom: 17px; } .new-chat { margin-bottom: 17px; } .conversation-list { max-height: 142px; } main { height: auto; min-height: auto; overflow: visible; padding: 19px 14px 20px; } .topbar { margin-bottom: 17px; } .topbar .muted, .topbar-slash { display: none; } .hero { padding: 25px 21px 22px; border-radius: 17px; } .hero::after { right: 17px; top: 8px; font-size: 63px; } .hero-intro { gap: 13px; } .hero .mark { width: 45px; height: 45px; border-radius: 14px; font-size: 22px; } h1 { font-size: 31px; } .hero p { font-size: 14px; } .suggestions { grid-template-columns: 1fr; } .message.user .bubble { max-width: 90%; } .composer { border-radius: 17px; } .send { min-width: 45px; width: 45px; padding: 0; } .send-label { display: none; } }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand"><span class="mark">✦</span><div><strong>DeepDeep</strong><span class="caption">your local thinking partner</span></div></div>
      <form method="post" action="{{ url_for('new_conversation') }}"><button class="new-chat" type="submit">＋ &nbsp; Start a new thought</button></form>
      <div class="eyebrow">YOUR THREADS</div>
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
      <div class="topbar"><div class="breadcrumb"><span class="page-title">A quiet place to think</span><span class="topbar-slash">/</span><span class="muted">DeepDeep</span></div><span id="status" class="status {% if loaded %}ready{% endif %}" aria-live="polite">● &nbsp;{{ status }}</span></div>
      {% if not messages %}
        <section class="hero">
          <div class="hero-intro"><span class="mark" aria-hidden="true">✦</span><div><div class="hero-kicker">THOUGHTFUL LOCAL COMPANION</div><h1>Let’s make the next step clearer.</h1><p>Bring me a rough idea, a half-written note, or a tricky question. We’ll sort through it together—calmly, clearly, and one useful step at a time.</p><div class="hero-note"><span class="dot"></span><span>Private by default · unhurried by design.</span></div></div></div>
          <hr><div class="suggestions-header"><div class="eyebrow">A PLACE TO BEGIN</div><span class="caption">Pick a direction, or start anywhere</span></div>
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
        <div id="thinking" class="thinking" role="status" aria-live="polite" aria-hidden="true">
          <div class="thinking-avatar" aria-hidden="true">✦</div>
          <div class="thinking-body">
            <div class="thinking-title">DEEPDEEP IS WITH YOU</div>
            <div class="thinking-stage"><span id="thinking-stage">Reading your message</span><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span></div>
            <div id="thinking-time" class="thinking-time">0s</div>
          </div>
        </div>
      </section>
      <form id="chat-form" class="composer" method="post" action="{{ url_for('chat', conversation_id=current_id) }}">
        <div class="composer-meta"><span>What are you working through?</span><span class="privacy-mini"><span class="privacy-dot"></span> Private on this device</span></div>
        <div class="composer-wrap">
          <div id="command-menu" class="command-menu" role="listbox" aria-label="Commands">
            <div class="command-menu-header">COMMANDS</div>
            {% for command in commands %}
              <button class="command-option" type="button" role="option" data-command="{{ command.command }}" data-template="{{ command.template }}" data-description="{{ command.description }}">
                <span class="command-icon">/</span><span class="command-copy"><span class="command-name">{{ command.command }}</span><span class="command-description">{{ command.description }}</span></span><span class="command-key">{{ command.template }}</span>
              </button>
            {% endfor %}
          </div>
          <div id="attachments" class="attachments" aria-live="polite"></div>
          <div class="composer-row"><textarea id="message" name="message" placeholder="Ask a question, paste a draft, or start with a thought…" rows="1" required {% if not loaded %}disabled{% endif %}></textarea><label class="attach" title="Attach text, Markdown, code, JSON, or CSV files"><input id="file-input" type="file" multiple accept=".txt,.md,.py,.json,.csv,text/plain,text/markdown,text/csv,application/json" {% if not loaded %}disabled{% endif %}>＋</label><button id="send" class="send" type="submit" {% if not loaded %}disabled{% endif %}><span class="send-label">Send</span><span class="send-arrow">↑</span></button></div>
        </div>
      </form>
      <div class="hint">Enter to send · Shift + Enter for a new line · Type / for tools</div>
    </main>
  </div>
  <script>
    const status = document.getElementById("status");
    const input = document.getElementById("message");
    const fileInput = document.getElementById("file-input");
    const attachmentList = document.getElementById("attachments");
    const send = document.getElementById("send");
    const thinking = document.getElementById("thinking");
    const thinkingStage = document.getElementById("thinking-stage");
    const thinkingTime = document.getElementById("thinking-time");
    const thinkingStages = ["Taking in what you mean", "Checking our local context", "Looking through local notes", "Finding a useful next step"];
    const commandMenu = document.getElementById("command-menu");
    const commandOptions = [...commandMenu.querySelectorAll(".command-option")];
    const messages = document.getElementById("messages");
    let activeCommandIndex = 0;
    let thinkingTimer;
    let thinkingStageTimer;
    let thinkingStartedAt;
    let requestInFlight = false;
    let selectedFiles = [];
    function renderAttachments() {
      attachmentList.replaceChildren(...selectedFiles.map((file, index) => {
        const chip = document.createElement("span");
        chip.className = "attachment";
        chip.textContent = file.name;
        const remove = document.createElement("button");
        remove.type = "button"; remove.setAttribute("aria-label", "Remove " + file.name); remove.textContent = "×";
        remove.addEventListener("click", () => { selectedFiles.splice(index, 1); renderAttachments(); });
        chip.appendChild(remove);
        return chip;
      }));
    }
    fileInput.addEventListener("change", () => {
      selectedFiles = [...selectedFiles, ...fileInput.files];
      renderAttachments();
      fileInput.value = "";
    });
    function resizeInput() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 170) + "px"; }
    async function refreshStatus() {
      try {
        const response = await fetch("{{ url_for('status') }}");
        const data = await response.json();
        status.textContent = "●  " + data.status;
        status.classList.toggle("ready", data.loaded);
        const canInteract = data.loaded && !requestInFlight;
        input.disabled = !canInteract;
        send.disabled = !canInteract;
      } catch (_) { /* The local server may be briefly busy while the model starts. */ }
    }
    function usePrompt(prompt) { input.value = prompt; resizeInput(); input.focus(); }
    function closeCommandMenu() { commandMenu.classList.remove("open"); input.removeAttribute("aria-activedescendant"); }
    function updateCommandMenu() {
      const value = input.value;
      const match = value.match(/^\/([^\s]*)$/);
      if (!match) { closeCommandMenu(); return; }
      const query = match[1].toLowerCase();
      commandOptions.forEach((option) => {
        option.hidden = query && !option.dataset.command.slice(1).startsWith(query);
        option.classList.remove("active");
      });
      const visible = commandOptions.filter((option) => !option.hidden);
      if (!visible.length) { closeCommandMenu(); return; }
      activeCommandIndex = Math.min(activeCommandIndex, visible.length - 1);
      visible[activeCommandIndex].classList.add("active");
      commandMenu.classList.add("open");
    }
    function selectCommand(option) {
      input.value = option.dataset.template;
      closeCommandMenu();
      resizeInput();
      input.focus();
    }
    commandOptions.forEach((option) => option.addEventListener("click", () => selectCommand(option)));
    function renameConversation(form) { const title = prompt("Conversation name:"); if (title === null) return false; form.title.value = title; return Boolean(title.trim()); }
    function startThinking() {
      thinkingStartedAt = Date.now();
      let stageIndex = 0;
      thinkingStage.textContent = thinkingStages[stageIndex];
      thinkingTime.textContent = "0s";
      thinking.classList.add("visible");
      thinking.setAttribute("aria-hidden", "false");
      thinkingStageTimer = setInterval(() => {
        stageIndex = Math.min(stageIndex + 1, thinkingStages.length - 1);
        thinkingStage.textContent = thinkingStages[stageIndex];
      }, 1400);
      thinkingTimer = setInterval(() => {
        thinkingTime.textContent = Math.floor((Date.now() - thinkingStartedAt) / 1000) + "s";
      }, 250);
      requestAnimationFrame(scrollMessagesToBottom);
    }
    function stopThinking() {
      clearInterval(thinkingTimer);
      clearInterval(thinkingStageTimer);
      thinking.classList.remove("visible");
      thinking.setAttribute("aria-hidden", "true");
    }
    function appendOptimisticMessage(message, files) {
      const article = document.createElement("article");
      article.className = "message user optimistic-message";
      const bubble = document.createElement("div");
      bubble.className = "bubble optimistic-bubble";
      bubble.textContent = message;
      if (files.length) {
        const attachments = document.createElement("div");
        attachments.className = "message-attachments";
        attachments.setAttribute("aria-label", "Attachments");
        files.forEach((file) => {
          const attachment = document.createElement("span");
          attachment.className = "message-attachment";
          attachment.textContent = "📎 " + file.name;
          attachments.appendChild(attachment);
        });
        bubble.appendChild(attachments);
      }
      article.appendChild(bubble);
      messages.insertBefore(article, thinking);
      requestAnimationFrame(scrollMessagesToBottom);
      return article;
    }
    document.getElementById("chat-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!input.value.trim() || send.disabled || requestInFlight) return;
      const message = input.value.trim();
      const files = [...selectedFiles];
      const optimisticMessage = appendOptimisticMessage(message, files);
      input.value = "";
      selectedFiles = [];
      renderAttachments();
      closeCommandMenu();
      resizeInput();
      requestInFlight = true;
      send.disabled = true; input.disabled = true; status.textContent = "●  Thinking locally..."; send.querySelector(".send-label").textContent = "Thinking"; startThinking();
      try {
        const body = new FormData();
        body.append("message", message);
        files.forEach((file) => body.append("files", file, file.name));
        const response = await fetch(event.target.action, { method: "POST", body });
        const data = await response.json();
        if (response.ok) window.location.href = data.redirect;
        else throw new Error(data.error || "Could not send message.");
      } catch (error) {
        stopThinking();
        optimisticMessage.remove();
        requestInFlight = false;
        input.value = message;
        selectedFiles = files;
        renderAttachments();
        resizeInput();
        alert(error.message || "Could not send message.");
        send.disabled = false; input.disabled = false; send.querySelector(".send-label").textContent = "Send";
        await refreshStatus();
      }
    });
    input.addEventListener("input", () => { resizeInput(); updateCommandMenu(); });
    input.addEventListener("keydown", (event) => {
      const visible = commandOptions.filter((option) => !option.hidden);
      if (commandMenu.classList.contains("open") && visible.length) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          activeCommandIndex = (activeCommandIndex + (event.key === "ArrowDown" ? 1 : -1) + visible.length) % visible.length;
          visible.forEach((option, index) => option.classList.toggle("active", index === activeCommandIndex));
          return;
        }
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          selectCommand(visible[activeCommandIndex]);
          return;
        }
        if (event.key === "Escape") { event.preventDefault(); closeCommandMenu(); return; }
      }
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.getElementById("chat-form").requestSubmit(); }
    });
    document.addEventListener("click", (event) => { if (!commandMenu.contains(event.target) && event.target !== input) closeCommandMenu(); });
    setInterval(refreshStatus, 2000);
    resizeInput();
    function scrollMessagesToBottom() {
      const messages = document.getElementById("messages");
      messages.scrollTo({ top: messages.scrollHeight, behavior: "auto" });
    }
    requestAnimationFrame(scrollMessagesToBottom);
  </script>
</body>
</html>
"""


def _markdown_html(text: str) -> str:
    escaped = escape(str(text))
    rendered = markdown.markdown(
        escaped, extensions=["fenced_code", "nl2br", "tables"], output_format="html5"
    )

    # Python-Markdown escapes raw HTML but does not restrict URL schemes in
    # generated links/images. Keep only harmless web/mail/relative URLs.
    url_attribute = re.compile(r"(?P<name>href|src)=(?P<quote>[\"'])(?P<value>.*?)(?P=quote)", re.IGNORECASE)

    def safe_attribute(match: re.Match[str]) -> str:
        value = unescape(match.group("value")).strip()
        parsed = urlsplit(value)
        scheme = parsed.scheme.casefold()
        safe = (
            scheme in {"", "http", "https", "mailto"}
            and not value.startswith("//")
        )
        if not safe:
            value = "#"
        return f'{match.group("name")}="{escape(value, quote=True)}"'

    return url_attribute.sub(safe_attribute, rendered)


def create_app(brain: DeepDeepBrain, user_id: str) -> Flask:
    app = Flask(__name__)
    service = ConversationService(brain, user_id)
    app.extensions["deepdeep_service"] = service
    service.start_model_loading()

    @app.get("/")
    def index() -> str:
        all_conversations = service.list_conversations()
        if not all_conversations:
            current_id = service.ensure_conversation()
            all_conversations = service.list_conversations()
        else:
            current_id = request.args.get("conversation_id") or all_conversations[0]["conversation_id"]
        if not any(item["conversation_id"] == current_id for item in all_conversations):
            return redirect(url_for("index"))
        messages = service.conversation_messages(current_id)
        return render_template_string(
            PAGE, conversations=all_conversations, current_id=current_id, messages=messages,
            loaded=service.loaded, status=service.status,
            prompts=["Help me untangle an idea", "Turn these notes into a clear plan", "Explain this simply: "],
            commands=GUI_COMMANDS,
            markdown=_markdown_html, bg=BG, sidebar=SIDEBAR, panel=PANEL, ink=INK, muted=MUTED,
            line=LINE, accent=ACCENT, accent_dark=ACCENT_DARK,
        )

    @app.get("/status")
    def status() -> Any:
        return jsonify(loaded=service.loaded, status=service.status, error=service.state["error"])

    @app.post("/conversations/new")
    def new_conversation() -> Any:
        conversation_id = service.create_conversation()
        return redirect(url_for("index", conversation_id=conversation_id))

    @app.post("/conversations/<conversation_id>/delete")
    def delete_conversation(conversation_id: str) -> Any:
        try:
            service.delete_conversation(conversation_id)
        except ConversationNotFound:
            return jsonify(error="Conversation not found"), 404
        return redirect(url_for("index"))

    @app.post("/conversations/<conversation_id>/rename")
    def rename_conversation(conversation_id: str) -> Any:
        try:
            service.rename_conversation(conversation_id, request.form.get("title", ""))
        except ConversationNotFound:
            return jsonify(error="Conversation not found"), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return redirect(url_for("index", conversation_id=conversation_id))

    @app.post("/chat/<conversation_id>")
    def chat(conversation_id: str) -> Any:
        payload = request.get_json(silent=True) or request.form
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify(error="Message cannot be empty"), 400
        try:
            service.handle_message(conversation_id, message, request.files.getlist("files"))
        except ConversationNotFound:
            return jsonify(error="Conversation not found"), 404
        except (AttachmentError, ModelUnavailable, ValueError) as exc:
            status_code = 503 if isinstance(exc, ModelUnavailable) else 400
            return jsonify(error=str(exc)), status_code
        except Exception as exc:
            return jsonify(error=str(exc)), 500
        return jsonify(redirect=url_for("index", conversation_id=conversation_id))

    return app


def run_gui(brain: DeepDeepBrain, user_id: str) -> None:
    """Run the local web interface."""
    app = create_app(brain, user_id)
    service: ConversationService = app.extensions["deepdeep_service"]
    try:
        app.run(host="127.0.0.1", port=5000, threaded=True)
    finally:
        service.close()
