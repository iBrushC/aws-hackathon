const MANUAL_ACTION_ITEMS = [
  "Connect Rukaiya with Max",
  "Schedule a meeting with Kent",
];

const state = {
  people: [],
  actionItems: [...MANUAL_ACTION_ITEMS],
  clips: [],
  chatHistory: [],
  pendingTyping: null,
  live: false,      // true once the context graph answered
  sessionId: null,  // agent conversation, so follow-up questions keep context
};

const els = {
  sessionDate: document.getElementById("session-date"),
  exportBtn: document.getElementById("export-btn"),
  regenBtn: document.getElementById("regenerate-btn"),

  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatField: document.getElementById("chat-field"),

  summary: document.getElementById("summary"),
  peopleList: document.getElementById("people-list"),
  peopleCount: document.getElementById("people-count"),
  actionList: document.getElementById("action-list"),

  clipsList: document.getElementById("clips-list"),
  clipsMeta: document.getElementById("clips-meta"),
};

function init() {
  els.sessionDate.textContent = formatDate(new Date());
  els.regenBtn.disabled = true;
  els.exportBtn.disabled = false;

  els.chatForm.addEventListener("submit", onChatSubmit);
  els.exportBtn.addEventListener("click", onExport);

  loadSession();
}

/* Prefer the real context graph. The seeded roster renders first so the page is
 * never blank, and stays put if the backend is down. */
async function loadSession() {
  seedDemoSession();
  if (!window.WhiskerGraph) return;
  try {
    const { people, clips } = await window.WhiskerGraph.loadGraphSession();
    if (people.length === 0) return;
    state.people = people.map((p) => ({
      ...p,
      photo: p.frame || avatarSvg(avatarColor(p.name), p.initials),
      photoFallback: avatarSvg(avatarColor(p.name), p.initials),
    }));
    state.clips = clips.map((c) => ({ ...c, poster: clipPoster("#111827", c.tag) }));
    state.actionItems = [...MANUAL_ACTION_ITEMS];
    state.live = true;
    renderAll();
  } catch (err) {
    console.warn("Context graph unavailable, showing demo data:", err);
    state.live = false;
  }
}

const AVATAR_COLORS = ["#6fb1ff", "#bcd9ff", "#0a0a0a", "#5a5a5a", "#9a9a9a"];

