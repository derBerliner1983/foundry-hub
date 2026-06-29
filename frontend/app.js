// Foundry-Hub Frontend – Vanilla JS, spricht mit der REST-API.
const api = {
  async get(p) { const r = await fetch(p); return r.json(); },
  async post(p, b) { const r = await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return r.json(); },
  async put(p, b) { const r = await fetch(p, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }); return r.json(); },
};

let currentView = "dashboard";
let agentsCache = [];
let chefId = null;
let selectedAgent = null; // null = Chef-Inbox (an Nutzer)

const root = document.getElementById("view-root");
const titleEl = document.getElementById("view-title");
const TITLES = { dashboard: "Dashboard", inbox: "Inbox", assistant: "Daily-Assistent", projects: "Projekte", progress: "Fortschritt", org: "Team / Organisation", tasks: "Aufgaben", workshop: "Werkstatt", cookbook: "Cookbook / Regelwerk", knowledge: "Wissensspeicher", skills: "Skills & MCP", approvals: "Freigaben", activity: "Aktivität", users: "Nutzer & Teilen", settings: "Einstellungen" };
let wsProject = null;
let progProject = "";

function icons() { window.lucide && lucide.createIcons(); }
function esc(s) { return (s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function initials(n) { return (n || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase(); }
function secField(sec, key, label) {
  const st = sec[key] || { configured: false, source: "none", secret: false };
  const badge = st.configured
    ? `<span class="pill employed">✓ ${st.source}</span>`
    : `<span class="pill resigned">nicht gesetzt</span>`;
  const ph = st.configured ? "•••• gesetzt – neu eingeben zum Ändern" : "eintragen …";
  return `<label>${label} ${badge}</label>
    <input data-secret="${key}" type="${st.secret ? 'password' : 'text'}" autocomplete="off" placeholder="${ph}"/>`;
}

// ---------- Navigation ----------
document.querySelectorAll(".nav-item").forEach(el => {
  el.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    el.classList.add("active");
    currentView = el.dataset.view;
    titleEl.textContent = TITLES[currentView];
    render();
  });
});

// ---------- Globale Suche ----------
(function () {
  const box = document.getElementById("gsearch");
  const panel = document.getElementById("gsearch-results");
  if (!box || !panel) return;
  let timer = null;
  const ICONS = { Projekt: "folder", Aufgabe: "check-square", Nachricht: "mail", Agent: "user", Regel: "book-open", Wissen: "brain" };
  async function run() {
    const q = box.value.trim();
    if (q.length < 2) { panel.classList.add("hidden"); panel.innerHTML = ""; return; }
    try {
      const r = await api.get("/api/search?q=" + encodeURIComponent(q));
      if (!r.results.length) { panel.innerHTML = `<div class="gs-empty">Keine Treffer.</div>`; panel.classList.remove("hidden"); icons(); return; }
      panel.innerHTML = r.results.map((x, i) => `<div class="gs-item" data-i="${i}">
        <i data-lucide="${ICONS[x.type] || 'search'}"></i>
        <div class="gs-main"><b>${esc(x.title)}</b><small>${esc(x.type)}${x.snippet ? ' · ' + esc(x.snippet) : ''}</small></div></div>`).join("");
      panel.classList.remove("hidden"); icons();
      panel.querySelectorAll(".gs-item").forEach(el => {
        el.onclick = () => {
          const x = r.results[parseInt(el.dataset.i)];
          panel.classList.add("hidden"); box.value = "";
          if (x.view) window.goView(x.view);
        };
      });
    } catch (_) {}
  }
  box.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 220); });
  box.addEventListener("keydown", (e) => { if (e.key === "Escape") { panel.classList.add("hidden"); box.value = ""; } });
  document.addEventListener("click", (e) => { if (!document.getElementById("gsearch-wrap").contains(e.target)) panel.classList.add("hidden"); });
})();

