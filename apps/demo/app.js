/**
 * InsightAI demo — ChatGPT-style UI with server-backed sessions.
 */

const STORAGE_KEY = "insightai_demo_v1";

const phaseLabels = {
  generating_sql: "Generating SQL…",
  executing_query: "Running query…",
  generating_answer: "Writing answer…",
  retrieving_documents: "Searching knowledge…",
  classifying_route: "Routing question…",
};

const els = {
  sessionList: document.getElementById("sessionList"),
  messages: document.getElementById("messages"),
  messagesInner: document.getElementById("messagesInner"),
  emptyState: document.getElementById("emptyState"),
  composer: document.getElementById("composer"),
  composerInput: document.getElementById("composerInput"),
  sendBtn: document.getElementById("sendBtn"),
  newChatBtn: document.getElementById("newChatBtn"),
  settingsBtn: document.getElementById("settingsBtn"),
  settingsModal: document.getElementById("settingsModal"),
  settingsClose: document.getElementById("settingsClose"),
  settingsSave: document.getElementById("settingsSave"),
  apiUrl: document.getElementById("apiUrl"),
  apiKey: document.getElementById("apiKey"),
  includeSql: document.getElementById("includeSql"),
  mediaBaseUrl: document.getElementById("mediaBaseUrl"),
  chatTitle: document.getElementById("chatTitle"),
  sidebar: document.getElementById("sidebar"),
  menuBtn: document.getElementById("menuBtn"),
};

let state = loadState();
let activeSessionId = state.activeSessionId || null;
let streaming = false;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {
    /* ignore */
  }
  return {
    apiUrl: "http://localhost:8000",
    apiKey: "",
    includeSql: false,
    mediaBaseUrl: "",
    sessions: [],
    activeSessionId: null,
  };
}