function avatarColor(name) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function formatDate(d) {
  return d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function formatTime(d) {
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function seedDemoSession() {
  const now = Date.now();
  const mk = (name, role, tags, summary, minsAgo, photo) => ({
    id: crypto.randomUUID(),
    name,
    role,
    tags,
    summary,
    firstMet: new Date(now - minsAgo * 60_000),
    initials: name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase(),
    photo,
  });

  state.people = [
    mk(
      "Alex Chen",
      "Engineering lead",
      ["engineering", "demo"],
      "Walked me through the prototype. Wants feedback on the new ingest pipeline before Friday's demo and flagged two edge cases worth revisiting.",
      180,
      avatarSvg("#6fb1ff", "AC")
    ),
    mk(
      "Priya Raman",
      "Recruiter at Helix Labs",
      ["recruiting"],
      "Walking through the senior platform role. Said the team is hiring urgently and the timeline is moving up; asked for a portfolio link.",
      150,
      avatarSvg("#bcd9ff", "PR")
    ),
    mk(
      "Marcus Whitfield",
      "Industrial designer",
      ["hardware", "design"],
      "Brainstormed the next chassis revision. Shared CAD references and offered to send over the bracket mockup by end of week.",
      120,
      avatarSvg("#0a0a0a", "MW")
    ),
    mk(
      "Sofia Reyes",
      "Investor, climate funds",
      ["investor", "climate"],
      "Quick intro chat. She mentioned a possible intro to her network at Northwind and asked for a one-pager on the climate angle.",
      95,
      avatarSvg("#5a5a5a", "SR")
    ),
    mk(
      "Daniel Kwon",
      "Studio coworker",
      ["coworker"],
      "Caught up at the studio. Working on the same sprint, we paired on the new auth flow and swapped notes on the upcoming sprint review.",
      60,
      avatarSvg("#9a9a9a", "DK")
    ),
    mk(
      "Emma Larsson",
      "Founder, Northwind Robotics",
      ["hardware", "founder"],
      "First intro. She's exploring a robotics collaboration and wants to set up a longer call next week to scope the integration.",
      35,
      avatarSvg("#6fb1ff", "EL")
    ),
  ];

  state.actionItems = [
    ...MANUAL_ACTION_ITEMS,
    "Send Alex the updated build link by tomorrow",
    "Follow up with Sofia about the Northwind intro",
    "Email Priya the resume + availability by Friday",
    "Send Marcus the CAD file for the new bracket",
    "Schedule a longer call with Emma for next week",
  ];

  state.clips = [
    { id: crypto.randomUUID(), title: "Demo walkthrough with Alex", sub: "Library - 10:42 AM", tag: "Engineering", durationSec: 47, poster: clipPoster("#1f2937", "Demo"), src: null, minutesAgo: 180 },
    { id: crypto.randomUUID(), title: "Hardware chat with Marcus", sub: "Cafe - 11:18 AM", tag: "Hardware", durationSec: 92, poster: clipPoster("#374151", "Hardware"), src: null, minutesAgo: 120 },
    { id: crypto.randomUUID(), title: "Northwind intro with Emma", sub: "Lobby - 2:05 PM", tag: "Intro", durationSec: 38, poster: clipPoster("#111827", "Intro"), src: null, minutesAgo: 35 },
  ];

  state.chatHistory = [];
  renderAll();
}

function avatarSvg(bg, text) {
  const fg = bg === "#bcd9ff" || bg === "#6fb1ff" ? "#0a0a0a" : "#ffffff";
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'>
    <rect width='80' height='80' fill='${bg}'/>
    <text x='50%' y='54%' text-anchor='middle' fill='${fg}'
          font-family='DM Sans, sans-serif' font-size='28' font-weight='700'>${escapeHtml(text)}</text>
  </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

function clipPoster(color, label) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 180'>
    <rect width='320' height='180' fill='${color}'/>
    <text x='50%' y='52%' text-anchor='middle' fill='#9ca3af'
          font-family='DM Sans, sans-serif' font-size='22' font-weight='600'>${escapeHtml(label)}</text></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

function renderAll() {
  renderSummary();
  renderPeople();
  renderActionItems();
  renderClips();
}

function renderSummary() {
  if (state.people.length === 0 && state.actionItems.length === 0) {
    els.summary.innerHTML = '<p class="summary-empty">Run a session to generate a summary of conversations and action items.</p>';
    return;
  }
  const names = state.people.map((p) => p.name).join(", ");

  if (state.live) {
    // Everything here is read off the graph, so say what is actually in it
    // rather than narrating a story the data does not support.
    const topics = [];
    for (const p of state.people) {
      for (const t of p.topics || []) if (!topics.includes(t)) topics.push(t);
    }
    const busiest = state.people[0];
    els.summary.innerHTML = `
      <h2>Overview</h2>
      <p>${state.people.length} ${state.people.length === 1 ? "person" : "people"} recognised across ${state.clips.length} moment${state.clips.length === 1 ? "" : "s"}: ${escapeHtml(names)}.</p>
      <h3>Most seen</h3>
      <p><strong>${escapeHtml(busiest.name)}</strong> appears in ${busiest.moments} moment${busiest.moments === 1 ? "" : "s"}${busiest.role ? ` — ${escapeHtml(busiest.role)}` : ""}.</p>
      ${topics.length ? `<h3>What came up</h3><p>${escapeHtml(topics.slice(0, 8).join(", "))}.</p>` : ""}`;
    return;
  }

  els.summary.innerHTML = `
    <h2>Overview</h2>
    <p>You met ${state.people.length} ${state.people.length === 1 ? "person" : "people"} today: ${escapeHtml(names)}.</p>
    <h3>Highlights</h3>
    <p>Conversations ranged from project updates to a few new intros. Most chats were short and focused, with a couple of longer catch-ups.</p>
    <h3>Noteworthy</h3>
    <p>Sofia mentioned a possible intro to her network. Alex flagged next week's demo date. Emma is exploring a collaboration on the robotics side.</p>`;
}

function renderPeople() {
  els.peopleCount.textContent = String(state.people.length);
  if (state.people.length === 0) {
    els.peopleList.innerHTML = '<li class="empty-state">No one yet.</li>';
    return;
  }
  els.peopleList.innerHTML = state.people.map((p) => {
    const tags = (p.tags || [])
      .map((t) => `<span class="person-tag">${escapeHtml(t)}</span>`)
      .join("");
    return `
      <li>
        <article class="person-card">
          <span class="avatar"><img src="${escapeAttr(p.photo)}"
            ${p.photoFallback ? `data-fallback="${p.photoFallback}" onerror="this.onerror=null;this.src=this.dataset.fallback"` : ""}
            alt=""></span>
          <div class="person-body">
            <span class="person-name">${escapeHtml(p.name)}</span>
            <span class="person-context">${escapeHtml(p.role)}</span>
            <p class="person-summary">${escapeHtml(p.summary)}</p>
            ${tags ? `<div class="person-tags">${tags}</div>` : ""}
          </div>
        </article>
      </li>`;
  }).join("");
}

function renderActionItems() {
  if (state.actionItems.length === 0) {
    els.actionList.innerHTML = '<li class="empty-state">None yet.</li>';
    return;
  }
  els.actionList.innerHTML = state.actionItems.map((text, idx) => `
    <li>
      <input type="checkbox" class="action-checkbox" data-idx="${idx}" id="action-${idx}" />
      <label for="action-${idx}" class="action-text">${escapeHtml(text)}</label>
    </li>`).join("");

  els.actionList.querySelectorAll(".action-checkbox").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      e.target.nextElementSibling.classList.toggle("done", e.target.checked);
    });
  });
}