// ---------- Theme (mit Speicherung) ----------
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  const tog = document.getElementById("theme-toggle");
  tog.innerHTML = t === "dark"
    ? '<i data-lucide="moon"></i><span>Dunkel</span>'
    : '<i data-lucide="sun"></i><span>Hell</span>';
  icons();
  localStorage.setItem("foundryhub-theme", t);
}
applyTheme(localStorage.getItem("foundryhub-theme") || "dark");
document.getElementById("theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

// ---------- Render-Dispatcher ----------
async function render() {
  if (currentView === "dashboard") return renderDashboard();
  if (currentView === "inbox") return renderInbox();
  if (currentView === "assistant") return renderAssistant();
  if (currentView === "projects") return renderProjects();
  if (currentView === "progress") return renderProgress();
  if (currentView === "org") return renderOrg();
  if (currentView === "tasks") return renderTasks();
  if (currentView === "workshop") return renderWorkshop();
  if (currentView === "cookbook") return renderCookbook();
  if (currentView === "knowledge") return renderKnowledge();
  if (currentView === "skills") return renderSkills();
  if (currentView === "users") return renderUsers();
  if (currentView === "approvals") return renderApprovals();
  if (currentView === "activity") return renderActivity();
  if (currentView === "settings") return renderSettings();
}

// ---------- Dashboard ----------
window.goView = (view) => {
  const el = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (el) el.click();
};
window.openProjectProgress = (pid) => { progProject = String(pid); goView("progress"); };
window.answerQuestion = async (qid, senderAgentId) => {
  const inp = document.getElementById("qans-" + qid);
  const body = inp.value.trim(); if (!body) return;
  await api.post("/api/messages", { to_agent_id: senderAgentId, body });
  inp.value = ""; renderDashboard();
};

async function renderDashboard() {
  const d = await api.get("/api/dashboard");
  const bud = await api.get("/api/budget");
  const s = d.stats;
  const tile = (label, val, view, color) => `<div class="card" style="cursor:pointer" onclick="goView('${view}')">
    <div class="stat-label">${label}</div><div class="stat" style="color:${color || 'var(--text)'}">${val}</div></div>`;

  root.innerHTML = `
    <div class="grid cols-3" style="margin-bottom:16px">
      ${tile("Projekte", s.projects, "projects")}
      ${tile("Mitarbeiter", s.agents, "org")}
      ${tile("Aufgaben erledigt", `${s.tasks_done}/${s.tasks_total}`, "tasks", "var(--green)")}
      ${tile("Offene Rückfragen", s.open_questions, "inbox", s.open_questions ? "var(--yellow)" : "var(--text)")}
      ${tile("Freigaben", s.pending_approvals, "approvals", s.pending_approvals ? "var(--yellow)" : "var(--text)")}
      ${tile("Überfällig", s.overdue, "progress", s.overdue ? "var(--red)" : "var(--text)")}
      ${tile(bud.paused ? "Budget (pausiert!)" : "Kosten (USD)", "$" + bud.spent.toFixed(2), "settings", bud.paused ? "var(--red)" : "var(--text)")}
    </div>

    ${s.overdue ? `<div class="card" style="margin-bottom:16px;border-color:var(--red)">
      <h3><i data-lucide="alarm-clock"></i> Überfällige Meilensteine</h3>
      ${d.overdue_milestones.map(m => `<div class="agent-row" style="cursor:pointer" onclick="openProjectProgress(${m.project_id || ''})">
        <div class="avatar role-qa"><i data-lucide="flag"></i></div>
        <div class="info"><b>${esc(m.title)}</b><small>Projekt #${m.project_id ?? '–'} · ${m.days_over} Tage über Frist (${new Date(m.due_date).toLocaleDateString('de-DE')})</small></div>
        <span class="pill fired">⚠️ überfällig</span></div>`).join("")}
    </div>` : ''}

    <div class="grid cols-2" style="margin-bottom:16px">
      <div class="card"><h3><i data-lucide="folder-kanban"></i> Projekte</h3>
        ${d.projects.length ? d.projects.map(p => `<div class="agent-row" style="cursor:pointer" onclick="openProjectProgress(${p.id})">
          <div class="avatar role-project_manager"><i data-lucide="folder"></i></div>
          <div class="info"><b>#${p.id} ${esc(p.title)}</b>
            <small>${p.team} MA · ${p.tasks_done}/${p.tasks_total} Aufgaben · ${p.milestones_done}/${p.milestones_total} Meilensteine</small>
            <div style="margin-top:6px">${bar(p.task_percent, p.overdue ? 'var(--red)' : 'var(--green)')}</div></div>
          ${p.overdue ? `<span class="pill fired">${p.overdue}⚠️</span>` : `<span class="pill employed">${p.task_percent}%</span>`}
        </div>`).join("") : `<div class="muted">Noch keine Projekte. Lege in der Inbox oder unter Projekte eins an.</div>`}
      </div>
      <div class="card"><h3><i data-lucide="help-circle"></i> Offene Rückfragen an dich</h3>
        ${d.open_questions.length ? d.open_questions.map(q => `<div class="msg needs-answer">
          <div class="meta"><b>${esc(q.sender)}</b><span class="spacer" style="flex:1"></span>${new Date(q.created_at).toLocaleString('de-DE')}</div>
          <div class="subject">${esc(q.subject)}</div><div class="body">${esc((q.body||'').slice(0,200))}</div>
          <div class="row" style="margin-top:8px">
            <input id="qans-${q.id}" placeholder="Direkt antworten …" style="margin:0"
              onkeydown="if(event.key==='Enter')answerQuestion(${q.id}, ${q.sender_agent_id || 'null'})"/>
            <button class="btn sm" onclick="answerQuestion(${q.id}, ${q.sender_agent_id || 'null'})"><i data-lucide="send"></i></button>
          </div></div>`).join("")
        : `<div class="muted">Keine offenen Rückfragen.</div>`}
        ${d.approvals.length ? `<h3 style="margin-top:14px"><i data-lucide="shield-check"></i> Wartende Freigaben</h3>
          ${d.approvals.map(a => `<div class="agent-row" style="cursor:pointer" onclick="goView('approvals')">
            <div class="info"><b>${esc(a.summary)}</b></div><i data-lucide="chevron-right"></i></div>`).join("")}` : ''}
      </div>
    </div>

    <div class="card"><h3><i data-lucide="activity"></i> Letzte Aktivität</h3>
      ${d.recent_activity.length ? d.recent_activity.map(e => `<div class="agent-row">
        <div class="avatar" style="background:var(--panel-2);color:var(--text-dim);width:32px;height:32px"><i data-lucide="circle"></i></div>
        <div class="info"><b style="font-weight:500">${esc(e.text)}</b><small>${new Date(e.created_at).toLocaleString('de-DE')}</small></div></div>`).join("")
      : `<div class="muted">Noch keine Aktivität.</div>`}
      <div class="row" style="margin-top:10px"><button class="btn ghost sm" onclick="goView('activity')">Alle Ereignisse <i data-lucide="arrow-right"></i></button></div>
    </div>`;
  icons();
}

// ---------- Daily-Assistent ----------
let assistChat = [];
async function renderAssistant() {
  const st = await api.get("/api/assistant/status");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <h3><i data-lucide="sparkles"></i> Dein persönlicher Assistent</h3>
      <div class="row" style="flex-wrap:wrap;gap:8px">
        <span class="pill ${st.email_access ? 'employed' : 'resigned'}">E-Mail-Zugang: ${st.email_access ? 'an' : 'aus'}</span>
        <span class="pill ${st.imap ? 'employed' : 'resigned'}">IMAP (lesen): ${st.imap ? 'konfiguriert' : 'fehlt'}</span>
        <span class="pill ${st.smtp ? 'employed' : 'resigned'}">SMTP (senden): ${st.smtp ? 'konfiguriert' : 'fehlt'}</span>
        <span class="spacer" style="flex:1"></span>
        <button class="btn ghost sm" onclick="goView('settings')"><i data-lucide="settings"></i> E-Mail einrichten</button>
      </div>
      ${(!st.email_access || !st.imap) ? `<div class="tag" style="margin-top:8px">Für das Lesen/Zusammenfassen: in den Einstellungen IMAP konfigurieren und „E-Mail-Zugang für Assistent" aktivieren.</div>` : ''}
    </div>
    <div class="grid cols-2">
      <div class="card"><h3><i data-lucide="mail"></i> Posteingang</h3>
        <div class="row" style="margin-bottom:10px"><button class="btn" id="as-sum"><i data-lucide="wand-2"></i> E-Mails zusammenfassen</button>
          <button class="btn ghost" id="as-refresh"><i data-lucide="refresh-cw"></i> Laden</button></div>
        <div id="as-summary"></div>
        <div id="as-emails"></div>
      </div>
      <div class="card"><h3><i data-lucide="message-circle"></i> Mit dem Assistenten chatten</h3>
        <div id="as-chat" style="max-height:300px;overflow:auto;margin-bottom:10px"></div>
        <div class="row"><input id="as-msg" placeholder="Frag deinen Assistenten …" style="margin:0"
          onkeydown="if(event.key==='Enter')asSend()"/>
          <button class="btn" onclick="asSend()"><i data-lucide="send"></i></button></div>
        <h3 style="margin-top:16px"><i data-lucide="mail-plus"></i> E-Mail senden</h3>
        <input id="em-to" placeholder="An (E-Mail-Adresse)"/>
        <input id="em-subj" placeholder="Betreff"/>
        <textarea id="em-body" placeholder="Text …"></textarea>
        <button class="btn" id="em-send" ${st.smtp ? '' : 'disabled'}><i data-lucide="send"></i> Senden</button>
        <span class="muted" id="em-status" style="margin-left:8px"></span>
      </div>
    </div>`;
  icons();
  renderChat();
  document.getElementById("as-sum").onclick = async () => {
    const sumEl = document.getElementById("as-summary");
    sumEl.innerHTML = `<div class="muted">fasse zusammen …</div>`;
    const r = await api.post("/api/assistant/summarize");
    sumEl.innerHTML = r.ok
      ? `<div class="msg from-agent"><div class="subject">Zusammenfassung (${r.count} E-Mails)</div><div class="body">${esc(r.summary)}</div></div>`
      : `<div class="tag" style="color:var(--red)">${esc(r.error || 'Fehler')}</div>`;
  };
  document.getElementById("as-refresh").onclick = loadAssistantEmails;
  document.getElementById("em-send").onclick = async () => {
    const r = await api.post("/api/assistant/send", {
      to: document.getElementById("em-to").value, subject: document.getElementById("em-subj").value,
      body: document.getElementById("em-body").value });
    document.getElementById("em-status").textContent = r.ok ? "✓ gesendet" : ("✕ " + (r.error || ""));
  };
  if (st.email_access && st.imap) loadAssistantEmails();
}

async function loadAssistantEmails() {
  const el = document.getElementById("as-emails"); if (!el) return;
  el.innerHTML = `<div class="muted">lade …</div>`;
  const r = await api.get("/api/assistant/emails");
  if (!r.ok) { el.innerHTML = `<div class="tag" style="color:var(--red)">${esc(r.error || 'Fehler')}</div>`; return; }
  el.innerHTML = r.emails.length ? r.emails.map((m, i) => `<div class="msg">
    <div class="meta"><b>${esc(m.from)}</b><span class="spacer" style="flex:1"></span>${esc(m.date)}
      <button class="btn ghost sm" onclick='emailToTask(${JSON.stringify(m.subject)}, ${JSON.stringify(m.snippet)})' style="margin-left:6px">→ Auftrag</button></div>
    <div class="subject">${esc(m.subject)}</div><div class="body">${esc(m.snippet)}</div></div>`).join("")
    : `<div class="muted">Keine E-Mails.</div>`;
}

function renderChat() {
  const el = document.getElementById("as-chat"); if (!el) return;
  el.innerHTML = assistChat.map(m => `<div class="msg ${m.role === 'user' ? 'from-user' : 'from-agent'}">
    <div class="meta">${m.role === 'user' ? 'Du' : 'Assistent'}</div><div class="body">${esc(m.text)}</div></div>`).join("")
    || `<div class="muted">Stell eine Frage – z. B. „Fasse meine wichtigsten Mails zusammen" oder „Entwirf eine Antwort an …".</div>`;
  el.scrollTop = el.scrollHeight;
}
window.emailToTask = async (subject, body) => {
  await api.post("/api/assistant/email-to-task", { subject, body });
  alert("Als Auftrag an die Firma übergeben.");
};
window.asSend = async () => {
  const inp = document.getElementById("as-msg"); const msg = inp.value.trim(); if (!msg) return;
  assistChat.push({ role: "user", text: msg }); inp.value = ""; renderChat();
  assistChat.push({ role: "assistant", text: "…" }); renderChat();
  const r = await api.post("/api/assistant/chat", { message: msg });
  let text = r.reply || r.error || "(keine Antwort)";
  if (r.done && r.done.length) text += "\n\n✅ " + r.done.join("\n✅ ");
  assistChat[assistChat.length - 1] = { role: "assistant", text };
  renderChat();
};

// ---------- Inbox ----------
async function renderInbox() {
  const state = await api.get("/api/state");
  agentsCache = state.agents; chefId = state.chef_id;
  const employed = agentsCache.filter(a => a.status === "employed");

  const options = [`<option value="">📥 Chef-Inbox (an dich)</option>`]
    .concat(employed.map(a => `<option value="${a.id}" ${selectedAgent == a.id ? "selected" : ""}>${esc(a.name)} – ${esc(a.title)}</option>`)).join("");

  root.innerHTML = `
    <div class="grid cols-2" style="margin-bottom:16px">
      <div class="card">
        <h3><i data-lucide="send"></i> Neue Anfrage an den Chef</h3>
        <label>Art</label>
        <select id="req-type"><option value="project">Projekt (eigenes Team)</option><option value="quick">Einzelaufgabe (kein Projekt)</option></select>
        <input id="req-title" placeholder="Was möchtest du? (Titel)" />
        <textarea id="req-desc" placeholder="Beschreibe Wunsch, Ziel, Termin/Frist, Details …"></textarea>
        <div class="row"><button class="btn" id="req-send"><i data-lucide="rocket"></i> Auftrag senden</button>
          <button class="btn ghost" id="req-mic" title="Diktieren"><i data-lucide="mic"></i></button></div>
      </div>
      <div class="card">
        <h3><i data-lucide="messages-square"></i> Konversation</h3>
        <label>Postfach wählen</label>
        <select id="inbox-pick">${options}</select>
        <textarea id="reply-body" placeholder="Nachricht an dieses Postfach …"></textarea>
        <button class="btn ghost" id="reply-send"><i data-lucide="reply"></i> Senden</button>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><i data-lucide="inbox"></i> <b>Nachrichten</b>
        <span class="tag" id="thread-label"></span><i data-lucide="chevron-down" class="chev"></i></div>
      <div class="panel-body" id="thread"></div>
    </div>`;
  icons();

  document.getElementById("req-send").onclick = async () => {
    const title = document.getElementById("req-title").value.trim();
    if (!title) return;
    const desc = document.getElementById("req-desc").value;
    const type = document.getElementById("req-type").value;
    await api.post(type === "quick" ? "/api/quicktasks" : "/api/projects", { title, description: desc });
    document.getElementById("req-title").value = ""; document.getElementById("req-desc").value = "";
    selectedAgent = ""; loadThread();
  };
  const mic = document.getElementById("req-mic");
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (mic) {
    if (!SR) { mic.disabled = true; mic.title = "Spracheingabe vom Browser nicht unterstützt"; }
    else mic.onclick = () => {
      const rec = new SR(); rec.lang = "de-DE"; rec.interimResults = false;
      mic.innerHTML = '<i data-lucide="mic" style="color:var(--red)"></i>'; icons();
      rec.onresult = (e) => { const t = e.results[0][0].transcript; const d = document.getElementById("req-desc"); d.value = (d.value ? d.value + " " : "") + t; };
      rec.onend = () => { mic.innerHTML = '<i data-lucide="mic"></i>'; icons(); };
      rec.start();
    };
  }
  document.getElementById("inbox-pick").onchange = e => { selectedAgent = e.target.value; loadThread(); };
  document.getElementById("reply-send").onclick = async () => {
    const body = document.getElementById("reply-body").value.trim();
    if (!body) return;
    const to = selectedAgent === "" || selectedAgent == chefId ? (selectedAgent === "" ? chefId : selectedAgent) : selectedAgent;
    await api.post("/api/messages", { to_agent_id: to ? Number(to) : null, body });
    document.getElementById("reply-body").value = ""; loadThread();
  };
  setupCollapse();
  loadThread();
}

async function loadThread() {
  const tEl = document.getElementById("thread");
  if (!tEl) return;
  let msgs;
  if (selectedAgent === "" || selectedAgent == null) {
    msgs = await api.get("/api/messages?inbox=user");
    document.getElementById("thread-label").textContent = "Chef → du";
  } else {
    msgs = await api.get("/api/messages?agent_id=" + selectedAgent);
    document.getElementById("thread-label").textContent = "Thread";
  }
  if (!msgs.length) { tEl.innerHTML = `<div class="empty">Noch keine Nachrichten.</div>`; return; }
  tEl.innerHTML = msgs.map(m => {
    const fromUser = m.sender_kind === "user";
    const cls = m.requires_answer && !m.answered ? "needs-answer" : (fromUser ? "from-user" : "from-agent");
    return `<div class="msg ${cls}">
      <div class="meta"><b>${esc(m.sender)}</b> <i data-lucide="arrow-right" style="width:13px"></i> ${esc(m.recipient)}
        <span class="spacer" style="flex:1"></span>${new Date(m.created_at).toLocaleString("de-DE")}</div>
      <div class="subject">${esc(m.subject)}</div>
      <div class="body">${esc(m.body)}</div>
      ${m.requires_answer && !m.answered ? `<div class="tag" style="margin-top:6px;color:var(--yellow)">⏳ wartet auf deine Antwort</div>` : ""}
    </div>`;
  }).join("");
  icons();
}

// ---------- Org / Team ----------
async function renderOrg() {
  const state = await api.get("/api/state");
  agentsCache = state.agents; chefId = state.chef_id;
  const byManager = {};
  agentsCache.forEach(a => { (byManager[a.manager_id] = byManager[a.manager_id] || []).push(a); });

  const employed = agentsCache.filter(a => a.status === "employed");
  function node(a) {
    const r = a.rating;
    const kids = employed.filter(c => c.manager_id === a.id);
    return `<li><div class="node" onclick="openAgent(${a.id})" style="cursor:pointer">
        <div class="avatar role-${a.role}" style="width:30px;height:30px">${initials(a.name)}</div>
        <div><b>${esc(a.name)}</b><small>${esc(a.title)} · ${r ?? '–'}★${a.stuck ? ' · ⚠️' : ''}</small></div>
      </div>${kids.length ? `<ul>${kids.map(node).join("")}</ul>` : ""}</li>`;
  }
  // Einfache Liste als Fallback + Baum
  function row(a, depth) {
    const r = a.rating; const p = r ? (r / 5) * 100 : 0;
    return `<div class="agent-row ${depth ? "indent" : ""}" style="margin-left:${depth * 26}px">
      <div class="avatar role-${a.role}">${initials(a.name)}</div>
      <div class="info"><b>${esc(a.name)}</b><small>${esc(a.title)} · ${esc(a.provider)}/${esc(a.model)}</small></div>
      <div class="donut" style="--p:${p}"><span>${r ?? "–"}</span></div>
      ${a.stuck ? `<span class="pill fired">⚠️ Schleife</span><button class="btn green sm" onclick="resumeAgent(${a.id})"><i data-lucide="play"></i> fortsetzen</button>` : ''}
      <span class="pill ${a.status}">${a.status}</span>
      <button class="btn ghost sm" onclick="openAgent(${a.id})"><i data-lucide="star"></i> bewerten</button>
    </div>` + (byManager[a.id] || []).map(c => row(c, depth + 1)).join("");
  }
  const chef = agentsCache.find(a => a.role === "ceo");
  root.innerHTML = `<div class="card"><h3><i data-lucide="network"></i> Organigramm</h3>
      ${chef ? `<ul class="tree">${node(chef)}</ul>` : `<div class="empty">Kein Chef.</div>`}</div>
    <div class="card" style="margin-top:14px"><h3><i data-lucide="list"></i> Team (Liste & Bewertung)</h3>
      ${chef ? row(chef, 0) : ''}</div>
    <div id="agent-detail"></div>`;
  icons();
}

window.resumeAgent = async (id) => { await api.post(`/api/agents/${id}/resume`); renderOrg(); };
window.openAgent = async function (id) {
  const a = await api.get("/api/agents/" + id);
  const d = document.getElementById("agent-detail");
  d.innerHTML = `<div class="card" style="margin-top:16px">
    <h3><i data-lucide="user"></i> ${esc(a.name)} – ${esc(a.title)}</h3>
    <div class="row" style="margin-bottom:12px"><span class="tag">${esc(a.provider)}/${esc(a.model)}</span>
      <span class="pill ${a.status}">${a.status}</span>
      <span class="muted">Ø Bewertung: ${a.rating ?? "–"} (${a.rating_count})</span></div>
    <label>Leistung bewerten</label>
    <div class="stars" id="stars">☆☆☆☆☆</div>
    <textarea id="rate-fb" placeholder="Feedback (optional)"></textarea>
    <button class="btn" id="rate-send"><i data-lucide="check"></i> Bewertung speichern</button>
    <h3 style="margin-top:18px"><i data-lucide="list"></i> Aufgaben</h3>
    ${a.tasks.length ? a.tasks.map(t => `<div class="msg"><div class="subject">${esc(t.title)} <span class="tag">${t.status}</span></div><div class="body">${esc(t.result || "")}</div></div>`).join("") : `<div class="muted">keine</div>`}
    <h3 style="margin-top:14px"><i data-lucide="star"></i> Bewertungen</h3>
    ${a.ratings.length ? a.ratings.map(r => `<div class="msg"><div class="meta">${esc(r.rater)} · ${r.score}/5</div><div class="body">${esc(r.feedback)}</div></div>`).join("") : `<div class="muted">noch keine</div>`}
  </div>`;
  icons();
  let score = 0;
  const stars = document.getElementById("stars");
  stars.onmousemove = e => { const i = Math.ceil(((e.offsetX) / stars.offsetWidth) * 5); stars.textContent = "★★★★★☆☆☆☆☆".slice(5 - i, 10 - i); };
  stars.onclick = e => { score = Math.ceil(((e.offsetX) / stars.offsetWidth) * 5); };
  document.getElementById("rate-send").onclick = async () => {
    if (!score) score = 3;
    await api.post("/api/ratings", { agent_id: id, score, feedback: document.getElementById("rate-fb").value });
    openAgent(id);
  };
};

// ---------- Tasks ----------
async function renderTasks() {
  const tasks = await api.get("/api/tasks");
  const cols = { todo: "Offen", in_progress: "In Arbeit", review: "Review", done: "Erledigt" };
  const groups = {}; Object.keys(cols).forEach(k => groups[k] = []);
  tasks.forEach(t => (groups[t.status] || (groups[t.status] = [])).push(t));
  root.innerHTML = `<div class="tag" style="margin-bottom:10px">Karten per Drag & Drop zwischen den Spalten verschieben.</div>
    <div class="kanban">${Object.keys(cols).map(k => `
      <div class="kcol" data-status="${k}" ondragover="event.preventDefault()" ondrop="dropTask(event,'${k}')">
        <div class="kcol-head">${cols[k]} <span class="tag">${(groups[k] || []).length}</span></div>
        ${(groups[k] || []).map(t => `<div class="kcard${t.blocked ? ' blocked' : ''}" draggable="true" ondragstart="event.dataTransfer.setData('id','${t.id}')">
          <b>#${t.id} ${esc(t.title)}</b>
          <div class="muted" style="font-size:12px">${esc((t.description || '').slice(0, 90))}</div>
          ${t.blocked ? `<div class="tag" style="margin-top:4px;color:var(--yellow)">⛔ blockiert: wartet auf #${esc(t.depends_on)}</div>` : ''}
          ${t.depends_on && !t.blocked ? `<div class="tag" style="margin-top:4px">↳ nach #${esc(t.depends_on)}</div>` : ''}
          ${t.result ? `<div class="tag" style="margin-top:4px">${esc(t.result.slice(0, 80))}</div>` : ''}
          <div style="margin-top:6px"><button class="btn ghost sm" onclick="editDeps(${t.id},'${esc(t.depends_on || '')}')"><i data-lucide="link"></i> Abhängigkeiten</button></div></div>`).join("")}
      </div>`).join("")}</div>`;
  icons();
}
window.editDeps = async (id, current) => {
  const v = prompt("Diese Aufgabe startet erst, wenn folgende Aufgaben-IDs erledigt sind (kommagetrennt, leer = keine):", current);
  if (v === null) return;
  await api.put("/api/tasks/" + id, { depends_on: v });
  renderTasks();
};
window.dropTask = async (e, status) => {
  e.preventDefault();
  const id = e.dataTransfer.getData("id"); if (!id) return;
  await api.put("/api/tasks/" + id, { status });
  renderTasks();
};

// ---------- Werkstatt ----------
async function renderWorkshop() {
  const projects = await api.get("/api/projects");
  if (wsProject === null && projects.length) wsProject = projects[0].id;
  const opts = projects.map(p => `<option value="${p.id}" ${wsProject == p.id ? "selected" : ""}>#${p.id} ${esc(p.title)}</option>`).join("");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <div class="row"><h3 style="margin:0"><i data-lucide="folder-code"></i> Projekt-Workspace</h3>
        <div class="spacer" style="flex:1"></div>
        <span id="ws-sandbox" class="tag">Sandbox …</span>
        <input type="file" id="ws-upload" class="hidden"/>
        <button class="btn ghost sm" id="ws-up"><i data-lucide="upload"></i> Hochladen</button>
        <button class="btn ghost sm" id="ws-zip"><i data-lucide="download"></i> ZIP</button>
        <button class="btn ghost sm" id="ws-preview"><i data-lucide="play-circle"></i> Vorschau</button>
        <button class="btn ghost sm" id="ws-github"><i data-lucide="github"></i> GitHub</button>
        <button class="btn ghost sm" id="ws-deploy"><i data-lucide="rocket"></i> Deploy</button>
        <button class="btn ghost sm" id="ws-reset"><i data-lucide="trash-2"></i> leeren</button>
        <select id="ws-proj" style="width:auto;margin:0">${opts || '<option>kein Projekt</option>'}</select></div>
      <div class="row" style="margin-top:8px;gap:8px">
        <input id="ws-testcmd" placeholder="Testbefehl (z. B. pytest -q)" style="margin:0"/>
        <input id="ws-deploycmd" placeholder="Deploy-Befehl (z. B. flyctl deploy)" style="margin:0"/>
        <button class="btn ghost sm" id="ws-cfgsave" style="white-space:nowrap">speichern</button>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card"><h3><i data-lucide="files"></i> Dateien</h3><div id="ws-files"></div></div>
      <div class="card"><h3><i data-lucide="file-text"></i> Vorschau</h3><pre id="ws-view" style="white-space:pre-wrap;max-height:340px;overflow:auto;margin:0;color:var(--text-dim)">Datei wählen …</pre></div>
    </div>
    <div class="panel" style="margin-top:14px">
      <div class="panel-head"><i data-lucide="terminal"></i> <b>Konsole / Ausführungen</b><i data-lucide="chevron-down" class="chev"></i></div>
      <div class="panel-body" id="ws-console"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><i data-lucide="git-branch"></i> <b>Versionen / Rollback</b><i data-lucide="chevron-down" class="chev"></i></div>
      <div class="panel-body" id="ws-git"></div>
    </div>`;
  icons(); setupCollapse();
  document.getElementById("ws-proj").onchange = e => { wsProject = e.target.value; loadWorkshop(); };
  document.getElementById("ws-reset").onclick = async () => {
    if (!confirm("Workspace dieses Projekts leeren (Dateien & Builds löschen)?")) return;
    await api.post("/api/sandbox/reset?project_id=" + (wsProject || ""));
    loadWorkshop();
  };
  document.getElementById("ws-up").onclick = () => document.getElementById("ws-upload").click();
  document.getElementById("ws-upload").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f); if (wsProject) fd.append("project_id", wsProject);
    await fetch("/api/workspace/upload", { method: "POST", body: fd });
    loadWorkshop();
  };
  document.getElementById("ws-zip").onclick = () => {
    window.open("/api/workspace/zip?project_id=" + (wsProject || ""), "_blank");
  };
  document.getElementById("ws-preview").onclick = async () => {
    const cmd = prompt("Live-Vorschau starten. Befehl (leer = statischer Server für HTML/CSS/JS):\nz. B. 'npm run dev -- --port 8090' oder leer", "");
    const r = await api.post("/api/preview/start", { project_id: wsProject ? Number(wsProject) : null, cmd: cmd || "" });
    if (r.ok) { setTimeout(() => window.open(r.url, "_blank"), 1200); }
    else alert("Vorschau fehlgeschlagen: " + (r.error || ""));
  };
  document.getElementById("ws-github").onclick = async () => {
    const st = await api.get("/api/github/status");
    if (!st.configured) { alert("Bitte zuerst ein GitHub-Token unter Einstellungen → Zugangsdaten eintragen."); return; }
    const repo = prompt("Repository-Name auf GitHub (" + (st.login || "") + "):", "foundry-hub-projekt");
    if (!repo) return;
    const r = await api.post("/api/github/push", { project_id: wsProject ? Number(wsProject) : null, repo_name: repo, private: true });
    alert(r.ok ? "Gepusht: " + r.url : "Fehler: " + (r.error || ""));
  };
  document.getElementById("ws-deploy").onclick = async () => {
    const r = await api.post("/api/deploy?project_id=" + (wsProject || ""));
    alert(r.ok ? "Deploy gestartet/erledigt." : ("Deploy: " + (r.error || (r.output || "").slice(-300))));
  };
  // Projekt-Konfiguration (Test/Deploy) laden + speichern
  if (wsProject) api.get("/api/projects/" + wsProject).then(p => {
    const tc = document.getElementById("ws-testcmd"), dc = document.getElementById("ws-deploycmd");
    if (tc) tc.value = p.test_command || ""; if (dc) dc.value = p.deploy_command || "";
  }).catch(() => {});
  const cfgSave = document.getElementById("ws-cfgsave");
  if (cfgSave) cfgSave.onclick = async () => {
    if (!wsProject) { alert("Erst ein Projekt wählen."); return; }
    await api.put("/api/projects/" + wsProject, { test_command: document.getElementById("ws-testcmd").value, deploy_command: document.getElementById("ws-deploycmd").value });
    cfgSave.textContent = "✓";
  };
  api.get("/api/sandbox/status").then(st => {
    const el = document.getElementById("ws-sandbox"); if (!el) return;
    if (st.enabled && st.reachable) el.innerHTML = `<span style="color:var(--green)">● Build-Container aktiv</span>`;
    else if (st.enabled) el.innerHTML = `<span style="color:var(--red)">● Sandbox offline</span>`;
    else el.textContent = "lokal (kein Build-Container)";
  });
  loadWorkshop();
}

async function loadWorkshop() {
  if (wsProject === null) return;
  const data = await api.get("/api/workspace?project_id=" + wsProject);
  const fEl = document.getElementById("ws-files");
  if (!fEl) return;
  fEl.innerHTML = data.files.length ? data.files.map(f =>
    `<div class="agent-row" style="padding:8px 11px">
      <i data-lucide="file" style="width:16px"></i>
      <div class="info" style="cursor:pointer" onclick="viewFile('${encodeURIComponent(f.path)}')"><b style="font-size:13px">${esc(f.path)}</b></div>
      <span class="tag">${f.size} B</span>
      ${/\.html?$/.test(f.path) ? `<a class="btn ghost sm" href="/api/workspace/download?project_id=${wsProject || ''}&path=${encodeURIComponent(f.path)}&inline=1" target="_blank" title="Vorschau"><i data-lucide="eye"></i></a>` : ''}
      <a class="btn ghost sm" href="/api/workspace/download?project_id=${wsProject || ''}&path=${encodeURIComponent(f.path)}" download><i data-lucide="download"></i></a>
    </div>`).join("") : `<div class="muted">Noch keine Dateien. Entwickler-Agenten legen hier Dateien an, oder lade selbst welche hoch.</div>`;
  const git = await api.get("/api/git/history?project_id=" + wsProject);
  const gEl = document.getElementById("ws-git");
  if (gEl) gEl.innerHTML = git.history.length ? git.history.map(h => `<div class="agent-row" style="padding:8px 11px">
    <i data-lucide="${h.verified ? 'badge-check' : 'git-commit'}" style="width:16px;color:${h.verified ? 'var(--green)' : 'var(--text-dim)'}"></i>
    <div class="info"><b style="font-size:13px">${esc(h.message)}</b><small>${esc(h.date)} · ${esc(h.sha)}</small></div>
    <button class="btn ghost sm" onclick="showDiff('${esc(h.sha)}')"><i data-lucide="file-diff"></i> Diff</button>
    <button class="btn ghost sm" onclick="rollbackTo('${esc(h.sha)}')"><i data-lucide="rotate-ccw"></i> hierhin zurück</button></div>`).join("")
    : `<div class="muted">Noch keine Versionen. Sie entstehen automatisch, wenn Agenten Dateien ändern.</div>`;
  if (gEl && !document.getElementById("ws-diff")) gEl.insertAdjacentHTML("afterend", `<pre id="ws-diff" class="diff-view hidden"></pre>`);
  const cons = await api.get("/api/console?project_id=" + wsProject);
  const cEl = document.getElementById("ws-console");
  cEl.innerHTML = cons.length ? cons.map(e =>
    `<div class="msg ${e.kind === 'exec' ? 'from-agent' : ''}" style="font-family:ui-monospace,monospace;font-size:12px">
      <div class="meta">${e.kind} · ${new Date(e.created_at).toLocaleTimeString("de-DE")}</div>
      <div class="body">${esc(e.text)}</div></div>`).join("") : `<div class="muted">Noch keine Ausführungen.</div>`;
  icons();
}

window.viewFile = async function (p) {
  const r = await api.get(`/api/workspace/file?project_id=${wsProject}&path=${p}`);
  document.getElementById("ws-view").textContent = r.content || "(leer)";
};
window.rollbackTo = async function (sha) {
  if (!confirm("Workspace auf Version " + sha + " zurücksetzen? Spätere Änderungen gehen verloren.")) return;
  const r = await api.post("/api/git/rollback", { project_id: wsProject ? Number(wsProject) : null, commit: sha });
  if (!r.ok) alert("Rollback fehlgeschlagen: " + (r.stderr || ""));
  loadWorkshop();
};
window.showDiff = async function (sha) {
  const el = document.getElementById("ws-diff");
  if (!el) return;
  el.classList.remove("hidden");
  el.textContent = "lade Diff …";
  const r = await api.get(`/api/git/diff?project_id=${wsProject || ''}&commit=${encodeURIComponent(sha)}`);
  const txt = ((r.stat ? r.stat + "\n\n" : "") + (r.diff || "")).trim();
  el.innerHTML = txt ? colorizeDiff(txt) : "(keine Änderungen)";
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
};
function colorizeDiff(txt) {
  return txt.split("\n").map(l => {
    const e = esc(l);
    if (l.startsWith("+") && !l.startsWith("+++")) return `<span class="d-add">${e}</span>`;
    if (l.startsWith("-") && !l.startsWith("---")) return `<span class="d-del">${e}</span>`;
    if (l.startsWith("@@")) return `<span class="d-hunk">${e}</span>`;
    return e;
  }).join("\n");
}

// ---------- Projekte ----------
async function renderProjects() {
  const [projects, agents] = await Promise.all([api.get("/api/projects"), api.get("/api/state")]);
  const teamCount = pid => agents.agents.filter(a => a.project_id === pid && a.status === "employed").length;
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <h3><i data-lucide="folder-plus"></i> Neues Projekt</h3>
      <input id="np-title" placeholder="Projekttitel"/>
      <textarea id="np-desc" placeholder="Ziel, Umfang, Frist …"></textarea>
      <div class="row"><button class="btn" id="np-send"><i data-lucide="rocket"></i> Projekt starten</button>
        <select id="np-tpl" style="width:auto;margin:0"><option value="">— oder Vorlage —</option></select>
        <button class="btn ghost" id="np-tplgo">aus Vorlage</button></div>
    </div>
    <div class="card"><h3><i data-lucide="folder-kanban"></i> Laufende Projekte</h3>
      ${projects.length ? projects.map(p => `<div class="agent-row">
        <div class="avatar role-project_manager"><i data-lucide="folder"></i></div>
        <div class="info"><b>#${p.id} ${esc(p.title)}</b><small>${teamCount(p.id)} Mitarbeiter · Status ${esc(p.status)}</small></div>
        <button class="btn ghost sm" onclick="gotoWorkshop(${p.id})"><i data-lucide="folder-code"></i> Werkstatt</button>
      </div>`).join("") : `<div class="empty">Noch keine Projekte. Starte oben eins.</div>`}
    </div>`;
  icons();
  document.getElementById("np-send").onclick = async () => {
    const t = document.getElementById("np-title").value.trim(); if (!t) return;
    await api.post("/api/projects", { title: t, description: document.getElementById("np-desc").value });
    renderProjects();
  };
  const tpls = await api.get("/api/templates");
  const sel = document.getElementById("np-tpl");
  sel.innerHTML = `<option value="">— oder Vorlage —</option>` + tpls.map(t => `<option value="${t.key}">${esc(t.title)} (${t.milestones.length} Schritte)</option>`).join("");
  document.getElementById("np-tplgo").onclick = async () => {
    const key = sel.value; if (!key) return;
    const title = document.getElementById("np-title").value.trim() || sel.options[sel.selectedIndex].text;
    await api.post("/api/projects/from-template", { template: key, title, description: document.getElementById("np-desc").value });
    renderProjects();
  };
}
window.gotoWorkshop = (pid) => {
  wsProject = pid;
  document.querySelector('.nav-item[data-view="workshop"]').click();
};

// ---------- Fortschritt ----------
async function renderProgress() {
  const projects = await api.get("/api/projects");
  const opts = [`<option value="">Firma gesamt / Einzelaufgaben</option>`]
    .concat(projects.map(p => `<option value="${p.id}" ${progProject == p.id ? "selected" : ""}>#${p.id} ${esc(p.title)}</option>`)).join("");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <div class="row"><h3 style="margin:0"><i data-lucide="gauge"></i> Projekt</h3>
        <div class="spacer" style="flex:1"></div>
        <select id="pg-proj" style="width:auto;margin:0">${opts}</select></div>
    </div>
    <div id="pg-body"></div>`;
  icons();
  document.getElementById("pg-proj").onchange = e => { progProject = e.target.value; loadProgress(); };
  loadProgress();
}

function bar(pct, color) {
  return `<div style="background:var(--bg-2);border-radius:8px;height:14px;overflow:hidden;border:1px solid var(--border)">
    <div style="width:${pct}%;height:100%;background:${color}"></div></div>`;
}

async function loadProgress() {
  const body = document.getElementById("pg-body");
  if (!body) return;
  const pid = progProject === "" ? "" : "project_id=" + progProject;
  const [prog, decisions, milestones] = await Promise.all([
    api.get("/api/progress" + (pid ? "?" + pid : "")),
    api.get("/api/decisions" + (pid ? "?" + pid : "")),
    api.get("/api/milestones" + (pid ? "?" + pid : "")),
  ]);
  const stCls = { planned: "resigned", in_progress: "employed", done: "employed" };
  const stTxt = { planned: "geplant", in_progress: "läuft", done: "✓ erledigt" };
  body.innerHTML = `
    <div class="grid cols-2" style="margin-bottom:14px">
      <div class="card"><div class="stat-label">Aufgaben erledigt</div>
        <div class="stat">${prog.tasks_done}/${prog.tasks_total} <span class="muted" style="font-size:15px">(${prog.task_percent}%)</span></div>
        ${bar(prog.task_percent, "var(--green)")}
        <div class="muted" style="margin-top:6px">${prog.tasks_in_progress} in Arbeit</div></div>
      <div class="card"><div class="stat-label">Meilensteine erreicht</div>
        <div class="stat">${prog.milestones_done}/${prog.milestones_total} <span class="muted" style="font-size:15px">(${prog.milestone_percent}%)</span></div>
        ${bar(prog.milestone_percent, "var(--accent)")}</div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="flag"></i> Roadmap / Zwischenschritte</h3>
      ${(prog.milestones && prog.milestones.length) ? prog.milestones.map(m => {
        const due = m.due_date ? new Date(m.due_date) : null;
        const soon = due && !m.overdue && m.status !== 'done' && m.due_in_days !== null && m.due_in_days <= 2;
        const dueBadge = m.overdue ? `<span class="pill fired">⚠️ überfällig</span>`
          : (soon ? `<span class="pill resigned">⏳ bald fällig</span>` : '');
        const dueTxt = due ? `Frist ${due.toLocaleDateString('de-DE')}${(m.status!=='done' && m.due_in_days!==null) ? ` (${m.due_in_days>=0?'in '+m.due_in_days+' T':Math.abs(m.due_in_days)+' T über'})` : ''}` : '';
        return `<div style="border:1px solid ${m.overdue ? 'var(--red)' : 'var(--border)'};border-radius:10px;padding:11px 13px;margin-bottom:9px;background:var(--bg-2)">
        <div class="row">
          <div class="avatar role-${m.status === 'done' ? 'developer' : (m.status === 'in_progress' ? 'project_manager' : 'planner')}" style="width:32px;height:32px">
            <i data-lucide="${m.status === 'done' ? 'check' : (m.status === 'in_progress' ? 'loader' : 'circle')}"></i></div>
          <div style="flex:1"><b>${esc(m.title)}</b>${m.description ? `<br><small class="muted">${esc(m.description)}</small>` : ''}</div>
          ${dueBadge}
          <span class="pill ${stCls[m.status]}">${stTxt[m.status]}</span>
          ${m.status !== 'done' ? `<button class="btn ghost sm" onclick="msDone(${m.id})"><i data-lucide="check"></i></button>` : ''}
          <button class="btn red sm" onclick="msDel(${m.id})"><i data-lucide="trash-2"></i></button>
        </div>
        <div class="row" style="margin-top:8px;gap:8px">
          <div style="flex:1">${bar(m.percent, m.status === 'done' ? 'var(--green)' : (m.overdue ? 'var(--red)' : 'var(--accent)'))}</div>
          <small class="muted" style="white-space:nowrap">${m.tasks_done}/${m.tasks_total} Aufgaben</small>
        </div>
        <div class="row" style="margin-top:5px;gap:8px">
          <small class="${m.overdue ? '' : 'muted'}" style="${m.overdue ? 'color:var(--red)' : ''}">${dueTxt || 'keine Frist'}${m.completed_at ? ' · erledigt ' + new Date(m.completed_at).toLocaleDateString('de-DE') : ''}</small>
          <span class="spacer" style="flex:1"></span>
          <input type="date" onchange="msDue(${m.id}, this.value)" style="width:auto;margin:0;padding:3px 7px" ${due ? `value="${m.due_date.slice(0,10)}"` : ''}/>
        </div>
      </div>`; }).join("") : `<div class="muted">Noch keine Meilensteine. Der Projektleiter plant sie automatisch – oder lege selbst welche an:</div>`}
      ${prog.unassigned_tasks ? `<div class="tag" style="margin-top:4px">${prog.unassigned_done}/${prog.unassigned_tasks} Aufgaben ohne Meilenstein</div>` : ''}
      <div class="row" style="margin-top:10px"><input id="ms-title" placeholder="Eigener Meilenstein" style="margin:0"/>
        <input id="ms-due" type="date" style="width:auto;margin:0" title="Frist (optional)"/>
        <button class="btn sm" id="ms-add" style="white-space:nowrap"><i data-lucide="plus"></i> Hinzufügen</button></div>
    </div>
    <div class="card"><h3><i data-lucide="brain"></i> Entscheidungen der KI – warum &amp; was</h3>
      ${decisions.length ? decisions.map(d => `<div class="msg from-agent">
        <div class="meta"><b>${esc(d.agent)}</b><span class="spacer" style="flex:1"></span>${new Date(d.created_at).toLocaleString('de-DE')}</div>
        ${d.thoughts ? `<div class="body"><b>Warum:</b> ${esc(d.thoughts)}</div>` : ''}
        <div class="body"><b>Was/wie:</b> ${esc(d.actions_summary)}</div>
        ${d.trigger ? `<div class="tag" style="margin-top:6px">Auslöser: ${esc(d.trigger.slice(0,160))}</div>` : ''}
      </div>`).join("") : `<div class="empty">Noch keine Entscheidungen protokolliert.</div>`}
    </div>`;
  icons();
  document.getElementById("ms-add").onclick = async () => {
    const t = document.getElementById("ms-title").value.trim(); if (!t) return;
    await api.post("/api/milestones", { project_id: progProject === "" ? null : Number(progProject),
      title: t, due_date: document.getElementById("ms-due").value || null });
    loadProgress();
  };
}
window.msDone = async (id) => { await api.put("/api/milestones/" + id, { status: "done" }); loadProgress(); };
window.msDel = async (id) => { await fetch("/api/milestones/" + id, { method: "DELETE" }); loadProgress(); };
window.msDue = async (id, val) => { await api.put("/api/milestones/" + id, { due_date: val || null }); loadProgress(); };

// ---------- Wissensspeicher ----------
async function renderKnowledge() {
  const docs = await api.get("/api/knowledge");
  const vault = await api.get("/api/vault");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="notebook-pen"></i> Obsidian-Vault (Gehirn)
      <span class="pill ${vault.enabled ? 'employed' : 'resigned'}">${vault.enabled ? 'aktiv' : 'aus'}</span></h3>
      ${vault.enabled ? `
        <div class="row"><input id="vn-title" placeholder="Notiz-Titel" style="margin:0"/>
          <button class="btn sm" id="vn-add" style="white-space:nowrap"><i data-lucide="plus"></i> Notiz</button></div>
        <textarea id="vn-content" placeholder="Markdown-Inhalt … [[Verlinkungen]] erlaubt"></textarea>
        <div class="stat-label" style="margin-top:6px">Notizen (${vault.notes.length})</div>
        ${vault.notes.length ? vault.notes.map(n => `<div class="agent-row" style="padding:7px 11px;cursor:pointer" onclick="viewNote('${encodeURIComponent(n.name)}')">
          <i data-lucide="file-text" style="width:15px"></i><div class="info"><b style="font-size:13px">${esc(n.name)}</b></div></div>`).join("") : `<div class="muted">noch keine</div>`}
        <pre id="vn-view" style="white-space:pre-wrap;max-height:200px;overflow:auto;color:var(--text-dim);margin-top:8px"></pre>
      ` : `<div class="tag">Setze <code>OBSIDIAN_VAULT</code> und hänge deinen Vault-Ordner im Compose ein (<code>- /pfad/Vault:/data/vault</code>). Dann schreiben Agenten Notizen hierher und durchsuchen sie.</div>`}
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="brain"></i> Wissen hinzufügen</h3>
      <input id="kn-title" placeholder="Titel (z. B. Markenrichtlinie, API-Doku)"/>
      <textarea id="kn-content" placeholder="Inhalt/Notiz, den die Agenten durchsuchen können …"></textarea>
      <div class="row"><button class="btn" id="kn-add"><i data-lucide="plus"></i> Speichern</button>
        <button class="btn ghost" id="kn-up"><i data-lucide="upload"></i> Datei (txt/md/pdf/docx)</button>
        <button class="btn ghost" id="kn-web"><i data-lucide="globe"></i> Webseite einlesen</button>
        <button class="btn ghost" id="kn-reindex" title="Embeddings neu berechnen"><i data-lucide="sparkles"></i> Vektor-Index</button>
        <input type="file" id="kn-file" class="hidden"/></div>
      <span class="muted" id="kn-idxstatus"></span>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="search"></i> Wissen durchsuchen</h3>
      <div class="row"><input id="kn-q" placeholder="Suchbegriff …" style="margin:0" onkeydown="if(event.key==='Enter')knSearch()"/>
        <button class="btn sm" onclick="knSearch()">suchen</button></div>
      <div id="kn-results" style="margin-top:10px"></div>
    </div>
    <div class="card"><h3><i data-lucide="library"></i> Dokumente (${docs.length})</h3>
      ${docs.length ? docs.map(d => `<div class="agent-row">
        <div class="avatar role-planner"><i data-lucide="${d.source === 'upload' ? 'file' : 'sticky-note'}"></i></div>
        <div class="info"><b>${esc(d.title)}</b><small>${d.chars} Zeichen · ${d.source}</small></div>
        <button class="btn red sm" onclick="delDoc(${d.id})"><i data-lucide="trash-2"></i></button></div>`).join("")
      : `<div class="muted">Noch kein Wissen. Agenten nutzen es per <code>search_memory</code> – plus alle früheren Entscheidungen.</div>`}
    </div>`;
  icons();
  document.getElementById("kn-add").onclick = async () => {
    const t = document.getElementById("kn-title").value.trim(); if (!t) return;
    await api.post("/api/knowledge", { title: t, content: document.getElementById("kn-content").value });
    renderKnowledge();
  };
  const vnAdd = document.getElementById("vn-add");
  if (vnAdd) vnAdd.onclick = async () => {
    const t = document.getElementById("vn-title").value.trim(); if (!t) return;
    await api.post("/api/vault/note", { title: t, content: document.getElementById("vn-content").value });
    renderKnowledge();
  };
  document.getElementById("kn-reindex").onclick = async () => {
    document.getElementById("kn-idxstatus").textContent = "indexiere …";
    const r = await api.post("/api/knowledge/reindex");
    document.getElementById("kn-idxstatus").textContent = r.available ? `✓ Vektor-Suche aktiv (${r.indexed} Dok.)` : "Keine Embeddings verfügbar – Stichwortsuche (OpenAI-Key oder Ollama nutzen)";
  };
  document.getElementById("kn-up").onclick = () => document.getElementById("kn-file").click();
  document.getElementById("kn-file").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    await fetch("/api/knowledge/upload", { method: "POST", body: fd });
    renderKnowledge();
  };
  document.getElementById("kn-web").onclick = async () => {
    const url = prompt("URL der Webseite, die eingelesen werden soll:");
    if (!url) return;
    const st = document.getElementById("kn-idxstatus");
    st.textContent = "lese Webseite …";
    try {
      const r = await api.post("/api/knowledge/web", { url });
      st.textContent = r && r.ok ? `✓ „${r.title || url}" gespeichert` : "Konnte Seite nicht laden";
    } catch (_) { st.textContent = "Fehler beim Laden der Seite"; }
    renderKnowledge();
  };
}
window.knSearch = async () => {
  const q = document.getElementById("kn-q").value.trim();
  const el = document.getElementById("kn-results");
  if (!q) { el.innerHTML = ""; return; }
  const r = await api.get("/api/knowledge/search?q=" + encodeURIComponent(q));
  el.innerHTML = r.results.length ? r.results.map(h => `<div class="msg from-agent"><div class="subject">${esc(h.source)}</div><div class="body">${esc(h.snippet)}</div></div>`).join("") : `<div class="muted">Keine Treffer.</div>`;
};
window.delDoc = async (id) => { await fetch("/api/knowledge/" + id, { method: "DELETE" }); renderKnowledge(); };
window.viewNote = async (name) => {
  const r = await api.get("/api/vault/note?name=" + name);
  document.getElementById("vn-view").textContent = r.content || "(leer)";
};

