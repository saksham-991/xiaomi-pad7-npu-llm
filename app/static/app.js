const $ = (s) => document.querySelector(s);
const msgsEl = $("#messages");
const input = $("#input");
const sendBtn = $("#sendBtn");
const stopBtn = $("#stopBtn");
const chipSearch = $("#chipSearch");
const chipThink = $("#chipThink");
const sessionList = $("#sessionList");
const ringFg = $("#ringFg");
const ctxPct = $("#ctxPct");
const tokHint = $("#tokHint");

const LS_KEY = "pad7npu.sessions.v1";
const LS_ACTIVE = "pad7npu.active.v1";
let sessions = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
let activeId = localStorage.getItem(LS_ACTIVE) || null;
let busy = false;
let abortCtl = null;

let activeChatHandler = null;

function npuEvent(raw) {
  let ev;
  try { ev = JSON.parse(raw); } catch { return; }
  if (ev.type === "engine" || ev.type === "model") return engineEvent(ev);
  if (activeChatHandler) activeChatHandler(ev);
}

function engineEvent(ev) {
  const ov = document.getElementById("setup");
  if (!ov) return;
  const bar = ov.querySelector(".setup-bar div");
  const msg = ov.querySelector(".setup-msg");
  const btn = ov.querySelector(".setup-btn");
  if (ev.type === "model") {
    if (ev.state === "progress") {
      msg.textContent = "Downloading model… " + (ev.pct >= 0 ? ev.pct + "%" : Math.round(ev.done / 1048576) + " MB");
      if (bar) bar.style.width = (ev.pct >= 0 ? ev.pct : 40) + "%";
    } else if (ev.state === "ready") {
      msg.textContent = "Model ready. Starting NPU engine…";
      if (window.NPU) window.NPU.ensureEngine();
    } else if (ev.state === "error") {
      msg.textContent = "Download failed: " + (ev.msg || "unknown");
      btn.disabled = false;
    }
    return;
  }
  if (ev.type === "engine") {
    if (ev.state === "no_model") {
      msg.textContent = "First run: download the 660 MB NPU model (one time).";
      btn.textContent = "Download model";
      btn.disabled = false;
      btn.onclick = () => { btn.disabled = true; msg.textContent = "Starting download…"; window.NPU.downloadModel(); };
      if (bar) bar.style.width = "0%";
    } else if (ev.state === "starting") {
      msg.textContent = "Loading model onto the Hexagon NPU…";
      btn.disabled = true;
    } else if (ev.state === "ready") {
      ov.classList.add("hide");
      setTimeout(() => ov.remove(), 420);
      toast("NPU engine ready");
    } else if (ev.state === "error") {
      msg.textContent = "Engine error: " + (ev.msg || "unknown").slice(-220);
      btn.textContent = "Retry";
      btn.disabled = false;
      btn.onclick = () => { btn.disabled = true; window.NPU.ensureEngine(); };
    }
  }
}

function showSetup() {
  if (document.getElementById("setup")) return;
  const d = document.createElement("div");
  d.id = "setup";
  d.innerHTML = `<div class="setup-card">
      <div class="setup-orb"></div>
      <div class="setup-title">Local NPU Chat</div>
      <div class="setup-msg">Checking engine…</div>
      <div class="setup-bar"><div></div></div>
      <button class="setup-btn" disabled>Please wait…</button>
    </div>`;
  document.body.appendChild(d);
}
window.__npuEvent = npuEvent;


function uid() { return Math.random().toString(36).slice(2, 10) + Date.now().toString(36); }
function save() { localStorage.setItem(LS_KEY, JSON.stringify(sessions)); localStorage.setItem(LS_ACTIVE, activeId || ""); }
function active() { return sessions.find(s => s.id === activeId); }

function newSession() {
  const s = { id: uid(), title: "New chat", messages: [], created: Date.now() };
  sessions.unshift(s); activeId = s.id; save(); renderSessions(); renderChat();
  input.focus();
}

function renderSessions() {
  sessionList.innerHTML = "";
  sessions.forEach(s => {
    const el = document.createElement("div");
    el.className = "session" + (s.id === activeId ? " active" : "");
    el.innerHTML = `<span class="t"></span><button class="del" title="Delete">✕</button>`;
    el.querySelector(".t").textContent = s.title;
    el.onclick = () => { activeId = s.id; save(); renderSessions(); renderChat(); };
    el.querySelector(".del").onclick = (e) => {
      e.stopPropagation();
      sessions = sessions.filter(x => x.id !== s.id);
      if (activeId === s.id) activeId = sessions[0]?.id || null;
      save(); renderSessions(); renderChat();
    };
    sessionList.appendChild(el);
  });
}

function renderChat() {
  msgsEl.innerHTML = "";
  if (!active()?.messages.length) {
    msgsEl.appendChild(buildEmpty());
    bindSuggests();
    return;
  }
  active().messages.forEach(m => renderMessage(m.role, m.content, m.reasoning, m.ts, false));
  scrollBottom(true);
}

