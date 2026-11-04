/* EXAMGEN AI — subject assistant chat panel.
 *
 * A grounded chatbot scoped to the subject workspace that is currently open.
 * Answers are composed server-side from the workspace's own uploaded coursework
 * and returned with citations, so the panel never shows unattributed claims.
 *
 * Conversations are persisted server-side; the active session id is remembered
 * per workspace so a refresh resumes the same thread.
 */
(function (global) {
  "use strict";

  const { api, el, clear, escapeHtml } = global.EXAMGEN;
  const sessionKey = (workspaceId) => "examgen.chat.session." + workspaceId;

  const state = {
    context: null,       // { id, name } of the open subject, or null
    sessionId: "",
    open: false,
    busy: false,
    prompts: [],
    greeting: "Ask me about this subject's coursework.",
  };

  let panel, launcher, logEl, composer, input, sendBtn, subjectLabel, statusEl;

  /* ------------------------------------------------------------------ build */

  function buildLauncher() {
    launcher = el("button", {
      class: "chat-launcher", type: "button",
      "aria-haspopup": "dialog", "aria-expanded": "false",
      "aria-label": "Open the subject assistant",
      title: "Subject assistant",
    }, [
      el("span", { class: "chat-launcher-mark", "aria-hidden": "true", text: "💬" }),
      el("span", { class: "chat-launcher-text", text: "Ask assistant" }),
    ]);
    launcher.addEventListener("click", () => toggle(!state.open));
    document.body.appendChild(launcher);
  }

  function buildPanel() {
    subjectLabel = el("small", { class: "chat-subject", text: "No subject open" });
    statusEl = el("p", { class: "chat-status sr-only", role: "status", "aria-live": "polite" });

    const newBtn = el("button", { class: "btn btn-sm btn-ghost", type: "button",
      text: "New chat", title: "Start a new conversation",
      onclick: () => newConversation() });
    const closeBtn = el("button", { class: "btn btn-sm btn-ghost chat-close", type: "button",
      text: "✕", "aria-label": "Close assistant", onclick: () => toggle(false) });

    const header = el("div", { class: "chat-head" }, [
      el("div", { class: "chat-head-text" }, [
        el("strong", { text: "Subject assistant" }),
        subjectLabel,
      ]),
      el("div", { class: "chat-head-actions" }, [newBtn, closeBtn]),
    ]);

    logEl = el("div", { class: "chat-log", role: "log", "aria-live": "polite",
      "aria-label": "Conversation" });

    input = el("textarea", { class: "chat-input", rows: 2,
      placeholder: "Ask about a concept, topic, gap or your progress…",
      "aria-label": "Your question" });
    input.addEventListener("keydown", function (event) {
      // Enter sends; Shift+Enter inserts a newline.
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    });

    sendBtn = el("button", { class: "btn btn-primary chat-send", type: "button",
      text: "Send", onclick: () => send() });

    composer = el("div", { class: "chat-composer" }, [
      input,
      el("div", { class: "chat-composer-actions" }, [
        el("span", { class: "tiny muted", text: "Enter to send · Shift+Enter for a new line" }),
        sendBtn,
      ]),
    ]);

    panel = el("div", { class: "chat-panel hidden", role: "dialog", "aria-modal": "false",
      "aria-label": "Subject assistant" }, [header, logEl, composer, statusEl]);

    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.stopPropagation(); toggle(false); }
    });

    document.body.appendChild(panel);
  }

  /* --------------------------------------------------------------- lifecycle */

  async function boot() {
    buildLauncher();
    buildPanel();
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && state.open) toggle(false);
    });
    try {
      const data = await api.get("/api/assistant/prompts");
      if (data && data.prompts) { state.prompts = data.prompts; state.greeting = data.greeting; }
    } catch (_) { /* prompts are optional; the panel still works without them */ }
    renderIntro();
  }

  function setContext(context) {
    const next = context && context.id ? { id: context.id, name: context.name || "this subject" } : null;
    const changed = (state.context && state.context.id) !== (next && next.id);
    state.context = next;
    if (!changed) return;
    state.sessionId = next ? (localStorage.getItem(sessionKey(next.id)) || "") : "";
    if (subjectLabel) {
      subjectLabel.textContent = next ? next.name : "No subject open";
    }
    if (next) {
      state.open = true;
      syncOpen();
      resumeOrIntro();
    } else {
      state.open = false;
      syncOpen();
    }
  }

  function toggle(open) {
    state.open = open;
    syncOpen();
    if (open) {
      if (state.context) resumeOrIntro();
      input.focus();
    } else {
      launcher.focus();
    }
  }

  function syncOpen() {
    panel.classList.toggle("hidden", !state.open);
    launcher.setAttribute("aria-expanded", String(state.open));
    launcher.classList.toggle("is-open", state.open);
  }

  async function resumeOrIntro() {
    if (!state.context) { renderIntro(); return; }
    if (state.sessionId) {
      try {
        const detail = await api.get(
          "/api/workspaces/" + state.context.id + "/assistant/sessions/" + state.sessionId);
        renderMessages(detail.messages);
        return;
      } catch (_) {
        state.sessionId = "";
        localStorage.removeItem(sessionKey(state.context.id));
      }
    }
    await newConversation();
  }

  async function newConversation() {
    if (!state.context) { renderIntro(); return; }
    clear(logEl);
    try {
      const detail = await api.post(
        "/api/workspaces/" + state.context.id + "/assistant/sessions", {});
      state.sessionId = detail.id;
      localStorage.setItem(sessionKey(state.context.id), detail.id);
      renderMessages(detail.messages);
    } catch (error) {
      logEl.appendChild(el("div", { class: "alert alert-danger", text: error.message }));
    }
  }

  /* ---------------------------------------------------------------- rendering */

  function renderIntro() {
    if (!logEl) return;
    clear(logEl);
    const message = state.context
      ? state.greeting
      : "Open a subject workspace first, then ask me about that subject's coursework. "
        + "I only answer from the material you uploaded for the subject you are in.";
    logEl.appendChild(bubble("assistant", message, [], []));
    if (state.context) renderPrompts(state.prompts);
  }

  function renderMessages(messages) {
    clear(logEl);
    messages.forEach(function (message) {
      logEl.appendChild(bubble(message.role, message.content,
        message.citations || [], message.suggestions || []));
    });
    scrollToEnd();
  }

  function bubble(role, content, citations, suggestions) {
    const wrap = el("div", { class: "chat-msg chat-msg-" + role });
    const body = el("div", { class: "chat-bubble" });
    // Content is composed from coursework text: render as text, never HTML.
    body.appendChild(el("div", { class: "chat-text", text: content }));
    if (citations && citations.length) {
      const sources = el("div", { class: "chat-sources" }, [
        el("span", { class: "tiny muted", text: "Sources" }),
      ]);
      citations.forEach(function (citation) {
        const label = citation.document_name
          + (citation.heading ? " › " + citation.heading : "")
          + (citation.page ? " (p. " + citation.page + ")" : "");
        sources.appendChild(el("span", {
          class: "badge badge-info", title: citation.excerpt || "", text: label }));
      });
      body.appendChild(sources);
    }
    if (suggestions && suggestions.length) {
      const chips = el("div", { class: "chat-suggestions" });
      suggestions.forEach(function (suggestion) {
        chips.appendChild(el("button", { class: "chat-chip", type: "button",
          text: suggestion, onclick: function () { ask(suggestion); } }));
      });
      body.appendChild(chips);
    }
    wrap.appendChild(body);
    return wrap;
  }

  function renderPrompts(prompts) {
    if (!prompts || !prompts.length) return;
    const chips = el("div", { class: "chat-suggestions chat-suggestions-intro" });
    prompts.slice(0, 5).forEach(function (prompt) {
      chips.appendChild(el("button", { class: "chat-chip", type: "button",
        text: prompt, onclick: function () { ask(prompt); } }));
    });
    logEl.appendChild(chips);
  }

  function scrollToEnd() { logEl.scrollTop = logEl.scrollHeight; }

  function setBusy(busy) {
    state.busy = busy;
    sendBtn.disabled = busy;
    input.disabled = busy;
    sendBtn.textContent = busy ? "Thinking…" : "Send";
  }

  /* -------------------------------------------------------------------- ask */

  function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    ask(text);
  }

  async function ask(question) {
    if (state.busy) return;
    if (!state.context) {
      logEl.appendChild(bubble("assistant",
        "Open a subject workspace first — I answer only from the coursework of the "
        + "subject you are currently in.", [], []));
      scrollToEnd();
      return;
    }
    const existing = logEl.querySelector(".chat-suggestions-intro");
    if (existing) existing.remove();

    logEl.appendChild(bubble("user", question, [], []));
    scrollToEnd();
    setBusy(true);
    statusEl.textContent = "Assistant is composing an answer";

    try {
      const result = await api.post("/api/workspaces/" + state.context.id + "/assistant/ask",
        { message: question, session_id: state.sessionId || null });
      if (result.session && result.session.id) {
        state.sessionId = result.session.id;
        localStorage.setItem(sessionKey(state.context.id), result.session.id);
      }
      const message = result.message;
      logEl.appendChild(bubble("assistant", message.content,
        message.citations || [], message.suggestions || []));
      statusEl.textContent = message.grounded
        ? "Answer grounded in your coursework"
        : "No matching coursework found";
    } catch (error) {
      logEl.appendChild(el("div", { class: "alert alert-danger", text: error.message }));
      statusEl.textContent = "The assistant could not answer";
    } finally {
      setBusy(false);
      scrollToEnd();
      input.focus();
    }
  }

  global.EXAMGEN = global.EXAMGEN || {};
  global.EXAMGEN.chat = { setContext: setContext, toggle: toggle, state: state };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