// ---------- Cookbook / Regelwerk ----------
async function renderCookbook() {
  const rules = await api.get("/api/rules");
  const scopeLabel = { global: "Global", role: "Rolle", project: "Projekt" };
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <h3><i data-lucide="book-plus"></i> Neue Regel / Standard</h3>
      <input id="cb-title" placeholder="Titel (z. B. Code-Stil, Designsprache, Lieferformat)"/>
      <textarea id="cb-content" placeholder="Die Regel: Wie muss etwas aussehen? Welche Standards gelten?"></textarea>
      <div class="row"><select id="cb-scope" style="margin:0">
        <option value="global">Global (für alle)</option>
        <option value="role">Pro Rolle</option>
        <option value="project">Pro Projekt</option></select>
        <input id="cb-role" placeholder="Rolle (z. B. developer)" style="margin:0"/>
        <button class="btn" id="cb-add" style="white-space:nowrap"><i data-lucide="plus"></i> Anlegen</button></div>
    </div>
    <div class="card"><h3><i data-lucide="book-open"></i> Regelwerk</h3>
      ${rules.length ? rules.map(r => `<div class="msg ${r.active ? '' : 'needs-answer'}">
        <div class="meta"><span class="tag">${scopeLabel[r.scope] || r.scope}${r.role ? ': ' + esc(r.role) : ''}</span>
          <span class="tag">${r.source === 'agent' ? '🤖 KI' : '👤 Du'}</span>
          <span class="spacer" style="flex:1"></span>
          <span class="toggle" onclick="toggleRule(${r.id},${!r.active})"><div class="switch ${r.active ? 'on' : ''}"></div></span>
          <button class="btn red sm" onclick="delRule(${r.id})"><i data-lucide="trash-2"></i></button></div>
        <div class="subject">${esc(r.title)}</div><div class="body">${esc(r.content)}</div></div>`).join("")
      : `<div class="empty">Noch keine Regeln. Lege Standards an – Agenten halten sich daran.</div>`}
    </div>`;
  icons();
  document.getElementById("cb-add").onclick = async () => {
    const title = document.getElementById("cb-title").value.trim(); if (!title) return;
    await api.post("/api/rules", {
      title, content: document.getElementById("cb-content").value,
      scope: document.getElementById("cb-scope").value,
      role: document.getElementById("cb-role").value.trim() || null,
    });
    renderCookbook();
  };
}
window.toggleRule = async (id, active) => { await api.put("/api/rules/" + id, { active }); renderCookbook(); };
window.delRule = async (id) => { await fetch("/api/rules/" + id, { method: "DELETE" }); renderCookbook(); };

// ---------- Skills & MCP ----------
async function renderSkills() {
  const [skills, mcp] = await Promise.all([api.get("/api/skills"), api.get("/api/mcp")]);
  root.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3><i data-lucide="puzzle"></i> Skills</h3>
        ${skills.length ? skills.map(s => `<div class="agent-row">
          <div class="avatar role-developer"><i data-lucide="zap"></i></div>
          <div class="info"><b>${esc(s.name)}</b><small>${esc(s.description)}${s.command ? ' · ⚙️ Befehl' : ''}</small></div>
          <span class="pill ${s.enabled ? 'employed' : 'resigned'}">${s.enabled ? 'aktiv' : 'aus'}</span>
          <button class="btn red sm" onclick="delSkill(${s.id})"><i data-lucide="trash-2"></i></button></div>`).join("") : `<div class="muted">keine</div>`}
        <hr style="border-color:var(--border);margin:12px 0"/>
        <input id="sk-name" placeholder="Skill-Name (z. B. unit_tests)"/>
        <input id="sk-desc" placeholder="Kurzbeschreibung"/>
        <textarea id="sk-instr" placeholder="Anweisung/Vorgehen (Prompt-Vorlage)"></textarea>
        <input id="sk-cmd" placeholder="Optionaler Befehl, {args} wird ersetzt (z. B. pytest {args})"/>
        <button class="btn" id="sk-add"><i data-lucide="plus"></i> Skill speichern</button>
      </div>
      <div class="card"><h3><i data-lucide="server"></i> MCP-Server</h3>
        ${mcp.length ? mcp.map(m => {
          const statusCls = m.status === 'connected' ? 'employed' : (m.status === 'error' ? 'fired' : 'resigned');
          const toolList = (m.tools || []).map(t => `<span class="tag" title="${esc(t.description)}">${esc(t.name)}</span>`).join(" ");
          return `<div class="msg">
            <div class="meta"><b>${esc(m.name)}</b> <span class="tag">${esc(m.transport)}</span>
              <span class="pill ${statusCls}">${m.status === 'connected' ? '✓ verbunden' : (m.status === 'error' ? '✕ Fehler' : 'unverbunden')}</span>
              <span class="spacer" style="flex:1"></span>
              <button class="btn ghost sm" onclick="mcpConnect(${m.id})"><i data-lucide="refresh-cw"></i> Verbinden</button>
              <button class="btn red sm" onclick="delMcp(${m.id})"><i data-lucide="trash-2"></i></button></div>
            <div class="body">${esc(m.description)}</div>
            ${toolList ? `<div style="margin-top:6px">Tools: ${toolList}</div>` : ''}
            ${m.status === 'error' && m.last_error ? `<div class="tag" style="color:var(--red);margin-top:6px">${esc(m.last_error)}</div>` : ''}
          </div>`;
        }).join("") : `<div class="muted">keine</div>`}
        <hr style="border-color:var(--border);margin:12px 0"/>
        <input id="mc-name" placeholder="Name (z. B. github)"/>
        <input id="mc-desc" placeholder="Beschreibung / Zweck"/>
        <div class="row"><select id="mc-transport" style="margin:0"><option value="stdio">stdio</option><option value="http">http</option></select>
          <input id="mc-target" placeholder="Befehl oder URL" style="margin:0"/></div>
        <button class="btn" id="mc-add"><i data-lucide="plus"></i> MCP-Server speichern</button>
        <div class="tag" style="margin-top:8px">Demo: Name <b>demo</b>, stdio, Befehl <code>python -m backend.app.mcp_demo_server</code></div>
      </div>
    </div>`;
  icons();
  document.getElementById("sk-add").onclick = async () => {
    const name = document.getElementById("sk-name").value.trim(); if (!name) return;
    await api.post("/api/skills", { name, description: document.getElementById("sk-desc").value,
      instructions: document.getElementById("sk-instr").value, command: document.getElementById("sk-cmd").value });
    renderSkills();
  };
  document.getElementById("mc-add").onclick = async () => {
    const name = document.getElementById("mc-name").value.trim(); if (!name) return;
    const tr = document.getElementById("mc-transport").value, tgt = document.getElementById("mc-target").value;
    await api.post("/api/mcp", { name, description: document.getElementById("mc-desc").value,
      transport: tr, command: tr === "stdio" ? tgt : "", url: tr === "http" ? tgt : "" });
    renderSkills();
  };
}
window.delSkill = async (id) => { await fetch("/api/skills/" + id, { method: "DELETE" }); renderSkills(); };
window.delMcp = async (id) => { await fetch("/api/mcp/" + id, { method: "DELETE" }); renderSkills(); };
window.mcpConnect = async (id) => {
  const r = await api.post(`/api/mcp/${id}/connect`);
  if (r.status === "error") alert("Verbindung fehlgeschlagen: " + (r.error || ""));
  renderSkills();
};

