// AI-Hub Frontend – Vanilla JS, spricht mit der REST-API.
const api = {
  async get(p) { const r = await fetch(p); return r.json(); },
  async post(p, b) { const r = await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return r.json(); },
  async put(p, b) { const r = await fetch(p, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }); return r.json(); },
};

let currentView = "inbox";
let agentsCache = [];
let chefId = null;
let selectedAgent = null; // null = Chef-Inbox (an Nutzer)

const root = document.getElementById("view-root");
const titleEl = document.getElementById("view-title");
const TITLES = { inbox: "Inbox", projects: "Projekte", org: "Team / Organisation", tasks: "Aufgaben", workshop: "Werkstatt", cookbook: "Cookbook / Regelwerk", skills: "Skills & MCP", approvals: "Freigaben", activity: "Aktivität", settings: "Einstellungen" };
let wsProject = null;

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
  if (currentView === "inbox") return renderInbox();
  if (currentView === "projects") return renderProjects();
  if (currentView === "org") return renderOrg();
  if (currentView === "tasks") return renderTasks();
  if (currentView === "workshop") return renderWorkshop();
  if (currentView === "cookbook") return renderCookbook();
  if (currentView === "skills") return renderSkills();
  if (currentView === "approvals") return renderApprovals();
  if (currentView === "activity") return renderActivity();
  if (currentView === "settings") return renderSettings();
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
      <div class="card"><h3><i data-lucide="server"></i> MCP-Server (Registry)</h3>
        ${mcp.length ? mcp.map(m => `<div class="agent-row">
          <div class="avatar role-planner"><i data-lucide="plug"></i></div>
          <div class="info"><b>${esc(m.name)}</b><small>${esc(m.transport)} · ${esc(m.description)}</small></div>
          <span class="pill ${m.enabled ? 'employed' : 'resigned'}">${m.enabled ? 'aktiv' : 'aus'}</span>
          <button class="btn red sm" onclick="delMcp(${m.id})"><i data-lucide="trash-2"></i></button></div>`).join("") : `<div class="muted">keine</div>`}
        <hr style="border-color:var(--border);margin:12px 0"/>
        <input id="mc-name" placeholder="Name (z. B. github)"/>
        <input id="mc-desc" placeholder="Beschreibung / Zweck"/>
        <div class="row"><select id="mc-transport" style="margin:0"><option value="stdio">stdio</option><option value="http">http</option></select>
          <input id="mc-target" placeholder="Befehl oder URL" style="margin:0"/></div>
        <button class="btn" id="mc-add"><i data-lucide="plus"></i> MCP-Server speichern</button>
        <div class="tag" style="margin-top:8px">Leichtgewichtig: Agenten kennen diese Werkzeuge und können sie anfragen.</div>
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
  const ic = { hire: "user-plus", fire: "user-minus", resign: "door-open", task: "list-checks", rating: "star", message: "mail", error: "alert-triangle", info: "info" };
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
  root.innerHTML = `
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
  document.getElementById("s-save").onclick = async () => {
    await api.put("/api/settings", {
      autonomy_level: document.getElementById("s-autonomy").value,
      auto_run: toggles["s-run"], require_approval_hire: toggles["s-hire"], require_approval_fire: toggles["s-fire"],
      fire_threshold: parseFloat(document.getElementById("s-thresh").value),
      enable_code_exec: toggles["s-code"],
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
    document.getElementById("run-dot").style.background = run.auto_run ? "var(--green)" : "var(--text-dim)";
    document.getElementById("run-label").textContent = run.auto_run ? "läuft" : "pausiert";
  } catch (e) { /* still */ }
}

// Initial + Polling
render();
refreshBadges();
setInterval(() => {
  refreshBadges();
  if (currentView === "inbox") loadThread();
  else if (currentView === "workshop") loadWorkshop();
  else if (["activity", "approvals", "tasks", "org"].includes(currentView)) render();
}, 5000);