function renderClips() {
  els.clipsMeta.textContent = `${state.clips.length} clip${state.clips.length === 1 ? "" : "s"}`;
  if (state.clips.length === 0) {
    els.clipsList.innerHTML = `
      <div class="clips-empty">
        <div class="clips-empty-inner">
          <p class="clips-empty-title">No clips yet</p>
          <p class="clips-empty-sub">Processed clips will appear here once available.</p>
        </div>
      </div>`;
    return;
  }
  els.clipsList.innerHTML = state.clips.map((c) => {
    const dur = formatDuration(c.durationSec);
    // Prefer the real frame from the moment itself; the generated poster is
    // only there for when the recording has no thumbnail behind it.
    const media = c.frame
      ? `<img src="${escapeAttr(c.frame)}" data-fallback="${c.poster}" loading="lazy"
              onerror="this.onerror=null;this.src=this.dataset.fallback" alt="" />`
      : c.src
        ? `<video src="${escapeHtml(c.src)}" poster="${c.poster}" preload="none" muted></video>`
        : `<img src="${c.poster}" alt="" />`;
    return `
      <article class="clip-card" data-id="${c.id}">
        <div class="clip-thumb">
          ${media}
          <span class="clip-duration">${dur}</span>
          <div class="clip-play">
            <span class="clip-play-icon" aria-hidden="true">
              <svg viewBox="0 0 20 20" width="16" height="16"><path d="M6 4l10 6-10 6V4z" fill="currentColor"/></svg>
            </span>
          </div>
        </div>
        <div class="clip-meta">
          <p class="clip-title">${escapeHtml(c.title)}</p>
          <p class="clip-sub">${escapeHtml(c.sub)}</p>
          <span class="clip-tag">${escapeHtml(c.tag)}</span>
        </div>
      </article>`;
  }).join("");

  els.clipsList.querySelectorAll(".clip-card").forEach((card) => {
    card.addEventListener("click", () => openClipModal(state.clips.find((c) => c.id === card.dataset.id)));
  });
}