// ---------- Approvals ----------
async function renderApprovals() {
  const items = await api.get("/api/approvals");
  root.innerHTML = `<div class="card"><h3><i data-lucide="shield-check"></i> Wartende Freigaben</h3>
    ${items.length ? items.map(a => `<div class="agent-row"><div class="info"><b>${esc(a.summary)}</b><small>${esc(JSON.stringify(a.action))}</small></div>
      <button class="btn green sm" onclick="decide(${a.id},'approve')"><i data-lucide="check"></i> Freigeben</button>
      <button class="btn red sm" onclick="decide(${a.id},'reject')"><i data-lucide="x"></i> Ablehnen</button></div>`).join("") : `<div class="empty">Keine offenen Freigaben.</div>`}</div>`;
  icons();
}
window.decide = async (id, d) => { await api.post(`/api/approvals/${id}/${d}`); renderApprovals(); refreshBadges(); };

// ---------- Activity ----------
async function renderActivity() {
  const evs = await api.get("/api/events");
  const ic = { hire: "user-plus", fire: "user-minus", resign: "door-open", task: "list-checks", rating: "star", message: "mail", error: "alert-triangle", info: "info", milestone: "flag", deadline: "alarm-clock", mcp: "plug", file: "file", exec: "terminal", rule: "book", skill: "zap", git: "git-branch", audit: "shield", email: "send", loop: "rotate-cw" };
  root.innerHTML = `<div class="card"><h3><i data-lucide="activity"></i> Aktivitäts-Log</h3>
    ${evs.length ? evs.map(e => `<div class="agent-row"><div class="avatar" style="background:var(--panel-2);color:var(--text-dim)"><i data-lucide="${ic[e.kind] || "circle"}"></i></div>
      <div class="info"><b>${esc(e.text)}</b><small>${e.agent ? esc(e.agent) + " · " : ""}${new Date(e.created_at).toLocaleString("de-DE")}</small></div></div>`).join("") : `<div class="empty">Noch keine Aktivität.</div>`}</div>`;
  icons();
}

