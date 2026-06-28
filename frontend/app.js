// AI-Hub Frontend – Vanilla JS, spricht mit der REST-API.
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
const TITLES = { dashboard: "Dashboard", inbox: "Inbox", projects: "Projekte", progress: "Fortschritt", org: "Team / Organisation", tasks: "Aufgaben", workshop: "Werkstatt", cookbook: "Cookbook / Regelwerk", skills: "Skills & MCP", approvals: "Freigaben", activity: "Aktivität", settings: "Einstellungen" };
let wsProject = null;
let progProject = "";

function icons() { window.lucide && lucide.createIcons(); }
function esc(s) { return (s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function initials(n) { return (n || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase(); }

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

// ---------- Theme (mit Speicherung) ----------
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  const tog = document.getElementById("theme-toggle");
  tog.innerHTML = t === "dark"
    ? '<i data-lucide="moon"></i><span>Dunkel</span>'
    : '<i data-lucide="sun"></i><span>Hell</span>';
  icons();
  localStorage.setItem("aihub-theme", t);
}
applyTheme(localStorage.getItem("aihub-theme") || "dark");
document.getElementById("theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

// ---------- Render-Dispatcher ----------
async function render() {
  if (currentView === "dashboard") return renderDashboard();
  if (currentView === "inbox") return renderInbox();
  if (currentView === "projects") return renderProjects();
  if (currentView === "progress") return renderProgress();
  if (currentView === "org") return renderOrg();
  if (currentView === "tasks") return renderTasks();
  if (currentView === "workshop") return renderWorkshop();
  if (currentView === "cookbook") return renderCookbook();
  if (currentView === "skills") return renderSkills();
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

async function renderDashboard() {
  const d = await api.get("/api/dashboard");
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
        ${d.open_questions.length ? d.open_questions.map(q => `<div class="msg needs-answer" style="cursor:pointer" onclick="goView('inbox')">
          <div class="meta"><b>${esc(q.sender)}</b><span class="spacer" style="flex:1"></span>${new Date(q.created_at).toLocaleString('de-DE')}</div>
          <div class="subject">${esc(q.subject)}</div><div class="body">${esc((q.body||'').slice(0,140))}</div></div>`).join("")
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
        <button class="btn" id="req-send"><i data-lucide="rocket"></i> Auftrag senden</button>
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

  function row(a, depth) {
    const r = a.rating; const p = r ? (r / 5) * 100 : 0;
    return `<div class="agent-row ${depth ? "indent" : ""}" style="margin-left:${depth * 26}px">
      <div class="avatar role-${a.role}">${initials(a.name)}</div>
      <div class="info"><b>${esc(a.name)}</b><small>${esc(a.title)} · ${esc(a.provider)}/${esc(a.model)}</small></div>
      <div class="donut" style="--p:${p}"><span>${r ?? "–"}</span></div>
      <span class="pill ${a.status}">${a.status}</span>
      <button class="btn ghost sm" onclick="openAgent(${a.id})"><i data-lucide="star"></i> bewerten</button>
    </div>` + (byManager[a.id] || []).map(c => row(c, depth + 1)).join("");
  }
  const chef = agentsCache.find(a => a.role === "ceo");
  root.innerHTML = `<div class="card"><h3><i data-lucide="network"></i> Organigramm</h3>${chef ? row(chef, 0) : `<div class="empty">Kein Chef.</div>`}</div>
    <div id="agent-detail"></div>`;
  icons();
}

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
  const groups = { todo: [], in_progress: [], done: [], failed: [] };
  tasks.forEach(t => (groups[t.status] || (groups[t.status] = [])).push(t));
  const labels = { todo: "Offen", in_progress: "In Arbeit", done: "Erledigt", failed: "Fehlgeschlagen" };
  root.innerHTML = Object.keys(labels).map(k => `
    <div class="panel">
      <div class="panel-head"><i data-lucide="circle-dot"></i> <b>${labels[k]}</b> <span class="tag">${(groups[k] || []).length}</span><i data-lucide="chevron-down" class="chev"></i></div>
      <div class="panel-body">${(groups[k] || []).length ? (groups[k]).map(t => `<div class="msg"><div class="subject">#${t.id} ${esc(t.title)}</div><div class="body">${esc(t.description)}</div>${t.result ? `<div class="tag" style="margin-top:6px">Ergebnis</div><div class="body">${esc(t.result)}</div>` : ""}</div>`).join("") : `<div class="muted">keine</div>`}</div>
    </div>`).join("");
  icons(); setupCollapse();
}

// ---------- Werkstatt ----------
async function renderWorkshop() {
  const projects = await api.get("/api/projects");
  if (wsProject === null && projects.length) wsProject = projects[0].id;
  const opts = projects.map(p => `<option value="${p.id}" ${wsProject == p.id ? "selected" : ""}>#${p.id} ${esc(p.title)}</option>`).join("");
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <div class="row"><h3 style="margin:0"><i data-lucide="folder-code"></i> Projekt-Workspace</h3>
        <div class="spacer" style="flex:1"></div>
        <select id="ws-proj" style="width:auto;margin:0">${opts || '<option>kein Projekt</option>'}</select></div>
    </div>
    <div class="grid cols-2">
      <div class="card"><h3><i data-lucide="files"></i> Dateien</h3><div id="ws-files"></div></div>
      <div class="card"><h3><i data-lucide="file-text"></i> Vorschau</h3><pre id="ws-view" style="white-space:pre-wrap;max-height:340px;overflow:auto;margin:0;color:var(--text-dim)">Datei wählen …</pre></div>
    </div>
    <div class="panel" style="margin-top:14px">
      <div class="panel-head"><i data-lucide="terminal"></i> <b>Konsole / Ausführungen</b><i data-lucide="chevron-down" class="chev"></i></div>
      <div class="panel-body" id="ws-console"></div>
    </div>`;
  icons(); setupCollapse();
  document.getElementById("ws-proj").onchange = e => { wsProject = e.target.value; loadWorkshop(); };
  loadWorkshop();
}

async function loadWorkshop() {
  if (wsProject === null) return;
  const data = await api.get("/api/workspace?project_id=" + wsProject);
  const fEl = document.getElementById("ws-files");
  if (!fEl) return;
  fEl.innerHTML = data.files.length ? data.files.map(f =>
    `<div class="agent-row" style="cursor:pointer;padding:8px 11px" onclick="viewFile('${encodeURIComponent(f.path)}')">
      <i data-lucide="file" style="width:16px"></i><div class="info"><b style="font-size:13px">${esc(f.path)}</b></div>
      <span class="tag">${f.size} B</span></div>`).join("") : `<div class="muted">Noch keine Dateien. Entwickler-Agenten legen hier Dateien an.</div>`;
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

// ---------- Projekte ----------
async function renderProjects() {
  const [projects, agents] = await Promise.all([api.get("/api/projects"), api.get("/api/state")]);
  const teamCount = pid => agents.agents.filter(a => a.project_id === pid && a.status === "employed").length;
  root.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <h3><i data-lucide="folder-plus"></i> Neues Projekt</h3>
      <input id="np-title" placeholder="Projekttitel"/>
      <textarea id="np-desc" placeholder="Ziel, Umfang, Frist …"></textarea>
      <button class="btn" id="np-send"><i data-lucide="rocket"></i> Projekt starten</button>
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
  const ic = { hire: "user-plus", fire: "user-minus", resign: "door-open", task: "list-checks", rating: "star", message: "mail", error: "alert-triangle", info: "info", milestone: "flag", deadline: "alarm-clock", mcp: "plug", file: "file", exec: "terminal", rule: "book", skill: "zap" };
  root.innerHTML = `<div class="card"><h3><i data-lucide="activity"></i> Aktivitäts-Log</h3>
    ${evs.length ? evs.map(e => `<div class="agent-row"><div class="avatar" style="background:var(--panel-2);color:var(--text-dim)"><i data-lucide="${ic[e.kind] || "circle"}"></i></div>
      <div class="info"><b>${esc(e.text)}</b><small>${e.agent ? esc(e.agent) + " · " : ""}${new Date(e.created_at).toLocaleString("de-DE")}</small></div></div>`).join("") : `<div class="empty">Noch keine Aktivität.</div>`}</div>`;
  icons();
}

// ---------- Settings ----------
async function renderSettings() {
  const s = await api.get("/api/settings");
  const provOpts = (sel) => ["claude", "openai", "ollama"].map(p => `<option ${sel === p ? "selected" : ""} value="${p}">${p}${s.providers_available[p] ? "" : " (kein Key → Mock)"}</option>`).join("");
  const autoOpts = { full: "Voll autonom (keine Rückfragen)", ask_for_hiring: "Nachfragen bei Einstellung/Kündigung", ask_for_everything: "Bei allem Wichtigen nachfragen" };
  const schedOpts = { always: "Dauerbetrieb (immer)", window: "Nur in einem Zeitfenster", manual: "Nur manuell (auf Knopfdruck)" };
  root.innerHTML = `
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
    <div class="card" style="margin-top:16px"><h3><i data-lucide="server"></i> Lokale Modelle (Ollama)</h3>
      <div class="row" style="margin-bottom:10px"><input id="ol-name" placeholder="Modell ziehen, z. B. llama3.1" style="margin:0"/>
        <button class="btn sm" id="ol-pull"><i data-lucide="download"></i> Ziehen</button></div>
      <div id="ol-list"><div class="muted">lade …</div></div>
    </div>`;
  icons();
  loadOllama();
  document.getElementById("ol-pull").onclick = async () => {
    const n = document.getElementById("ol-name").value.trim(); if (!n) return;
    document.getElementById("ol-pull").textContent = "lädt …";
    await api.post("/api/ollama/pull", { name: n }); loadOllama();
  };
  const toggles = {};
  ["s-run", "s-hire", "s-fire", "s-code"].forEach(id => {
    const el = document.getElementById(id);
    toggles[id] = el.querySelector(".switch").classList.contains("on");
    el.onclick = () => { const sw = el.querySelector(".switch"); sw.classList.toggle("on"); toggles[id] = sw.classList.contains("on"); };
  });
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
      schedule_mode: document.getElementById("s-sched").value,
      tick_seconds: parseFloat(document.getElementById("s-tick").value),
      active_from: parseInt(document.getElementById("s-from").value || "0"),
      active_to: parseInt(document.getElementById("s-to").value || "24"),
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
  if (!st.reachable) { el.innerHTML = `<div class="muted">Ollama nicht erreichbar (Container aus?).</div>`; return; }
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

// Initial + Polling
render();
refreshBadges();
setInterval(() => {
  refreshBadges();
  if (currentView === "inbox") loadThread();
  else if (currentView === "workshop") loadWorkshop();
  else if (["dashboard", "activity", "approvals", "tasks", "org"].includes(currentView)) render();
}, 5000);