function formatDuration(sec) {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

function openClipModal(clip) {
  if (!clip) return;
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;z-index:100;padding:24px;backdrop-filter:blur(4px);";
  const card = document.createElement("div");
  card.style.cssText = "background:#fff;border-radius:14px;overflow:hidden;width:min(720px,100%);max-height:90vh;display:flex;flex-direction:column;";
  card.innerHTML = `
    <div style="background:#111;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;">
      <img src="${escapeAttr(clip.frame || clip.poster)}" data-fallback="${clip.poster}"
           onerror="this.onerror=null;this.src=this.dataset.fallback"
           alt="" style="width:100%;height:100%;object-fit:cover;"/>
    </div>
    <div style="padding:16px 20px;display:flex;flex-direction:column;gap:6px;">
      <h3 style="margin:0;font-family:Lora,serif;font-size:18px;font-weight:600;">${escapeHtml(clip.title)}</h3>
      <p style="margin:0;color:#5a5a5a;font-size:13px;">${escapeHtml(clip.sub)} - ${formatDuration(clip.durationSec)}</p>
      ${clip.summary ? `<p style="margin:6px 0 0;font-size:14px;line-height:1.5;">${escapeHtml(clip.summary)}</p>` : ""}
      <div style="display:flex;justify-content:flex-end;margin-top:8px;"><button class="btn" id="clip-close">Close</button></div>
    </div>`;
  overlay.appendChild(card);
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  card.querySelector("#clip-close").addEventListener("click", close);
}

/* ---------- Export ---------- */

function onExport() {
  const payload = {
    exportedAt: new Date().toISOString(),
    sessionDate: state.sessionDate || null,
    people: state.people,
    actionItems: state.actionItems,
    clips: state.clips.map((c) => ({ id: c.id, title: c.title, sub: c.sub, tag: c.tag, durationSec: c.durationSec })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `whisker-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------- Markdown (lightweight) ---------- */

function renderMarkdown(src) {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;

  const inline = (s) =>
    escapeHtml(s)
      .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, h) => `<a href="${escapeAttr(h)}" target="_blank" rel="noopener">${t}</a>`);

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      const lang = line.replace(/^```/, "").trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      const langClass = lang ? ` class="lang-${escapeAttr(lang)}"` : "";
      out.push(`<pre${langClass}><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    if (/^#{1,3} /.test(line)) {
      const m = line.match(/^(#{1,3}) (.+)/);
      out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`);
      i++;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      out.push(`<blockquote>${inline(quoteLines.join(" "))}</blockquote>`);
      continue;
    }

    if (/^(\s*)[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^(\s*)[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^(\s*)[-*]\s+/, ""));
        i++;
      }
      out.push(`<ul>${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^(\s*)\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^(\s*)\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^(\s*)\d+\.\s+/, ""));
        i++;
      }
      out.push(`<ol>${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ol>`);
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,3} |```|>\s?|[-*]\s+|\d+\.\s+)/.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    out.push(`<p>${inline(para.join(" "))}</p>`);
  }

  return out.join("");
}

function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;");
}

/* ---------- Chat ---------- */

async function onChatSubmit(e) {
  e.preventDefault();
  const text = els.chatField.value.trim();
  if (!text || state.pendingTyping) return;
  els.chatField.value = "";

  appendUserMessage(text);
  state.chatHistory.push({ role: "user", text });

  showTyping();
  const reply = await generateBotReply(text);
  hideTyping();

  appendAgentMessage(reply.markdown, reply.refs);
  state.chatHistory.push({ role: "agent", text: reply.markdown });
}

function appendUserMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "chat-message user";
  wrap.innerHTML = `<div class="chat-bubble"><p>${escapeHtml(text)}</p></div>`;
  els.chatLog.appendChild(wrap);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function appendAgentMessage(markdown, refs = []) {
  const wrap = document.createElement("div");
  wrap.className = "chat-message agent";
  const refsHtml = refs.length
    ? `<div class="agent-refs">${refs.map((r) => `<span class="agent-ref">${escapeHtml(r)}</span>`).join("")}</div>`
    : "";
  wrap.innerHTML = `
    <span class="agent-label">Whisker</span>
    <div class="agent-markdown">${renderMarkdown(markdown)}</div>
    ${refsHtml}`;
  els.chatLog.appendChild(wrap);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function showTyping() {
  if (state.pendingTyping) return;
  const wrap = document.createElement("div");
  wrap.className = "chat-message agent";
  wrap.id = "chat-typing";
  wrap.innerHTML = `
    <span class="agent-label">Whisker</span>
    <div class="chat-typing" aria-label="Typing"><span></span><span></span><span></span></div>`;
  els.chatLog.appendChild(wrap);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
  state.pendingTyping = wrap;
}

function hideTyping() {
  if (state.pendingTyping) state.pendingTyping.remove();
  state.pendingTyping = null;
}

async function generateBotReply(question) {
  // On live data, let the graph agent answer: it can walk relationships
  // ("who did I meet who works on agents?") that matching over the cards can't.
  if (state.live && window.WhiskerGraph) {
    try {
      const res = await window.WhiskerGraph.askAgent(question, state.sessionId);
      state.sessionId = res.session_id || state.sessionId;
      const named = state.people
        .filter((p) => (res.response || "").toLowerCase().includes(p.name.toLowerCase()))
        .map((p) => p.name);
      return { markdown: res.response || "_No answer._", refs: named };
    } catch (err) {
      console.warn("Agent unavailable, matching locally:", err);
    }
  }

  await wait(600 + Math.random() * 700);
  const q = question.toLowerCase();
  const refs = [];

  if (state.people.length === 0) {
    return { markdown: "_I don't have any context for today yet._", refs };
  }

  const matches = state.people.filter((p) => {
    const blob = `${p.name} ${p.role} ${p.summary} ${(p.tags || []).join(" ")}`.toLowerCase();
    return blob.includes(q) || q.split(/\s+/).some((w) => w.length > 3 && blob.includes(w));
  });

  if (matches.length) {
    matches.forEach((m) => refs.push(m.name));
    const list = matches.map((m) => `**${m.name}** - ${m.summary}`).join("\n\n");
    const heading = matches.length === 1 ? `Found one match for _"${question}"_.` : `Found ${matches.length} matches for _"${question}"_.`;
    return { markdown: `### ${heading}\n\n${list}`, refs };
  }

  if (/(action|todo|follow)/.test(q)) {
    refs.push("Action items");
    const list = state.actionItems.map((a) => `- ${a}`).join("\n");
    return { markdown: `### Open action items\n\n${list}\n\nThe most urgent: **${state.actionItems[0]}**.`, refs };
  }

  if (/(clip|video)/.test(q)) {
    refs.push("Clips");
    const list = state.clips.map((c) => `- ${c.title} _(${c.sub})_`).join("\n");
    return { markdown: `### Processed clips from today\n\n${list}`, refs };
  }

  if (/(how many|count|total|summary)/.test(q)) {
    return {
      markdown: `### Today's counts\n\n- **${state.people.length}** people met\n- **${state.clips.length}** clips captured\n- **${state.actionItems.length}** action items open`,
      refs: [],
    };
  }

  return {
    markdown: `You met **${state.people.length}** people today. Try asking about a name, a topic (e.g. _hardware_, _investors_), or say _"show my action items"_.`,
    refs: [],
  };
}

init();