// ---------- Settings ----------
async function renderSettings() {
  const s = await api.get("/api/settings");
  const sec = await api.get("/api/secrets");
  const bud = await api.get("/api/budget");
  const recurring = await api.get("/api/recurring");
  const hist = await api.get("/api/budget/history");
  const twofa = CURRENT_USER && CURRENT_USER.totp_enabled;
  const maxCost = Math.max(0.0001, ...hist.series.map(p => p.cost));
  const chart = hist.series.length ? `<div class="row" style="align-items:flex-end;gap:3px;height:60px;margin-top:8px">` +
    hist.series.map(p => `<div title="${p.date}: $${p.cost.toFixed(4)}" style="flex:1;background:var(--accent);height:${Math.max(2, Math.round(100 * p.cost / maxCost))}%"></div>`).join("") + `</div>` : "";
  const provList = Object.keys(s.providers_available).filter(p => p !== "mock");
  const provOpts = (sel) => provList.map(p => `<option ${sel === p ? "selected" : ""} value="${p}">${p}${s.providers_available[p] ? "" : " (kein Key → Mock)"}</option>`).join("");
  const autoOpts = { full: "Voll autonom (keine Rückfragen)", ask_for_hiring: "Nachfragen bei Einstellung/Kündigung", ask_for_everything: "Bei allem Wichtigen nachfragen" };
  const schedOpts = { always: "Dauerbetrieb (immer)", window: "Nur in einem Zeitfenster", manual: "Nur manuell (auf Knopfdruck)" };
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="lock"></i> Konto & Sicherheit</h3>
      <label>Aktuelles Passwort</label><input id="pw-old" type="password" autocomplete="current-password"/>
      <label>Neues Passwort (min. 6 Zeichen)</label><input id="pw-new" type="password" autocomplete="new-password"/>
      <button class="btn" id="pw-save"><i data-lucide="key"></i> Passwort ändern</button>
      <span class="muted" id="pw-status" style="margin-left:8px"></span>
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="row"><b style="flex:1">Zwei-Faktor-Authentifizierung (2FA)</b>
        <span class="pill ${twofa ? 'employed' : 'resigned'}">${twofa ? 'aktiv' : 'aus'}</span>
        ${twofa ? `<button class="btn ghost sm" id="twofa-off">deaktivieren</button>`
          : `<button class="btn ghost sm" id="twofa-on"><i data-lucide="shield"></i> einrichten</button>`}</div>
      <div id="twofa-area"></div>
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="row"><b style="flex:1">Angemeldete Sitzungen</b>
        <button class="btn ghost sm" id="sess-others"><i data-lucide="log-out"></i> Andere abmelden</button></div>
      <div id="sess-list" class="muted" style="margin-top:8px">lade …</div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="repeat"></i> Wiederkehrende Aufträge</h3>
      ${recurring.length ? recurring.map(j => `<div class="agent-row">
        <div class="info"><b>${esc(j.title)}</b><small>${j.interval}${j.interval !== 'hourly' ? ' · ' + j.hour + ' Uhr' : ''}${j.as_project ? ' · Projekt' : ' · Einzelaufgabe'}</small></div>
        <button class="btn red sm" onclick="delRecurring(${j.id})"><i data-lucide="trash-2"></i></button></div>`).join("") : `<div class="muted">keine</div>`}
      <div class="row" style="margin-top:8px"><input id="rec-title" placeholder="Auftrag (z. B. Wochenreport)" style="margin:0"/>
        <select id="rec-int" style="width:auto;margin:0"><option value="daily">täglich</option><option value="weekly">wöchentlich</option><option value="hourly">stündlich</option></select>
        <button class="btn sm" id="rec-add" style="white-space:nowrap"><i data-lucide="plus"></i> anlegen</button></div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="archive"></i> Sicherung (Backup)</h3>
      <div class="row" style="flex-wrap:wrap"><button class="btn" id="bk-full"><i data-lucide="archive"></i> Vollständiges Backup (ZIP)</button>
        <button class="btn ghost" id="bk-export"><i data-lucide="download"></i> Snapshot (JSON)</button>
        <button class="btn ghost" id="bk-import"><i data-lucide="upload"></i> Regeln/Skills/MCP importieren</button>
        <button class="btn ghost" id="bk-restore"><i data-lucide="upload-cloud"></i> Aus ZIP wiederherstellen</button>
        <input type="file" id="bk-file" class="hidden" accept="application/json"/>
        <input type="file" id="bk-zip" class="hidden" accept=".zip,application/zip"/></div>
      <div class="row" style="margin-top:10px"><div class="toggle" id="s-autobak"><div class="switch ${s.auto_backup ? 'on' : ''}"></div> Automatische tägliche Sicherung</div>
        <input id="s-bakkeep" type="number" min="1" max="60" value="${s.backup_keep || 7}" style="width:90px;margin-left:10px" title="Wie viele Sicherungen behalten"/>
        <button class="btn ghost sm" id="bk-now" style="margin-left:10px">jetzt sichern</button></div>
      <div id="bk-list" class="muted" style="margin-top:8px"></div>
      <div class="tag" style="margin-top:8px">Vollständiges Backup enthält DB-Snapshot, alle Projekt-Workspaces und die Vault-Notizen. Automatische Sicherungen liegen unter <code>/data/backups</code> im Container.</div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="clock"></i> Zeitplan – wann die KI prüft & beobachtet</h3>
      <div class="grid cols-2" style="gap:10px">
        <div><label>Modus</label>
          <select id="s-sched">${Object.keys(schedOpts).map(k => `<option value="${k}" ${s.schedule_mode === k ? "selected" : ""}>${schedOpts[k]}</option>`).join("")}</select></div>
        <div><label>Takt (Sekunden zwischen den Prüfungen)</label>
          <input id="s-tick" type="number" min="1" step="1" value="${s.tick_seconds}"/></div>
      </div>
      <div id="s-window" class="row" style="${s.schedule_mode === 'window' ? '' : 'display:none'}">
        <div style="flex:1"><label>Aktiv ab (Stunde)</label><input id="s-from" type="number" min="0" max="23" value="${s.active_from}"/></div>
        <div style="flex:1"><label>Aktiv bis (Stunde)</label><input id="s-to" type="number" min="0" max="24" value="${s.active_to}"/></div>
      </div>
      <div class="row"><button class="btn" id="s-runnow"><i data-lucide="play"></i> Jetzt prüfen</button>
        <span class="muted" id="run-info"></span></div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="brain-circuit"></i> Arbeitsweise – erst denken, dann arbeiten</h3>
      <label>Denkmodus</label>
      <select id="s-think">
        <option value="off" ${s.thinking_mode === 'off' ? 'selected' : ''}>Aus (sofort handeln)</option>
        <option value="think" ${s.thinking_mode === 'think' ? 'selected' : ''}>Nachdenken (Plan vor dem Handeln)</option>
        <option value="deep" ${s.thinking_mode === 'deep' ? 'selected' : ''}>Tiefenrecherche (erst recherchieren/lesen, dann handeln)</option>
      </select>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-verify"><div class="switch ${s.require_verification ? 'on' : ''}"></div> <b>Vor „fertig" verifizieren</b> (Entwickler/QA müssen testen – keine Regressionen)</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-incr"><div class="switch ${s.incremental_mode ? 'on' : ''}"></div> Kleine Teilschritte & minimaler Code (nicht alles auf einmal)</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-review"><div class="switch ${s.require_review ? 'on' : ''}"></div> 4-Augen-Prinzip: Entwicklerarbeit muss reviewt werden</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-risk"><div class="switch ${s.risk_approval ? 'on' : ''}"></div> Riskante Befehle (rm -rf, push, deploy …) erst freigeben</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-route"><div class="switch ${s.model_routing ? 'on' : ''}"></div> Modell-Routing: Entwickler/QA nutzen das stärkere (Chef-)Modell</div></div>
      <div class="tag" style="margin-top:8px">Ist „verifizieren" an, blockiert das System den Abschluss einer Entwickler-/QA-Aufgabe, bis ein Test/Smoke-Check erfolgreich lief. Bei Provider-Fehlern wird automatisch ein anderer verfügbarer Anbieter genutzt.</div>
    </div>
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="wallet"></i> Budget & Kosten ${bud.paused ? '<span class="pill fired">pausiert</span>' : ''}</h3>
      <div class="row" style="gap:18px;margin-bottom:10px">
        <div><div class="stat-label">Verbraucht</div><div class="stat">$${bud.spent.toFixed(4)}</div></div>
        <div><div class="stat-label">Tokens (ein/aus)</div><div class="stat" style="font-size:18px">${bud.input_tokens}/${bud.output_tokens}</div></div>
        <div><div class="stat-label">Aufrufe</div><div class="stat" style="font-size:18px">${bud.calls}</div></div>
      </div>
      ${bud.limit > 0 ? bar(Math.min(100, Math.round(100 * bud.spent / bud.limit)), bud.paused ? 'var(--red)' : 'var(--accent)') : ''}
      <label style="margin-top:10px">Budget-Limit in USD (0 = unbegrenzt) – bei Überschreitung pausiert die Firma automatisch</label>
      <input id="s-budget" type="number" min="0" step="1" value="${bud.limit}"/>
      ${chart ? `<div class="stat-label" style="margin-top:8px">Verlauf (täglich)</div>${chart}` : ''}
      ${bud.by_model.length ? `<div class="stat-label" style="margin-top:6px">Je Modell</div>` + bud.by_model.map(m => `<div class="row"><small style="flex:1">${esc(m.model)}</small><small>$${m.cost.toFixed(4)}</small></div>`).join("") : ''}
      <div class="tag" style="margin-top:8px">Kosten sind Schätzungen (lokale Modelle = $0). Budget erhöhen hebt eine Pausierung wieder auf.</div>
    </div>
    <div class="grid cols-2">
      <div class="card"><h3><i data-lucide="sliders"></i> Autonomie & Freigaben</h3>
        <label>Autonomie-Stufe</label>
        <select id="s-autonomy">${Object.keys(autoOpts).map(k => `<option value="${k}" ${s.autonomy_level === k ? "selected" : ""}>${autoOpts[k]}</option>`).join("")}</select>
        <div class="row"><div class="toggle" id="s-run"><div class="switch ${s.auto_run ? "on" : ""}"></div> Agenten laufen automatisch</div></div>
        <div class="row" style="margin-top:10px"><div class="toggle" id="s-hire"><div class="switch ${s.require_approval_hire ? "on" : ""}"></div> Einstellung freigeben</div></div>
        <div class="row" style="margin-top:10px"><div class="toggle" id="s-fire"><div class="switch ${s.require_approval_fire ? "on" : ""}"></div> Kündigung freigeben</div></div>
        <div class="row" style="margin-top:10px"><div class="toggle" id="s-code"><div class="switch ${s.enable_code_exec ? "on" : ""}"></div> Code-Werkstatt (Dateien & Ausführung) erlauben</div></div>
        <label style="margin-top:12px">Kündigungsschwelle (Ø Bewertung)</label>
        <input id="s-thresh" type="number" min="1" max="5" step="0.5" value="${s.fire_threshold}" />
      </div>
      <div class="card"><h3><i data-lucide="cpu"></i> Modelle pro Rolle</h3>
        <label>Chef – Provider</label><select id="s-cp">${provOpts(s.default_chef_provider)}</select>
        <label>Chef – Modell</label><input id="s-cm" value="${esc(s.default_chef_model)}" />
        <label>Mitarbeiter – Provider</label><select id="s-wp">${provOpts(s.default_worker_provider)}</select>
        <label>Mitarbeiter – Modell</label><input id="s-wm" value="${esc(s.default_worker_model)}" />
        <label>Erlaubte Provider (CSV)</label><input id="s-allowed" value="${esc(s.allowed_providers)}" />
      </div>
    </div>
    <div style="margin-top:14px"><button class="btn" id="s-save"><i data-lucide="save"></i> Einstellungen speichern</button>
      <span class="muted" id="s-status" style="margin-left:10px"></span></div>
    <div class="card" style="margin-top:16px"><h3><i data-lucide="plug"></i> Provider-Status</h3>
      ${Object.entries(s.providers_available).map(([k, v]) => `<span class="pill ${v ? "employed" : "resigned"}" style="margin-right:8px">${k}: ${v ? "verfügbar" : "Mock"}</span>`).join("")}
    </div>
    <div class="card" style="margin-top:16px"><h3><i data-lucide="key-round"></i> Zugangsdaten (direkt hier – keine .env nötig)</h3>
      <div class="tag" style="margin-bottom:10px">Leeres Feld = unverändert. Gespeicherte Werte werden aus Sicherheitsgründen nicht angezeigt. Quelle: <b>gui</b> = hier gesetzt, <b>env</b> = aus .env erkannt.</div>
      ${secField(sec, "ANTHROPIC_API_KEY", "Anthropic / Claude API-Key")}
      ${secField(sec, "OPENAI_API_KEY", "OpenAI API-Key")}
      ${secField(sec, "BRAVE_API_KEY", "Brave Search API-Key (optional)")}
      ${secField(sec, "GITHUB_TOKEN", "GitHub Token (für Repo/Push)")}
      ${secField(sec, "OPENROUTER_API_KEY", "OpenRouter API-Key")}
      ${secField(sec, "MISTRAL_API_KEY", "Mistral API-Key")}
      ${secField(sec, "GEMINI_API_KEY", "Google Gemini API-Key")}
      ${secField(sec, "SLACK_WEBHOOK", "Slack Incoming-Webhook URL")}
      ${secField(sec, "DISCORD_WEBHOOK", "Discord Webhook URL")}
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="stat-label" style="margin-bottom:6px">E-Mail senden (SMTP)</div>
      ${secField(sec, "SMTP_HOST", "SMTP-Server (z. B. smtp.gmail.com)")}
      ${secField(sec, "SMTP_PORT", "SMTP-Port (z. B. 587)")}
      ${secField(sec, "SMTP_USER", "SMTP-Benutzer / E-Mail")}
      ${secField(sec, "SMTP_PASS", "SMTP-Passwort / App-Passwort")}
      ${secField(sec, "SMTP_FROM", "Absender-Adresse (optional)")}
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="stat-label" style="margin-bottom:6px">E-Mail lesen (IMAP) – für den Assistenten</div>
      ${secField(sec, "IMAP_HOST", "IMAP-Server (z. B. imap.gmail.com)")}
      ${secField(sec, "IMAP_PORT", "IMAP-Port (z. B. 993)")}
      ${secField(sec, "IMAP_USER", "IMAP-Benutzer (leer = wie SMTP)")}
      ${secField(sec, "IMAP_PASS", "IMAP-Passwort (leer = wie SMTP)")}
      <button class="btn" id="sec-save"><i data-lucide="save"></i> Zugangsdaten speichern</button>
      <span class="muted" id="sec-status" style="margin-left:8px"></span>
    </div>
    <div class="card" style="margin-top:16px"><h3><i data-lucide="mail"></i> E-Mail & Benachrichtigungen</h3>
      <div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:10px">
        <span class="pill ${s.email_status.smtp ? 'employed' : 'resigned'}">SMTP (senden): ${s.email_status.smtp ? 'konfiguriert' : 'fehlt (.env)'}</span>
        <span class="pill ${s.email_status.imap ? 'employed' : 'resigned'}">IMAP (lesen): ${s.email_status.imap ? 'konfiguriert' : 'fehlt (.env)'}</span>
      </div>
      <label>Deine E-Mail (für Benachrichtigungen)</label>
      <input id="s-uemail" value="${esc(s.user_email || '')}" placeholder="du@beispiel.de"/>
      <div class="row" style="margin-top:6px"><div class="toggle" id="s-notif"><div class="switch ${s.email_notifications ? 'on' : ''}"></div> E-Mail-Benachrichtigungen aktiv</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-novd"><div class="switch ${s.notify_overdue ? 'on' : ''}"></div> bei Verzug</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-noq"><div class="switch ${s.notify_questions ? 'on' : ''}"></div> bei neuen Rückfragen</div></div>
      <div class="row" style="margin-top:8px"><div class="toggle" id="s-digest"><div class="switch ${s.daily_digest ? 'on' : ''}"></div> Täglicher Überblick per Mail</div>
        <button class="btn ghost sm" id="s-digestnow" style="margin-left:10px">jetzt senden</button></div>
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="row"><div class="toggle" id="s-aimail"><div class="switch ${s.assistant_email_access ? 'on' : ''}"></div> <b>Daily-Assistent darf meine E-Mails lesen</b></div></div>
      <hr style="border-color:var(--border);margin:12px 0"/>
      <div class="stat-label" style="margin-bottom:6px">Telegram (optional, für Benachrichtigungen)</div>
      <input id="s-tgtoken" value="${esc(s.telegram_token || '')}" placeholder="Bot-Token"/>
      <input id="s-tgchat" value="${esc(s.telegram_chat_id || '')}" placeholder="Chat-ID"/>
      <div class="tag" style="margin-top:4px">Zugangsdaten (SMTP/IMAP) trägst du oben unter „Zugangsdaten" ein.</div>
    </div>
    <div class="card" style="margin-top:16px"><h3><i data-lucide="server"></i> Lokale Modelle (Ollama)</h3>
      <label>Ollama-Server-URL (z. B. eigene Instanz: http://host.docker.internal:11434)</label>
      <div class="row" style="margin-bottom:10px"><input id="ol-url" placeholder="http://host.docker.internal:11434" style="margin:0"/>
        <button class="btn sm" id="ol-url-save"><i data-lucide="plug"></i> Verbinden</button>
        <span class="muted" id="ol-conn"></span></div>
      <div class="row" style="margin-bottom:10px"><input id="ol-name" placeholder="Modell ziehen, z. B. llama3.1" style="margin:0"/>
        <button class="btn sm" id="ol-pull"><i data-lucide="download"></i> Ziehen</button></div>
      <div id="ol-list"><div class="muted">lade …</div></div>
    </div>`;
  icons();
  loadOllama();
  document.getElementById("ol-url-save").onclick = async () => {
    const u = document.getElementById("ol-url").value.trim();
    await api.post("/api/secrets", { OLLAMA_BASE_URL: u });
    document.getElementById("ol-conn").textContent = "gespeichert – prüfe …";
    loadOllama();
  };
  document.getElementById("ol-pull").onclick = async () => {
    const n = document.getElementById("ol-name").value.trim(); if (!n) return;
    document.getElementById("ol-pull").textContent = "lädt …";
    await api.post("/api/ollama/pull", { name: n }); loadOllama();
  };
  const toggles = {};
  ["s-run", "s-hire", "s-fire", "s-code", "s-verify", "s-incr", "s-review", "s-risk", "s-route", "s-notif", "s-novd", "s-noq", "s-digest", "s-aimail", "s-autobak"].forEach(id => {
    const el = document.getElementById(id);
    toggles[id] = el.querySelector(".switch").classList.contains("on");
    el.onclick = () => { const sw = el.querySelector(".switch"); sw.classList.toggle("on"); toggles[id] = sw.classList.contains("on"); };
  });
  // Passwort ändern
  document.getElementById("pw-save").onclick = async () => {
    const r = await fetch("/api/auth/password", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: document.getElementById("pw-old").value, new_password: document.getElementById("pw-new").value }) });
    const d = await r.json().catch(() => ({}));
    document.getElementById("pw-status").textContent = r.status === 200 ? "✓ geändert" : ("✕ " + (d.detail || "Fehler"));
  };
  // 2FA
  const t2on = document.getElementById("twofa-on");
  if (t2on) t2on.onclick = async () => {
    const r = await api.post("/api/auth/2fa/setup");
    document.getElementById("twofa-area").innerHTML = `<div class="tag" style="margin-top:8px">In der Authenticator-App eintragen (oder Schlüssel <b>${esc(r.secret)}</b>):<br><code>${esc(r.otpauth)}</code></div>
      <div class="row" style="margin-top:8px"><input id="twofa-code" placeholder="6-stelliger Code" style="margin:0"/>
        <button class="btn sm" id="twofa-confirm">aktivieren</button></div>`;
    document.getElementById("twofa-confirm").onclick = async () => {
      const rr = await fetch("/api/auth/2fa/enable", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: document.getElementById("twofa-code").value }) });
      if (rr.status === 200) { alert("2FA aktiviert."); const m = await checkAuth(); CURRENT_USER = m; renderSettings(); }
      else alert("Code falsch.");
    };
  };
  const t2off = document.getElementById("twofa-off");
  if (t2off) t2off.onclick = async () => { await api.post("/api/auth/2fa/disable"); const m = await checkAuth(); CURRENT_USER = m; renderSettings(); };
  // Wiederkehrende Aufträge
  document.getElementById("rec-add").onclick = async () => {
    const t = document.getElementById("rec-title").value.trim(); if (!t) return;
    await api.post("/api/recurring", { title: t, interval: document.getElementById("rec-int").value });
    renderSettings();
  };
  document.getElementById("s-digestnow").onclick = async () => { await api.post("/api/digest/send"); alert("Digest gesendet (sofern E-Mail/Telegram konfiguriert)."); };
  // Backup
  document.getElementById("bk-full").onclick = () => window.open("/api/backup/full", "_blank");
  document.getElementById("bk-export").onclick = () => window.open("/api/backup/export", "_blank");
  document.getElementById("bk-import").onclick = () => document.getElementById("bk-file").click();
  document.getElementById("bk-file").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const data = JSON.parse(await f.text());
    await api.post("/api/backup/import-config", { rules: data.rules || [], skills: data.skills || [], mcp: data.mcp || [] });
    alert("Importiert."); renderSettings();
  };
  document.getElementById("bk-restore").onclick = () => document.getElementById("bk-zip").click();
  document.getElementById("bk-zip").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (!confirm("Aus diesem ZIP wiederherstellen? Vorhandenes wird ergänzt, nicht gelöscht.")) return;
    const fd = new FormData(); fd.append("file", f);
    const r = await fetch("/api/backup/restore-full", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    alert(r.status === 200 ? `Wiederhergestellt: ${JSON.stringify(d.restored)} · Dateien: ${d.files}` : "Fehler: " + (d.detail || r.status));
    renderSettings();
  };
  document.getElementById("bk-now").onclick = async () => {
    document.getElementById("bk-now").textContent = "sichert …";
    await api.post("/api/backup/auto/now"); loadBackups();
    document.getElementById("bk-now").textContent = "jetzt sichern";
  };
  async function loadBackups() {
    try {
      const r = await api.get("/api/backup/auto/list");
      const el = document.getElementById("bk-list");
      el.innerHTML = r.backups.length
        ? r.backups.map(b => `<div>📦 ${esc(b.name)} · ${(b.size / 1024).toFixed(0)} KB · ${b.created.replace('T', ' ').slice(0, 16)}</div>`).join("")
        : "Noch keine automatischen Sicherungen.";
    } catch (_) {}
  }
  loadBackups();
  // Sitzungen
  async function loadSessions() {
    try {
      const r = await api.get("/api/auth/sessions");
      const el = document.getElementById("sess-list");
      el.innerHTML = r.sessions.map(x => `<div class="agent-row"><div class="info">
        <b>${x.current ? '➡️ Diese Sitzung' : 'Sitzung'} ${esc(x.ip || '')}</b>
        <small>${esc((x.user_agent || '').slice(0, 60))} · zuletzt ${x.last_seen ? x.last_seen.replace('T', ' ').slice(0, 16) : '?'}</small></div>
        ${x.current ? '' : `<button class="btn ghost sm" onclick="revokeSession('${x.id}')">abmelden</button>`}</div>`).join("");
    } catch (_) {}
  }
  loadSessions();
  document.getElementById("sess-others").onclick = async () => {
    if (!confirm("Alle anderen Sitzungen abmelden?")) return;
    await api.post("/api/auth/sessions/revoke-others"); loadSessions();
  };
  // Zugangsdaten speichern (nur ausgefüllte Felder)
  document.getElementById("sec-save").onclick = async () => {
    const payload = {};
    document.querySelectorAll("[data-secret]").forEach(inp => {
      if (inp.value.trim() !== "") payload[inp.dataset.secret] = inp.value.trim();
    });
    if (Object.keys(payload).length === 0) { document.getElementById("sec-status").textContent = "nichts geändert"; return; }
    await api.post("/api/secrets", payload);
    document.getElementById("sec-status").textContent = "✓ gespeichert";
    setTimeout(renderSettings, 600);
  };
  // Zeitplan: Fenster ein-/ausblenden + Jetzt prüfen
  document.getElementById("s-sched").onchange = e => {
    document.getElementById("s-window").style.display = e.target.value === "window" ? "" : "none";
  };
  document.getElementById("s-runnow").onclick = async () => {
    const info = document.getElementById("run-info");
    info.textContent = "läuft …";
    const r = await api.post("/api/run-now");
    info.textContent = `✓ ${r.ran} Schritt(e) ausgeführt`;
  };
  document.getElementById("s-save").onclick = async () => {
    await api.put("/api/settings", {
      autonomy_level: document.getElementById("s-autonomy").value,
      auto_run: toggles["s-run"], require_approval_hire: toggles["s-hire"], require_approval_fire: toggles["s-fire"],
      fire_threshold: parseFloat(document.getElementById("s-thresh").value),
      enable_code_exec: toggles["s-code"],
      thinking_mode: document.getElementById("s-think").value,
      require_verification: toggles["s-verify"], incremental_mode: toggles["s-incr"],
      require_review: toggles["s-review"], risk_approval: toggles["s-risk"], model_routing: toggles["s-route"],
      budget_limit: parseFloat(document.getElementById("s-budget").value || "0"),
      schedule_mode: document.getElementById("s-sched").value,
      tick_seconds: parseFloat(document.getElementById("s-tick").value),
      active_from: parseInt(document.getElementById("s-from").value || "0"),
      active_to: parseInt(document.getElementById("s-to").value || "24"),
      user_email: document.getElementById("s-uemail").value,
      email_notifications: toggles["s-notif"], notify_overdue: toggles["s-novd"],
      notify_questions: toggles["s-noq"], daily_digest: toggles["s-digest"], assistant_email_access: toggles["s-aimail"],
      auto_backup: toggles["s-autobak"], backup_keep: parseInt(document.getElementById("s-bakkeep").value || "7"),
      telegram_token: document.getElementById("s-tgtoken").value, telegram_chat_id: document.getElementById("s-tgchat").value,
      default_chef_provider: document.getElementById("s-cp").value, default_chef_model: document.getElementById("s-cm").value,
      default_worker_provider: document.getElementById("s-wp").value, default_worker_model: document.getElementById("s-wm").value,
      allowed_providers: document.getElementById("s-allowed").value,
    });
    document.getElementById("s-status").textContent = "✓ gespeichert";
  };
}

async function loadOllama() {
  const el = document.getElementById("ol-list");
  if (!el) return;
  const st = await api.get("/api/ollama/status");
  const urlIn = document.getElementById("ol-url");
  if (urlIn && document.activeElement !== urlIn) urlIn.value = st.base_url || "";
  const conn = document.getElementById("ol-conn");
  if (conn) conn.innerHTML = st.reachable
    ? `<span style="color:var(--green)">✓ verbunden (${st.models.length} Modelle)</span>`
    : `<span style="color:var(--yellow)">✕ nicht erreichbar</span>`;
  if (!st.reachable) { el.innerHTML = `<div class="muted">Ollama unter <code>${esc(st.base_url || '')}</code> nicht erreichbar. URL prüfen – oder Host-Ollama auf 0.0.0.0 lauschen lassen.</div>`; return; }
  if (!st.models.length) { el.innerHTML = `<div class="muted">Keine lokalen Modelle. Oben eines ziehen.</div>`; return; }
  el.innerHTML = st.models.map(m => `<div class="agent-row" style="padding:9px 11px">
      <i data-lucide="box" style="width:18px"></i>
      <div class="info"><b style="font-size:13px">${esc(m.name)}</b><small>${(m.size / 1e9).toFixed(2)} GB</small></div>
      <span class="pill ${m.loaded ? "employed" : "resigned"}">${m.loaded ? "im RAM" : "entladen"}</span>
      ${m.loaded
        ? `<button class="btn ghost sm" onclick="olAct('unload','${esc(m.name)}')"><i data-lucide="power"></i> entladen</button>`
        : `<button class="btn sm" onclick="olAct('load','${esc(m.name)}')"><i data-lucide="play"></i> laden</button>`}
      <button class="btn red sm" onclick="olAct('delete','${esc(m.name)}')"><i data-lucide="trash-2"></i></button>
    </div>`).join("");
  icons();
}
window.olAct = async (action, name) => {
  await api.post("/api/ollama/" + action, { name });
  loadOllama();
};

// ---------- Helpers ----------
function setupCollapse() {
  document.querySelectorAll(".panel-head").forEach(h => h.onclick = () => h.parentElement.classList.toggle("collapsed"));
}

async function refreshBadges() {
  try {
    const s = await api.get("/api/state");
    const bi = document.getElementById("badge-inbox");
    const ba = document.getElementById("badge-approvals");
    bi.textContent = s.open_questions; bi.classList.toggle("hidden", !s.open_questions);
    ba.textContent = s.pending_approvals; ba.classList.toggle("hidden", !s.pending_approvals);
    const run = await api.get("/api/settings");
    let label = "pausiert", active = false;
    if (run.auto_run) {
      if (run.schedule_mode === "manual") { label = "manuell"; }
      else if (run.schedule_mode === "window") { label = `Zeitfenster ${run.active_from}–${run.active_to} Uhr`; active = true; }
      else { label = "läuft"; active = true; }
    }
    document.getElementById("run-dot").style.background = active ? "var(--green)" : "var(--text-dim)";
    document.getElementById("run-label").textContent = label;
  } catch (e) { /* still */ }
}

// ---------- Auth / Mehrbenutzer ----------
let CURRENT_USER = null;
let pollTimer = null;

async function checkAuth() {
  const r = await fetch("/api/auth/me");
  return r.status === 200 ? r.json() : null;
}

async function renderAuthScreen() {
  const st = await api.get("/api/auth/status");
  const setup = st.needs_setup;
  document.querySelector(".app").innerHTML = `
    <div style="grid-column:1/-1;display:grid;place-items:center;min-height:100vh">
      <div class="card" style="width:360px;max-width:92vw">
        <div class="brand" style="justify-content:center"><div class="logo"><i data-lucide="bot"></i></div>
          <div><b>Foundry-Hub</b><small>${setup ? "Owner-Konto einrichten" : "Anmelden"}</small></div></div>
        <label>Benutzername</label><input id="au-user" autocomplete="username"/>
        <label>Passwort</label><input id="au-pass" type="password" autocomplete="current-password"
          onkeydown="if(event.key==='Enter')doAuth(${setup})"/>
        <button class="btn" style="width:100%;justify-content:center" onclick="doAuth(${setup})">
          <i data-lucide="${setup ? 'user-plus' : 'log-in'}"></i> ${setup ? "Konto erstellen & starten" : "Anmelden"}</button>
        <div class="tag" id="au-err" style="color:var(--red);margin-top:10px;display:none"></div>
        ${setup ? `<div class="tag" style="margin-top:10px">Dies wird das Owner-Konto. Weitere Nutzer legst du später unter „Nutzer & Teilen" an.</div>` : ""}
      </div>
    </div>`;
  icons();
}
window.doAuth = async (setup) => {
  const username = document.getElementById("au-user").value.trim();
  const password = document.getElementById("au-pass").value;
  const codeEl = document.getElementById("au-code");
  const code = codeEl ? codeEl.value.trim() : undefined;
  const err = document.getElementById("au-err");
  const r = await fetch(setup ? "/api/auth/setup" : "/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, code }) });
  if (r.status === 200) { location.reload(); return; }
  const d = await r.json().catch(() => ({}));
  if (d.detail === "2fa") {
    err.style.display = "none";
    if (!document.getElementById("au-code")) {
      const inp = document.createElement("input");
      inp.id = "au-code"; inp.placeholder = "2FA-Code (6-stellig)"; inp.autocomplete = "one-time-code";
      inp.onkeydown = (e) => { if (e.key === "Enter") doAuth(setup); };
      document.getElementById("au-pass").after(inp);
      inp.focus();
    } else { err.style.display = "block"; err.textContent = "Code falsch"; }
    return;
  }
  err.style.display = "block"; err.textContent = d.detail || d.error || "Fehlgeschlagen";
};

function setupHeader(me) {
  document.getElementById("user-label").textContent = me.username + (me.is_owner ? " (Owner)" : "");
  document.getElementById("user-label").classList.remove("hidden");
  const lo = document.getElementById("logout-btn"); lo.classList.remove("hidden");
  lo.onclick = async () => { await api.post("/api/auth/logout"); location.reload(); };
  const sw = document.getElementById("tenant-switch");
  if (me.tenants.length > 1) {
    sw.classList.remove("hidden");
    sw.innerHTML = me.tenants.map(t => `<option value="${t.tenant_id}" ${t.tenant_id === me.active_tenant ? "selected" : ""}>${t.own ? "Meine Firma" : esc(t.name)}</option>`).join("");
    sw.onchange = async () => { await api.post("/api/auth/switch", { tenant_id: Number(sw.value) }); location.reload(); };
  }
  document.getElementById("nav-users").classList.toggle("hidden", !me.is_owner);
}

async function init() {
  const me = await checkAuth();
  if (!me) return renderAuthScreen();
  CURRENT_USER = me;
  setupHeader(me);
  render();
  refreshBadges();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    refreshBadges();
    if (currentView === "inbox") loadThread();
    else if (currentView === "workshop") loadWorkshop();
    else if (["dashboard", "activity", "approvals", "tasks", "org"].includes(currentView)) render();
  }, 5000);
}

// ---------- Nutzer & Teilen (Owner) ----------
async function renderUsers() {
  const users = await api.get("/api/users");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px"><h3><i data-lucide="user-plus"></i> Neuen Nutzer anlegen</h3>
      <input id="nu-name" placeholder="Benutzername"/>
      <input id="nu-pass" type="password" placeholder="Passwort (min. 6 Zeichen)"/>
      <button class="btn" id="nu-add"><i data-lucide="plus"></i> Nutzer anlegen</button>
      <span class="muted" id="nu-status" style="margin-left:8px"></span>
      <div class="tag" style="margin-top:8px">Jeder neue Nutzer bekommt eine eigene, getrennte Firma.</div>
    </div>
    <div class="card"><h3><i data-lucide="users"></i> Nutzer</h3>
      ${users.map(u => `<div class="agent-row">
        <div class="avatar role-${u.is_owner ? 'ceo' : 'planner'}">${initials(u.username)}</div>
        <div class="info"><b>${esc(u.username)}</b><small>${u.is_owner ? "Owner" : "Nutzer"}</small></div>
        ${u.is_owner ? "" : (u.has_access_to_my_firm
          ? `<span class="pill employed">Zugriff auf deine Firma</span><button class="btn ghost sm" onclick="unshare(${u.id})">entziehen</button>`
          : `<button class="btn ghost sm" onclick="shareWith('${esc(u.username)}')"><i data-lucide="share-2"></i> meine Firma teilen</button>`)}
        ${u.is_owner ? "" : `<button class="btn ghost sm" onclick="resetPw(${u.id}, '${esc(u.username)}')"><i data-lucide="key-round"></i> Passwort</button>`}
      </div>`).join("")}
    </div>`;
  icons();
  document.getElementById("nu-add").onclick = async () => {
    const r = await fetch("/api/users", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.getElementById("nu-name").value.trim(), password: document.getElementById("nu-pass").value }) });
    const d = await r.json().catch(() => ({}));
    document.getElementById("nu-status").textContent = r.status === 200 ? "✓ angelegt" : ("✕ " + (d.detail || "Fehler"));
    if (r.status === 200) renderUsers();
  };
}
window.shareWith = async (username) => { await api.post("/api/access", { username }); renderUsers(); };
window.unshare = async (uid) => { await fetch("/api/access/" + uid, { method: "DELETE" }); renderUsers(); };
window.delRecurring = async (id) => { await fetch("/api/recurring/" + id, { method: "DELETE" }); renderSettings(); };
window.revokeSession = async (id) => { await fetch("/api/auth/sessions/" + id, { method: "DELETE" }); renderSettings(); };
window.resetPw = async (uid, name) => {
  const pw = prompt("Neues Passwort für " + name + " (min. 6 Zeichen):");
  if (!pw) return;
  const r = await fetch(`/api/users/${uid}/reset-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ new_password: pw }) });
  alert(r.status === 200 ? "Passwort gesetzt." : "Fehler.");
};

init();