function buildEmpty() {
  const d = document.createElement("div");
  d.className = "empty";
  d.innerHTML = `
    <div class="empty-orb"></div>
    <h1>Your private AI,<br>on the NPU.</h1>
    <p>Runs 100% on the Hexagon tensor processor. No cloud. No GPU.</p>
    <div class="suggests">
      <button class="suggest" data-q="Explain how Qualcomm Hexagon HMX differs from HVX for matrix multiplies.">How HMX differs from HVX</button>
      <button class="suggest" data-q="search latest Android 16 QPR2 changes">Search: Android 16 QPR2</button>
      <button class="suggest" data-q="Write a Kotlin snippet for a Material You themed Compose app with dynamic color.">Compose + Material You</button>
    </div>`;
  return d;
}
function bindSuggests() {
  msgsEl.querySelectorAll(".suggest").forEach(b => b.onclick = () => { input.value = b.dataset.q; autoresize(); send(); });
}

function esc(s) { return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function md(s) {
  let h = esc(s);
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code}</code></pre>`);
  h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/\*([^*]+)\*/g, "<i>$1</i>");
  h = h.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return h;
}

function renderMessage(role, content, reasoning, ts, anim = true) {
  const tpl = $("#msgTpl").content.cloneNode(true);
  const el = tpl.querySelector(".msg");
  el.classList.add(role);
  if (!anim) el.style.animation = "none";
  el.querySelector(".avatar").textContent = role === "user" ? "You" : "AI";
  el.querySelector(".time").textContent = new Date(ts || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const contentEl = el.querySelector(".content");
  contentEl.innerHTML = md(content || "");
  if (reasoning) {
    const r = el.querySelector(".reasoning");
    r.classList.remove("hidden");
    r.querySelector(".reasoning-body").textContent = reasoning;
  }
  el.querySelector(".copy-btn").onclick = () => {
    navigator.clipboard.writeText(content || "").then(() => toast("Copied"));
  };
  el.querySelector(".reasoning-head").onclick = () => el.querySelector(".reasoning").classList.toggle("open");
  msgsEl.appendChild(el);
  return el;
}

function scrollBottom(force) {
  const near = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight < 220;
  if (force || near) msgsEl.scrollTop = msgsEl.scrollHeight;
}
function toast(text, err) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}
function setCtx(used, ctx) {
  const pct = Math.min(100, Math.round(used / ctx * 100));
  ctxPct.textContent = pct + "%";
  ringFg.style.strokeDashoffset = String(100 - pct);
  tokHint.textContent = used;
}

function autoresize() {
  input.style.height = "auto";
  input.style.height = Math.min(180, input.scrollHeight) + "px";
}

chipSearch.onclick = () => chipSearch.classList.toggle("on");
chipThink.onclick = () => chipThink.classList.toggle("on");
$("#newChat").onclick = () => { newSession(); $("#sidebar").classList.remove("open"); };
$("#menuBtn").onclick = () => $("#sidebar").classList.toggle("open");
$("#exportBtn").onclick = () => {
  const blob = new Blob([JSON.stringify(sessions, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "pad7-npu-chats.json";
  a.click();
};
$("#importBtn").onclick = () => $("#importFile").click();
$("#importFile").onchange = (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => {
    try {
      const data = JSON.parse(r.result);
      if (Array.isArray(data)) { sessions = data.concat(sessions); save(); renderSessions(); toast("Chats imported"); }
    } catch { toast("Invalid file", true); }
  };
  r.readAsText(f);
};
input.addEventListener("input", autoresize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
sendBtn.onclick = () => send();
stopBtn.onclick = () => { if (abortCtl) abortCtl.abort(); };

async function send() {
  if (busy) return;
  const text = input.value.trim();
  if (!text) return;
  if (!active()) newSession();
  const s = active();
  const useSearch = chipSearch.classList.contains("on") || /^\s*search\b/i.test(text);
  const think = chipThink.classList.contains("on");

  if (s.messages.length === 0) s.title = text.slice(0, 42);
  const userMsg = { role: "user", content: text, ts: Date.now() };
  s.messages.push(userMsg);
  save(); renderSessions();

  if (s.messages.length === 1) renderChat(); else renderMessage("user", text, null, userMsg.ts);
  input.value = ""; autoresize();
  scrollBottom(true);

  busy = true; sendBtn.disabled = true; stopBtn.classList.remove("hidden");

  const thinkRow = document.createElement("div");
  thinkRow.className = "msg assistant";
  thinkRow.innerHTML = `<div class="avatar">AI</div>
    <div class="bubble"><div class="thinking-bubble">
      <span class="think-orb"></span><span class="shimmer">Thinking</span>
      <span class="tdots"><i></i><i></i><i></i></span>
      <span class="elapsed" style="font-size:12px;opacity:.6"></span>
    </div></div>`;
  msgsEl.appendChild(thinkRow);
  scrollBottom(true);
  const started = Date.now();
  const elapsedEl = thinkRow.querySelector(".elapsed");
  const timer = setInterval(() => {
    elapsedEl.textContent = ((Date.now() - started) / 1000).toFixed(1) + "s";
  }, 100);

  let assistantEl = null, contentEl = null, reasoningEl = null, reasoningBody = null, contentBuf = "", reasoningBuf = "";
  const ensureAssistant = () => {
    if (assistantEl) return;
    thinkRow.remove();
    assistantEl = renderMessage("assistant", "", reasoningBuf, Date.now());
    contentEl = assistantEl.querySelector(".content");
    reasoningEl = assistantEl.querySelector(".reasoning");
    reasoningBody = reasoningEl.querySelector(".reasoning-body");
    if (reasoningBuf) reasoningEl.classList.remove("hidden");
  };

  const finish = () => {
    ensureAssistant();
    contentEl.innerHTML = md(contentBuf);
    s.messages.push({ role: "assistant", content: contentBuf, reasoning: reasoningBuf, ts: Date.now() });
    save();
    clearInterval(timer);
    busy = false; sendBtn.disabled = false; stopBtn.classList.add("hidden");
    scrollBottom();
  };
  const handleEvent = (ev) => {
    if (ev.type === "reasoning") {
      reasoningBuf += ev.text;
      ensureAssistant();
      reasoningEl.classList.remove("hidden");
      reasoningBody.textContent = reasoningBuf;
      reasoningBody.scrollTop = reasoningBody.scrollHeight;
    } else if (ev.type === "content") {
      contentBuf += ev.text;
      ensureAssistant();
      contentEl.innerHTML = md(contentBuf) + '<span class="cursor"></span>';
      scrollBottom();
    } else if (ev.type === "usage") {
      setCtx(ev.tokens, ev.ctx);
    } else if (ev.type === "search") {
      toast(ev.error ? "Search failed: " + ev.error : `Searched the web · ${ev.count} results`);
    } else if (ev.type === "summary") {
      const chip = document.createElement("div");
      chip.className = "event-chip";
      chip.innerHTML = `<div class="pill"><b>Context compacted</b> · 85% full → lossless summary · <a href="#" class="show-sum">view</a></div>`;
      msgsEl.insertBefore(chip, thinkRow);
      chip.querySelector(".show-sum").onclick = (e) => {
        e.preventDefault();
        const pre = document.createElement("div");
        pre.className = "event-chip";
        pre.innerHTML = `<div class="pill" style="white-space:pre-wrap;text-align:left">${esc(ev.text)}</div>`;
        chip.replaceWith(pre);
      };
      toast("Context compacted at 85%");
    } else if (ev.type === "error" || ev.type === "summary_error") {
      toast(ev.error || "error", true);
    }
  };

  if (window.NPU) {
    activeChatHandler = (ev) => {
      handleEvent(ev);
      if (ev.type === "done") { finish(); activeChatHandler = null; }
      else if (ev.type === "error") {
        if (contentBuf) finish();
        else { clearInterval(timer); thinkRow.remove(); busy = false; sendBtn.disabled = false; stopBtn.classList.add("hidden"); }
        activeChatHandler = null;
      }
    };
    try {
      window.NPU.chat(JSON.stringify({
        messages: s.messages.map(m => ({ role: m.role, content: m.content })),
        search: useSearch, think
      }));
    } catch (e) {
      toast("Native bridge error: " + e.message, true);
      activeChatHandler = null; busy = false; sendBtn.disabled = false; stopBtn.classList.add("hidden");
    }
    return;
  }

  abortCtl = new AbortController();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: s.messages.map(m => ({ role: m.role, content: m.content })),
        search: useSearch, think
      }),
      signal: abortCtl.signal
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        if (!chunk.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(chunk.slice(5).trim()); } catch { continue; }
        handleEvent(ev);
      }
    }
    finish();
  } catch (e) {
    if (e.name !== "AbortError") {
      ensureAssistant();
      contentEl.innerHTML += `<p style="color:var(--error)">Connection error: ${esc(e.message)}</p>`;
      toast("Backend unreachable — is llama-server running?", true);
    } else if (contentBuf) {
      ensureAssistant();
      s.messages.push({ role: "assistant", content: contentBuf, reasoning: reasoningBuf, ts: Date.now() });
      save();
    }
  } finally {
    clearInterval(timer);
    thinkRow.remove();
    busy = false; sendBtn.disabled = false; stopBtn.classList.add("hidden");
    scrollBottom();
  }
}

/* init */
if (!sessions.length) newSession();
else { renderSessions(); renderChat(); }
if (window.NPU) {
  showSetup();
  window.NPU.ensureEngine();
} else {
  fetch("/api/health").then(r => r.json()).then(h => {
    if (!h.llama) toast("llama-server offline — NPU runtime not started", true);
  });
}