function saveState() {
  state.apiUrl = els.apiUrl.value.trim() || state.apiUrl;
  state.apiKey = els.apiKey.value.trim();
  state.includeSql = els.includeSql.checked;
  state.mediaBaseUrl = els.mediaBaseUrl.value.trim();
  state.activeSessionId = activeSessionId;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function baseUrl() {
  return (els.apiUrl.value.trim() || state.apiUrl).replace(/\/$/, "");
}

function headers() {
  const h = { "Content-Type": "application/json" };
  const key = els.apiKey.value.trim() || state.apiKey;
  if (key) h["X-API-Key"] = key;
  return h;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function resolvedMediaBase() {
  return (els.mediaBaseUrl.value.trim() || state.mediaBaseUrl || "").replace(/\/$/, "");
}

/** Turn SQL/answer file paths into markdown images when a media base URL is set. */
function linkifyMediaPaths(text) {
  const base = resolvedMediaBase();
  if (!base || !text) return text;
  let out = text;
  out = out.replace(
    /\b(image[1-5]|attachment_file|file)\s*:\s*(\S+)/gi,
    (_, label, path) => {
      const clean = path.replace(/^["']|["']$/g, "");
      if (/^https?:\/\//i.test(clean)) {
        return `${label}: ${clean}\n\n![](${clean})`;
      }
      const url = `${base}/${clean.replace(/^\//, "")}`;
      return `${label}: ${clean}\n\n![](${url})`;
    }
  );
  out = out.replace(
    /(^|[\s(])(uploads\/[^\s)\n]+\.(?:jpg|jpeg|png|gif|webp|bmp))/gi,
    (match, prefix, path) => `${prefix}![](${base}/${path})`
  );
  return out;
}

function renderMarkdown(text) {
  const raw = linkifyMediaPaths(text || "");
  if (typeof marked === "undefined") {
    return escapeHtml(raw);
  }
  marked.setOptions({ breaks: true, gfm: true });
  const html = marked.parse(raw);
  if (typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(html, {
      ADD_TAGS: ["img"],
      ADD_ATTR: ["src", "alt", "title", "loading"],
    });
  }
  return html;
}

function setMessageContent(el, text, { markdown = true } = {}) {
  if (markdown && text) {
    el.classList.add("markdown");
    el.innerHTML = renderMarkdown(text);
  } else {
    el.classList.remove("markdown");
    el.textContent = text || "";
  }
}

function sessionTitle(entry) {
  return entry.title || "New chat";
}

function upsertSessionEntry(id, title) {
  const now = Date.now();
  let entry = state.sessions.find((s) => s.id === id);
  if (!entry) {
    entry = { id, title: title || null, updatedAt: now };
    state.sessions.unshift(entry);
  } else {
    if (title) entry.title = title;
    entry.updatedAt = now;
  }
  state.sessions.sort((a, b) => b.updatedAt - a.updatedAt);
  saveState();
  renderSessionList();
}

function renderSessionList() {
  els.sessionList.innerHTML = "";
  for (const entry of state.sessions) {
    const wrap = document.createElement("div");
    wrap.className =
      "session-item" + (entry.id === activeSessionId ? " active" : "");

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "session-btn";
    btn.textContent = sessionTitle(entry);
    btn.title = sessionTitle(entry);
    btn.addEventListener("click", () => selectSession(entry.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "session-delete";
    del.setAttribute("aria-label", "Delete chat");
    del.textContent = "×";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(entry.id);
    });

    wrap.appendChild(btn);
    wrap.appendChild(del);
    els.sessionList.appendChild(wrap);
  }
}

function setComposerEnabled(enabled) {
  els.composerInput.disabled = !enabled;
  els.sendBtn.disabled = !enabled || !els.composerInput.value.trim();
  streaming = !enabled;
}

function resizeComposer() {
  const ta = els.composerInput;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
}

function showEmpty(show) {
  els.emptyState.hidden = !show;
}

function clearMessages() {
  els.messagesInner
    .querySelectorAll(".message")
    .forEach((n) => n.remove());
}

function renderMessage({ role, content, metaHtml }) {
  const row = document.createElement("div");
  row.className = `message ${role}`;
  const label = role === "user" ? "You" : "AI";
  row.innerHTML = `
    <div class="avatar" aria-hidden="true">${role === "user" ? "U" : "AI"}</div>
    <div class="message-body">
      <div class="message-content"></div>
      ${metaHtml ? `<div class="message-meta">${metaHtml}</div>` : ""}
    </div>
  `;
  const contentEl = row.querySelector(".message-content");
  if (role === "assistant") {
    setMessageContent(contentEl, content);
  } else {
    contentEl.textContent = content;
  }
  els.messagesInner.appendChild(row);
  showEmpty(false);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function formatMeta(data) {
  const parts = [];
  if (data.route) parts.push(`Route: ${data.route}`);
  if (data.row_count != null) {
    parts.push(`Rows: ${data.row_count}${data.truncation_noted ? " (truncated)" : ""}`);
  }
  const t = data.timings || {};
  if (t.total_ms != null) parts.push(`${Math.round(t.total_ms)} ms`);

  let html = escapeHtml(parts.join(" · "));
  if (data.sources && data.sources.length) {
    const cites = data.sources
      .map((s) => s.source_path || s.title || s.id)
      .slice(0, 5)
      .join(", ");
    html += `<br>Sources: ${escapeHtml(cites)}`;
  }
  if (data.sql) {
    html += `<details><summary>SQL</summary><pre>${escapeHtml(data.sql)}</pre></details>`;
  }
  return html;
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${baseUrl()}${path}`, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      data.detail?.message ||
      (typeof data.detail === "string" ? data.detail : null) ||
      res.statusText;
    throw new Error(msg);
  }
  return data;
}

async function createSession() {
  const session = await apiFetch("/api/v1/chat/sessions", {
    method: "POST",
    body: JSON.stringify({}),
  });
  upsertSessionEntry(session.id, null);
  return session.id;
}

async function loadMessages(sessionId) {
  const data = await apiFetch(
    `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages?limit=200`
  );
  clearMessages();
  if (!data.messages.length) {
    showEmpty(true);
    return;
  }
  showEmpty(false);
  for (const msg of data.messages) {
    const meta =
      msg.role === "assistant" && (msg.row_count != null || msg.sql)
        ? formatMeta({
            row_count: msg.row_count,
            sql: state.includeSql || els.includeSql.checked ? msg.sql : null,
            route: null,
            timings: {},
          })
        : "";
    renderMessage({
      role: msg.role,
      content: msg.content,
      metaHtml: meta,
    });
  }
  els.messages.scrollTop = els.messages.scrollHeight;
}

async function selectSession(sessionId) {
  if (streaming) return;
  activeSessionId = sessionId;
  saveState();
  renderSessionList();
  els.chatTitle.textContent = sessionTitle(
    state.sessions.find((s) => s.id === sessionId) || {}
  );
  clearMessages();
  showEmpty(true);
  try {
    await loadMessages(sessionId);
  } catch (err) {
    renderMessage({ role: "assistant", content: `Error: ${err.message}` });
    rowClassError();
  }
  closeSidebarMobile();
}

function rowClassError() {
  const last = els.messagesInner.querySelector(".message:last-child");
  if (last) last.classList.add("error");
}

function startNewChat() {
  if (streaming) return;
  activeSessionId = null;
  saveState();
  renderSessionList();
  clearMessages();
  showEmpty(true);
  els.chatTitle.textContent = "InsightAI";
  els.composerInput.focus();
  closeSidebarMobile();
}

async function deleteSession(sessionId) {
  if (streaming) return;
  try {
    await fetch(`${baseUrl()}/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: headers(),
    });
  } catch (_) {
    /* best effort */
  }
  state.sessions = state.sessions.filter((s) => s.id !== sessionId);
  saveState();
  if (activeSessionId === sessionId) startNewChat();
  else renderSessionList();
}

function parseSseBlock(block) {
  let name = null;
  let dataLine = null;
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7).trim();
    if (line.startsWith("data: ")) dataLine = line.slice(6);
  }
  if (!name || !dataLine) return null;
  return { name, data: JSON.parse(dataLine) };
}

async function sendMessage() {
  const question = els.composerInput.value.trim();
  if (!question || streaming) return;

  saveState();
  setComposerEnabled(false);
  els.composerInput.value = "";
  resizeComposer();

  let sessionId = activeSessionId;
  if (!sessionId) {
    try {
      sessionId = await createSession();
      activeSessionId = sessionId;
      saveState();
      renderSessionList();
    } catch (err) {
      renderMessage({ role: "assistant", content: `Error: ${err.message}` });
      rowClassError();
      setComposerEnabled(true);
      return;
    }
  }

  const title =
    state.sessions.find((s) => s.id === sessionId)?.title ||
    question.slice(0, 48) + (question.length > 48 ? "…" : "");
  upsertSessionEntry(sessionId, title);
  els.chatTitle.textContent = sessionTitle(
    state.sessions.find((s) => s.id === sessionId) || { title }
  );

  renderMessage({ role: "user", content: question });
  const assistantRow = renderMessage({ role: "assistant", content: "" });
  const contentEl = assistantRow.querySelector(".message-content");
  const statusEl = document.createElement("div");
  statusEl.className = "status-pill";
  assistantRow.querySelector(".message-body").prepend(statusEl);

  const body = {
    question,
    session_id: sessionId,
    include_sql: els.includeSql.checked,
  };

  try {
    const res = await fetch(`${baseUrl()}/api/v1/chat/stream`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail?.message || data.detail || res.statusText);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let donePayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const block of parts) {
        const event = parseSseBlock(block);
        if (!event) continue;
        if (event.name === "status") {
          statusEl.textContent =
            phaseLabels[event.data.phase] || event.data.phase;
        } else if (event.name === "token") {
          statusEl.remove();
          contentEl.textContent += event.data.text || "";
          els.messages.scrollTop = els.messages.scrollHeight;
        } else if (event.name === "done") {
          donePayload = event.data;
        } else if (event.name === "error") {
          throw new Error(event.data.error_message || "Stream error");
        }
      }
    }

    statusEl.remove();
    if (donePayload) {
      const answerText = contentEl.textContent || donePayload.answer || "";
      if (answerText) {
        setMessageContent(contentEl, answerText);
      }
      const metaHtml = formatMeta(donePayload);
      if (metaHtml) {
        const metaDiv = document.createElement("div");
        metaDiv.className = "message-meta";
        metaDiv.innerHTML = metaHtml;
        assistantRow.querySelector(".message-body").appendChild(metaDiv);
      }
    }
    await loadMessages(sessionId);
  } catch (err) {
    statusEl.remove();
    contentEl.textContent = err.message;
    assistantRow.classList.add("error");
  } finally {
    setComposerEnabled(true);
    els.composerInput.focus();
  }
}

function openSettings() {
  els.settingsModal.classList.add("open");
}

function closeSettings() {
  els.settingsModal.classList.remove("open");
}

function closeSidebarMobile() {
  els.sidebar.classList.remove("open");
}

function init() {
  els.apiUrl.value = state.apiUrl;
  els.apiKey.value = state.apiKey;
  els.includeSql.checked = state.includeSql;
  els.mediaBaseUrl.value = state.mediaBaseUrl || "";
  renderSessionList();

  if (activeSessionId && state.sessions.some((s) => s.id === activeSessionId)) {
    selectSession(activeSessionId);
  } else {
    startNewChat();
  }

  els.newChatBtn.addEventListener("click", startNewChat);
  els.settingsBtn.addEventListener("click", openSettings);
  els.settingsClose.addEventListener("click", closeSettings);
  els.settingsSave.addEventListener("click", () => {
    saveState();
    closeSettings();
  });
  els.settingsModal.addEventListener("click", (e) => {
    if (e.target === els.settingsModal) closeSettings();
  });
  els.menuBtn.addEventListener("click", () => {
    els.sidebar.classList.toggle("open");
  });

  els.sendBtn.addEventListener("click", sendMessage);
  els.composerInput.addEventListener("input", () => {
    resizeComposer();
    els.sendBtn.disabled = streaming || !els.composerInput.value.trim();
  });
  els.composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

init();
