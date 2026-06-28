"""FastAPI-App: REST-API, Hintergrund-Orchestrator und Auslieferung der Web-UI."""
import asyncio
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant as assistant_mod
from . import email_util
from . import mcp_client
from . import ollama_admin
from . import orchestrator as orch
from . import providers
from . import secrets as secrets_mod
from . import workspace
from .config import config
from .database import Base, SessionLocal, engine
from .models import (
    Agent,
    Decision,
    Event,
    McpServer,
    Message,
    Milestone,
    PendingApproval,
    Project,
    Rating,
    Rule,
    Settings,
    Skill,
    Task,
)
from .roles import ROLES, role_title
from .seed import ensure_seed

app = FastAPI(title="AI-Hub", version="1.0")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


# --------------------------------------------------------------------------- #
# Lebenszyklus
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed(db)
    finally:
        db.close()
    secrets_mod.apply_to_environ()  # GUI-Zugangsdaten für Subprozesse verfügbar machen
    asyncio.create_task(orchestrator_loop())
    asyncio.create_task(_startup_ollama())
    asyncio.create_task(_startup_mcp())


async def _startup_mcp():
    """Verbindet sich beim Start best-effort mit allen aktiven MCP-Servern und cached deren Tools."""
    db = SessionLocal()
    try:
        servers = [(m.id, m.transport, m.command, m.url, m.name)
                   for m in db.query(McpServer).filter(McpServer.enabled == True).all()]  # noqa: E712
    finally:
        db.close()
    for mid, transport, command, url, name in servers:
        try:
            tools = await mcp_client.list_tools(transport, command=command, url=url)
            status, last_error, tj = "connected", "", json.dumps(tools)
        except Exception as e:  # noqa: BLE001
            status, last_error, tj = "error", str(e), "[]"
        db = SessionLocal()
        try:
            m = db.get(McpServer, mid)
            if m:
                m.tools_json, m.status, m.last_error = tj, status, last_error
                db.commit()
        finally:
            db.close()
        print(f"MCP '{name}': {status}{(' – ' + last_error) if last_error else ''}")


async def _startup_ollama():
    """Zieht beim Start ein lokales Modell – nur falls noch keines vorhanden ist."""
    try:
        res = await ollama_admin.ensure_default_model()
        print("Ollama Auto-Modell:", res)
    except Exception as e:  # noqa: BLE001
        print("Ollama-Start übersprungen:", e)


async def orchestrator_loop():
    """Lässt die Agenten arbeiten – Takt und Zeitplan kommen aus den Einstellungen."""
    while True:
        sleep_for = config.TICK_INTERVAL_SECONDS
        try:
            db = SessionLocal()
            try:
                await orch.tick(db)
                s = orch.get_settings(db)
                sleep_for = max(1.0, s.tick_seconds or config.TICK_INTERVAL_SECONDS)
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            print("Orchestrator-Fehler:", e)
        await asyncio.sleep(sleep_for)


# --------------------------------------------------------------------------- #
# Serialisierung
# --------------------------------------------------------------------------- #
def agent_dict(db, a: Agent):
    return {
        "id": a.id, "name": a.name, "role": a.role, "title": role_title(a.role),
        "provider": a.provider, "model": a.model, "status": a.status,
        "manager_id": a.manager_id, "project_id": a.project_id,
        "stuck": a.stuck,
        "rating": orch.avg_rating(db, a.id),
        "rating_count": db.query(Rating).filter(Rating.ratee_agent_id == a.id).count(),
    }


def msg_dict(db, m: Message):
    sender = "Nutzer"
    if m.sender_kind == "agent" and m.sender_agent_id:
        sa = db.get(Agent, m.sender_agent_id)
        sender = sa.name if sa else f"#{m.sender_agent_id}"
    elif m.sender_kind == "system":
        sender = "System"
    recipient = "Nutzer"
    if m.recipient_kind == "agent" and m.recipient_agent_id:
        ra = db.get(Agent, m.recipient_agent_id)
        recipient = ra.name if ra else f"#{m.recipient_agent_id}"
    return {
        "id": m.id, "sender": sender, "recipient": recipient,
        "sender_kind": m.sender_kind, "sender_agent_id": m.sender_agent_id,
        "recipient_kind": m.recipient_kind, "recipient_agent_id": m.recipient_agent_id,
        "subject": m.subject, "body": m.body, "requires_answer": m.requires_answer,
        "answered": m.answered, "created_at": m.created_at.isoformat(),
    }


# --------------------------------------------------------------------------- #
# Request-Modelle
# --------------------------------------------------------------------------- #
class NewRequest(BaseModel):
    title: str
    description: str = ""


class QuickTask(BaseModel):
    title: str
    description: str = ""


class RuleIn(BaseModel):
    title: str | None = None
    content: str | None = None
    scope: str | None = None
    role: str | None = None
    project_id: int | None = None
    active: bool | None = None


class SkillIn(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    command: str = ""
    enabled: bool | None = None


class McpIn(BaseModel):
    name: str
    description: str = ""
    transport: str = "stdio"
    command: str = ""
    url: str = ""
    enabled: bool | None = None


class UserMessage(BaseModel):
    to_agent_id: int | None = None  # None = Chef
    subject: str = ""
    body: str


class SettingsUpdate(BaseModel):
    autonomy_level: str | None = None
    allowed_providers: str | None = None
    default_chef_provider: str | None = None
    default_chef_model: str | None = None
    default_worker_provider: str | None = None
    default_worker_model: str | None = None
    auto_run: bool | None = None
    require_approval_hire: bool | None = None
    require_approval_fire: bool | None = None
    fire_threshold: float | None = None
    enable_code_exec: bool | None = None
    schedule_mode: str | None = None
    active_from: int | None = None
    active_to: int | None = None
    tick_seconds: float | None = None
    user_email: str | None = None
    email_notifications: bool | None = None
    notify_overdue: bool | None = None
    notify_questions: bool | None = None
    assistant_email_access: bool | None = None


class UserRating(BaseModel):
    agent_id: int
    score: int
    feedback: str = ""


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "providers": providers.available_providers()}


@app.get("/api/secrets")
def get_secrets():
    """Status aller Zugangsdaten (nie die Werte selbst)."""
    return secrets_mod.status()


@app.post("/api/secrets")
def set_secrets(values: dict):
    """Setzt Zugangsdaten aus der GUI. Leerer Wert = unverändert lassen.
    Wert '__CLEAR__' = löschen (wieder auf .env/Default zurückfallen)."""
    for key, val in values.items():
        if key not in secrets_mod.KEYS:
            continue
        if val == "__CLEAR__":
            secrets_mod.set_value(key, "")
        elif val not in (None, ""):
            secrets_mod.set_value(key, str(val))
    secrets_mod.apply_to_environ()
    return {"ok": True, "status": secrets_mod.status()}


@app.post("/api/run-now")
async def run_now(steps: int = 6):
    """Lässt die KI sofort prüfen/arbeiten – ignoriert den Zeitplan (manueller Anstoß)."""
    done = 0
    for _ in range(max(1, min(steps, 20))):
        db = SessionLocal()
        try:
            result = await orch.tick(db, force=True)
        finally:
            db.close()
        if result is None:
            break
        done += 1
    return {"ran": done}


@app.get("/api/dashboard")
def dashboard():
    """Aggregierte Übersicht für die Startseite."""
    from datetime import datetime
    db = SessionLocal()
    try:
        now_ = datetime.utcnow()
        projects = db.query(Project).filter(Project.status == "active").order_by(Project.id.desc()).all()
        agents = db.query(Agent).filter(Agent.status == "employed").all()
        all_tasks = db.query(Task).all()
        all_ms = db.query(Milestone).all()

        def proj_card(p):
            ptasks = [t for t in all_tasks if t.project_id == p.id]
            pms = [m for m in all_ms if m.project_id == p.id]
            td = sum(1 for t in ptasks if t.status == "done")
            mdone = sum(1 for m in pms if m.status == "done")
            over = sum(1 for m in pms if m.due_date and m.status != "done" and m.due_date < now_)
            return {"id": p.id, "title": p.title, "status": p.status,
                    "team": sum(1 for a in agents if a.project_id == p.id),
                    "tasks_done": td, "tasks_total": len(ptasks),
                    "task_percent": round(100 * td / len(ptasks)) if ptasks else 0,
                    "milestones_done": mdone, "milestones_total": len(pms),
                    "overdue": over}

        overdue_ms = []
        for m in all_ms:
            if m.due_date and m.status != "done" and m.due_date < now_:
                days_over = round((now_ - m.due_date).total_seconds() / 86400, 1)
                overdue_ms.append({"id": m.id, "title": m.title, "project_id": m.project_id,
                                   "due_date": m.due_date.isoformat(), "days_over": days_over})

        questions = (db.query(Message)
                     .filter(Message.recipient_kind == "user",
                             Message.requires_answer == True,  # noqa: E712
                             Message.answered == False)  # noqa: E712
                     .order_by(Message.id.desc()).limit(10).all())
        approvals = (db.query(PendingApproval)
                     .filter(PendingApproval.status == "pending")
                     .order_by(PendingApproval.id).all())
        events = db.query(Event).order_by(Event.id.desc()).limit(8).all()

        td_all = sum(1 for t in all_tasks if t.status == "done")
        return {
            "stats": {
                "projects": len(projects),
                "agents": len(agents),
                "open_questions": len(questions),
                "pending_approvals": len(approvals),
                "overdue": len(overdue_ms),
                "tasks_done": td_all, "tasks_total": len(all_tasks),
            },
            "projects": [proj_card(p) for p in projects],
            "open_questions": [{"id": q.id, "subject": q.subject, "body": q.body,
                                "sender": (db.get(Agent, q.sender_agent_id).name
                                           if q.sender_agent_id else "System"),
                                "sender_agent_id": q.sender_agent_id,
                                "created_at": q.created_at.isoformat()} for q in questions],
            "approvals": [{"id": a.id, "summary": a.summary} for a in approvals],
            "overdue_milestones": overdue_ms,
            "recent_activity": [{"kind": e.kind, "text": e.text,
                                 "created_at": e.created_at.isoformat()} for e in events],
        }
    finally:
        db.close()


@app.get("/api/state")
def state():
    db = SessionLocal()
    try:
        chef = db.query(Agent).filter(Agent.role == "ceo").first()
        agents = db.query(Agent).order_by(Agent.id).all()
        return {
            "chef_id": chef.id if chef else None,
            "agents": [agent_dict(db, a) for a in agents],
            "open_questions": db.query(Message).filter(
                Message.recipient_kind == "user",
                Message.requires_answer == True,  # noqa: E712
                Message.answered == False).count(),  # noqa: E712
            "pending_approvals": db.query(PendingApproval).filter(
                PendingApproval.status == "pending").count(),
        }
    finally:
        db.close()


@app.post("/api/requests")
def create_request(req: NewRequest):
    """Neue Anfrage des Nutzers an den Chef."""
    db = SessionLocal()
    try:
        chef = ensure_seed(db)
        project = Project(title=req.title, description=req.description)
        db.add(project)
        db.flush()
        orch.send_message(
            db, sender_kind="user", sender_agent_id=None,
            recipient_kind="agent", recipient_agent_id=chef.id,
            subject="Neue Anfrage: " + req.title,
            body=req.description or req.title, project_id=project.id,
        )
        db.commit()
        return {"project_id": project.id, "chef_id": chef.id}
    finally:
        db.close()


@app.post("/api/messages")
def post_message(m: UserMessage):
    """Nutzer schreibt an einen beliebigen Agenten (Standard: Chef)."""
    db = SessionLocal()
    try:
        if m.to_agent_id is None:
            chef = db.query(Agent).filter(Agent.role == "ceo").first()
            target_id = chef.id if chef else None
        else:
            target_id = m.to_agent_id
        if not target_id:
            raise HTTPException(404, "Kein Empfänger")
        # Eine Nachricht des Nutzers weckt einen festsitzenden Agenten wieder
        ta = db.get(Agent, target_id)
        if ta and ta.stuck:
            ta.stuck = False
            orch.log(db, "info", f"{ta.name} durch Nutzer fortgesetzt", agent_id=ta.id)
        # offene Rückfragen an diesen Agenten als beantwortet markieren
        for q in db.query(Message).filter(
                Message.sender_agent_id == target_id,
                Message.requires_answer == True,  # noqa: E712
                Message.answered == False).all():  # noqa: E712
            q.answered = True
        orch.send_message(db, sender_kind="user", sender_agent_id=None,
                          recipient_kind="agent", recipient_agent_id=target_id,
                          subject=m.subject or "Antwort", body=m.body)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/messages")
def list_messages(agent_id: int | None = None, inbox: str | None = None):
    """inbox=user -> Nachrichten an den Nutzer. agent_id -> Thread mit einem Agenten."""
    db = SessionLocal()
    try:
        q = db.query(Message)
        if inbox == "user":
            q = q.filter(Message.recipient_kind == "user")
        elif agent_id is not None:
            q = q.filter(
                ((Message.sender_agent_id == agent_id) & (Message.sender_kind == "agent")) |
                ((Message.recipient_agent_id == agent_id) & (Message.recipient_kind == "agent"))
            )
        msgs = q.order_by(Message.created_at.desc()).limit(200).all()
        return [msg_dict(db, m) for m in reversed(msgs)]
    finally:
        db.close()


@app.post("/api/agents/{agent_id}/resume")
def resume_agent(agent_id: int):
    """Setzt einen automatisch gestoppten (festsitzenden) Agenten fort."""
    db = SessionLocal()
    try:
        a = db.get(Agent, agent_id)
        if not a:
            raise HTTPException(404, "Agent nicht gefunden")
        a.stuck = False
        orch.log(db, "info", f"{a.name} fortgesetzt", agent_id=a.id)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int):
    db = SessionLocal()
    try:
        a = db.get(Agent, agent_id)
        if not a:
            raise HTTPException(404, "Agent nicht gefunden")
        data = agent_dict(db, a)
        data["reports"] = [agent_dict(db, r) for r in
                           db.query(Agent).filter(Agent.manager_id == a.id).all()]
        data["tasks"] = [{"id": t.id, "title": t.title, "status": t.status,
                          "result": t.result} for t in
                         db.query(Task).filter(Task.assigned_agent_id == a.id).all()]
        data["ratings"] = [{"score": r.score, "feedback": r.feedback,
                            "rater": "Nutzer" if r.rater_kind == "user" else f"#{r.rater_agent_id}"}
                           for r in db.query(Rating).filter(Rating.ratee_agent_id == a.id).all()]
        return data
    finally:
        db.close()


@app.get("/api/tasks")
def list_tasks():
    db = SessionLocal()
    try:
        tasks = db.query(Task).order_by(Task.id.desc()).limit(200).all()
        return [{"id": t.id, "title": t.title, "description": t.description,
                 "status": t.status, "assigned_agent_id": t.assigned_agent_id,
                 "milestone_id": t.milestone_id, "result": t.result} for t in tasks]
    finally:
        db.close()


@app.post("/api/ratings")
def rate(r: UserRating):
    db = SessionLocal()
    try:
        db.add(Rating(ratee_agent_id=r.agent_id, rater_kind="user",
                      score=max(1, min(5, r.score)), feedback=r.feedback))
        orch.log(db, "rating", f"Nutzer bewertet #{r.agent_id} mit {r.score}/5", agent_id=r.agent_id)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/approvals")
def list_approvals():
    db = SessionLocal()
    try:
        items = db.query(PendingApproval).filter(
            PendingApproval.status == "pending").order_by(PendingApproval.id).all()
        return [{"id": a.id, "summary": a.summary,
                 "action": json.loads(a.action_json)} for a in items]
    finally:
        db.close()


@app.post("/api/approvals/{approval_id}/{decision}")
def decide_approval(approval_id: int, decision: str):
    db = SessionLocal()
    try:
        ap = db.get(PendingApproval, approval_id)
        if not ap or ap.status != "pending":
            raise HTTPException(404, "Freigabe nicht gefunden")
        action = json.loads(ap.action_json)
        if decision == "approve":
            ap.status = "approved"
            if action.get("type") == "hire":
                orch._create_agent(db, action["role"], action["name"],
                                   action["provider"], action["model"],
                                   action.get("manager_id"), action.get("project_id"))
            elif action.get("type") == "fire":
                target = db.get(Agent, action["agent_id"])
                if target:
                    target.status = "fired"
                    orch.log(db, "fire", f"{target.name} gekündigt (freigegeben)", agent_id=target.id)
        else:
            ap.status = "rejected"
        db.commit()
        return {"ok": True, "status": ap.status}
    finally:
        db.close()


@app.get("/api/events")
def list_events():
    db = SessionLocal()
    try:
        evs = db.query(Event).order_by(Event.id.desc()).limit(100).all()
        out = []
        for e in evs:
            name = ""
            if e.agent_id:
                a = db.get(Agent, e.agent_id)
                name = a.name if a else f"#{e.agent_id}"
            out.append({"id": e.id, "kind": e.kind, "agent": name,
                        "text": e.text, "created_at": e.created_at.isoformat()})
        return out
    finally:
        db.close()


@app.get("/api/settings")
def get_settings():
    db = SessionLocal()
    try:
        s = orch.get_settings(db)
        return {
            "autonomy_level": s.autonomy_level,
            "allowed_providers": s.allowed_providers,
            "default_chef_provider": s.default_chef_provider,
            "default_chef_model": s.default_chef_model,
            "default_worker_provider": s.default_worker_provider,
            "default_worker_model": s.default_worker_model,
            "auto_run": s.auto_run,
            "require_approval_hire": s.require_approval_hire,
            "require_approval_fire": s.require_approval_fire,
            "fire_threshold": s.fire_threshold,
            "enable_code_exec": s.enable_code_exec,
            "schedule_mode": s.schedule_mode,
            "active_from": s.active_from,
            "active_to": s.active_to,
            "tick_seconds": s.tick_seconds,
            "user_email": s.user_email,
            "email_notifications": s.email_notifications,
            "notify_overdue": s.notify_overdue,
            "notify_questions": s.notify_questions,
            "assistant_email_access": s.assistant_email_access,
            "email_status": {"smtp": email_util.smtp_configured(),
                             "imap": email_util.imap_configured()},
            "providers_available": providers.available_providers(),
            "roles": {k: role_title(k) for k in ROLES},
        }
    finally:
        db.close()


@app.put("/api/settings")
def update_settings(upd: SettingsUpdate):
    db = SessionLocal()
    try:
        s = orch.get_settings(db)
        for field, value in upd.model_dump(exclude_none=True).items():
            setattr(s, field, value)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Code-Werkstatt
# --------------------------------------------------------------------------- #
@app.get("/api/projects")
def list_projects():
    db = SessionLocal()
    try:
        return [{"id": p.id, "title": p.title, "status": p.status}
                for p in db.query(Project).order_by(Project.id.desc()).all()]
    finally:
        db.close()


class MilestoneIn(BaseModel):
    project_id: int | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: str | None = None   # 'YYYY-MM-DD' oder leer
    due_days: float | None = None


def _ms_dict(m: Milestone):
    from datetime import datetime
    overdue = bool(m.due_date and m.status != "done" and m.due_date < datetime.utcnow())
    due_in_days = None
    if m.due_date:
        due_in_days = round((m.due_date - datetime.utcnow()).total_seconds() / 86400, 1)
    return {"id": m.id, "project_id": m.project_id, "title": m.title,
            "description": m.description, "status": m.status, "order_index": m.order_index,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "overdue": overdue, "due_in_days": due_in_days,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "completed_at": m.completed_at.isoformat() if m.completed_at else None}


@app.get("/api/progress")
def progress(project_id: int | None = None):
    """Projekt-Fortschritt: Meilensteine, Aufgaben-Statistik, Stand."""
    db = SessionLocal()
    try:
        msq = db.query(Milestone)
        tq = db.query(Task)
        if project_id is not None:
            msq = msq.filter(Milestone.project_id == project_id)
            tq = tq.filter(Task.project_id == project_id)
        milestones = msq.order_by(Milestone.order_index, Milestone.id).all()
        tasks = tq.all()
        t_total = len(tasks)
        t_done = sum(1 for t in tasks if t.status == "done")
        m_total = len(milestones)
        m_done = sum(1 for m in milestones if m.status == "done")
        # Aufgaben-Fortschritt je Meilenstein
        ms_list = []
        for m in milestones:
            mtasks = [t for t in tasks if t.milestone_id == m.id]
            md = sum(1 for t in mtasks if t.status == "done")
            d = _ms_dict(m)
            d["tasks_total"] = len(mtasks)
            d["tasks_done"] = md
            d["percent"] = round(100 * md / len(mtasks)) if mtasks else (100 if m.status == "done" else 0)
            ms_list.append(d)
        unassigned = [t for t in tasks if t.milestone_id is None]
        return {
            "project_id": project_id,
            "milestones": ms_list,
            "unassigned_tasks": len(unassigned),
            "unassigned_done": sum(1 for t in unassigned if t.status == "done"),
            "tasks_total": t_total, "tasks_done": t_done,
            "tasks_in_progress": sum(1 for t in tasks if t.status == "in_progress"),
            "milestones_total": m_total, "milestones_done": m_done,
            "task_percent": round(100 * t_done / t_total) if t_total else 0,
            "milestone_percent": round(100 * m_done / m_total) if m_total else 0,
        }
    finally:
        db.close()


@app.get("/api/milestones")
def list_milestones(project_id: int | None = None):
    db = SessionLocal()
    try:
        q = db.query(Milestone)
        if project_id is not None:
            q = q.filter(Milestone.project_id == project_id)
        return [_ms_dict(m) for m in q.order_by(Milestone.order_index, Milestone.id).all()]
    finally:
        db.close()


@app.post("/api/milestones")
def create_milestone(m: MilestoneIn):
    db = SessionLocal()
    try:
        n = db.query(Milestone).filter(Milestone.project_id == m.project_id).count()
        ms = Milestone(project_id=m.project_id, title=m.title or "Meilenstein",
                       description=m.description or "", status=m.status or "planned",
                       order_index=n, due_date=orch.parse_due(m.due_days, m.due_date))
        db.add(ms)
        db.commit()
        return _ms_dict(ms)
    finally:
        db.close()


@app.put("/api/milestones/{ms_id}")
def update_milestone(ms_id: int, m: MilestoneIn):
    db = SessionLocal()
    try:
        ms = db.get(Milestone, ms_id)
        if not ms:
            raise HTTPException(404, "Meilenstein nicht gefunden")
        if m.status:
            ms.status = m.status
            if m.status == "done" and not ms.completed_at:
                from .models import now as _now
                ms.completed_at = _now()
        if m.title:
            ms.title = m.title
        if m.description is not None:
            ms.description = m.description
        if m.due_date is not None or m.due_days is not None:
            ms.due_date = orch.parse_due(m.due_days, m.due_date)
            ms.overdue_notified = False  # neue Frist -> Verzug ggf. neu melden
        db.commit()
        return _ms_dict(ms)
    finally:
        db.close()


@app.delete("/api/milestones/{ms_id}")
def delete_milestone(ms_id: int):
    db = SessionLocal()
    try:
        ms = db.get(Milestone, ms_id)
        if ms:
            db.delete(ms)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/decisions")
def list_decisions(project_id: int | None = None, agent_id: int | None = None, limit: int = 60):
    """Entscheidungs-Log: warum/was/wie die KI gehandelt hat."""
    db = SessionLocal()
    try:
        q = db.query(Decision)
        if project_id is not None:
            q = q.filter(Decision.project_id == project_id)
        if agent_id is not None:
            q = q.filter(Decision.agent_id == agent_id)
        rows = q.order_by(Decision.id.desc()).limit(min(limit, 200)).all()
        out = []
        for d in rows:
            a = db.get(Agent, d.agent_id) if d.agent_id else None
            out.append({"id": d.id, "agent": a.name if a else "—",
                        "agent_id": d.agent_id, "project_id": d.project_id,
                        "thoughts": d.thoughts, "actions_summary": d.actions_summary,
                        "trigger": d.trigger,
                        "created_at": d.created_at.isoformat() if d.created_at else None})
        return out
    finally:
        db.close()


@app.get("/api/workspace")
def workspace_files(project_id: int | None = None):
    return {"project_id": project_id, "files": workspace.list_files(project_id)}


@app.get("/api/workspace/file")
def workspace_file(path: str, project_id: int | None = None):
    return {"path": path, "content": workspace.read_file(project_id, path)}


@app.get("/api/sandbox/status")
def sandbox_status():
    """Status des isolierten Build-Containers (Werkzeuge)."""
    if not config.SANDBOX_URL:
        return {"enabled": False, "reachable": False,
                "note": "Läuft lokal im App-Container (kein isolierter Build-Container konfiguriert)."}
    try:
        import httpx
        r = httpx.get(f"{config.SANDBOX_URL}/health", timeout=8)
        d = r.json()
        return {"enabled": True, "reachable": True, "tools": d.get("tools", {})}
    except Exception as e:  # noqa: BLE001
        return {"enabled": True, "reachable": False, "error": str(e)}


@app.post("/api/sandbox/reset")
def sandbox_reset(project_id: int | None = None):
    return workspace.reset_workspace(project_id)


@app.get("/api/console")
def console(project_id: int | None = None):
    """Letzte Befehlsausführungen (aus dem Event-Log)."""
    db = SessionLocal()
    try:
        evs = (db.query(Event).filter(Event.kind.in_(["exec", "file"]))
               .order_by(Event.id.desc()).limit(60).all())
        return [{"id": e.id, "kind": e.kind, "text": e.text,
                 "created_at": e.created_at.isoformat()} for e in evs]
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Ollama-Verwaltung (lokale Modelle)
# --------------------------------------------------------------------------- #
class OllamaModel(BaseModel):
    name: str


@app.get("/api/ollama/status")
async def ollama_status():
    return await ollama_admin.status()


@app.post("/api/ollama/pull")
async def ollama_pull(m: OllamaModel):
    return await ollama_admin.pull(m.name)


@app.post("/api/ollama/load")
async def ollama_load(m: OllamaModel):
    return await ollama_admin.load(m.name)


@app.post("/api/ollama/unload")
async def ollama_unload(m: OllamaModel):
    return await ollama_admin.unload(m.name)


@app.post("/api/ollama/delete")
async def ollama_delete(m: OllamaModel):
    return await ollama_admin.delete(m.name)


# --------------------------------------------------------------------------- #
# Projekte & Einzelaufgaben
# --------------------------------------------------------------------------- #
@app.post("/api/projects")
def create_project(req: NewRequest):
    """Legt ein Projekt an und beauftragt den Chef damit."""
    db = SessionLocal()
    try:
        chef = ensure_seed(db)
        project = Project(title=req.title, description=req.description)
        db.add(project)
        db.flush()
        orch.send_message(db, sender_kind="user", sender_agent_id=None,
                          recipient_kind="agent", recipient_agent_id=chef.id,
                          subject="Neues Projekt: " + req.title,
                          body=req.description or req.title, project_id=project.id)
        db.commit()
        return {"project_id": project.id}
    finally:
        db.close()


@app.post("/api/quicktasks")
def create_quicktask(req: QuickTask):
    """Einzelaufgabe (kein Projekt) direkt an die Firma/den Chef."""
    db = SessionLocal()
    try:
        chef = ensure_seed(db)
        orch.send_message(db, sender_kind="user", sender_agent_id=None,
                          recipient_kind="agent", recipient_agent_id=chef.id,
                          subject="Einzelaufgabe: " + req.title,
                          body=(req.description or req.title) +
                          "\n\n(Hinweis: Einzelaufgabe – kein volles Projekt nötig. "
                          "Erledige es selbst oder delegiere es schlank.)",
                          project_id=None)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Cookbook / Regelwerk
# --------------------------------------------------------------------------- #
def _rule_dict(r: Rule):
    return {"id": r.id, "title": r.title, "content": r.content, "scope": r.scope,
            "role": r.role, "project_id": r.project_id, "source": r.source,
            "active": r.active}


@app.get("/api/rules")
def list_rules():
    db = SessionLocal()
    try:
        return [_rule_dict(r) for r in db.query(Rule).order_by(Rule.id.desc()).all()]
    finally:
        db.close()


@app.post("/api/rules")
def create_rule(r: RuleIn):
    db = SessionLocal()
    try:
        rule = Rule(title=r.title or "Regel", content=r.content or "",
                    scope=r.scope or "global", role=r.role,
                    project_id=r.project_id, source="user",
                    active=True if r.active is None else r.active)
        db.add(rule)
        db.commit()
        return _rule_dict(rule)
    finally:
        db.close()


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, r: RuleIn):
    db = SessionLocal()
    try:
        rule = db.get(Rule, rule_id)
        if not rule:
            raise HTTPException(404, "Regel nicht gefunden")
        for f, v in r.model_dump(exclude_none=True).items():
            setattr(rule, f, v)
        db.commit()
        return _rule_dict(rule)
    finally:
        db.close()


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    db = SessionLocal()
    try:
        rule = db.get(Rule, rule_id)
        if rule:
            db.delete(rule)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Skills & MCP-Registry
# --------------------------------------------------------------------------- #
def _skill_dict(s: Skill):
    return {"id": s.id, "name": s.name, "description": s.description,
            "instructions": s.instructions, "command": s.command, "enabled": s.enabled}


@app.get("/api/skills")
def list_skills():
    db = SessionLocal()
    try:
        return [_skill_dict(s) for s in db.query(Skill).order_by(Skill.id).all()]
    finally:
        db.close()


@app.post("/api/skills")
def create_skill(s: SkillIn):
    db = SessionLocal()
    try:
        existing = db.query(Skill).filter(Skill.name == s.name).first()
        if existing:
            for f, v in s.model_dump(exclude_none=True).items():
                setattr(existing, f, v)
            db.commit()
            return _skill_dict(existing)
        skill = Skill(name=s.name, description=s.description, instructions=s.instructions,
                      command=s.command, enabled=True if s.enabled is None else s.enabled)
        db.add(skill)
        db.commit()
        return _skill_dict(skill)
    finally:
        db.close()


@app.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: int):
    db = SessionLocal()
    try:
        s = db.get(Skill, skill_id)
        if s:
            db.delete(s)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


def _mcp_dict(m: McpServer):
    try:
        tools = json.loads(m.tools_json or "[]")
    except Exception:  # noqa: BLE001
        tools = []
    return {"id": m.id, "name": m.name, "description": m.description,
            "transport": m.transport, "command": m.command, "url": m.url,
            "enabled": m.enabled, "status": m.status, "last_error": m.last_error,
            "tools": [{"name": t.get("name"), "description": t.get("description", "")}
                      for t in tools]}


@app.get("/api/mcp")
def list_mcp():
    db = SessionLocal()
    try:
        return [_mcp_dict(m) for m in db.query(McpServer).order_by(McpServer.id).all()]
    finally:
        db.close()


@app.post("/api/mcp")
def create_mcp(m: McpIn):
    db = SessionLocal()
    try:
        existing = db.query(McpServer).filter(McpServer.name == m.name).first()
        if existing:
            for f, v in m.model_dump(exclude_none=True).items():
                setattr(existing, f, v)
            db.commit()
            return _mcp_dict(existing)
        srv = McpServer(name=m.name, description=m.description, transport=m.transport,
                        command=m.command, url=m.url,
                        enabled=True if m.enabled is None else m.enabled)
        db.add(srv)
        db.commit()
        return _mcp_dict(srv)
    finally:
        db.close()


@app.delete("/api/mcp/{mcp_id}")
async def delete_mcp(mcp_id: int):
    db = SessionLocal()
    try:
        m = db.get(McpServer, mcp_id)
        if m:
            transport, command, url = m.transport, m.command, m.url
            db.delete(m)
            db.commit()
            await mcp_client.close_session(transport, command, url)
        return {"ok": True}
    finally:
        db.close()


class McpCall(BaseModel):
    tool: str
    arguments: dict = {}


@app.post("/api/mcp/{mcp_id}/connect")
async def mcp_connect(mcp_id: int):
    """Verbindet sich mit dem MCP-Server, lädt die Tool-Liste und cached sie."""
    db = SessionLocal()
    try:
        m = db.get(McpServer, mcp_id)
        if not m:
            raise HTTPException(404, "MCP-Server nicht gefunden")
        transport, command, url, name = m.transport, m.command, m.url, m.name
    finally:
        db.close()
    try:
        tools = await mcp_client.list_tools(transport, command=command, url=url)
        status, last_error, tools_json = "connected", "", json.dumps(tools)
    except Exception as e:  # noqa: BLE001
        tools, status, last_error, tools_json = [], "error", str(e), "[]"
    db = SessionLocal()
    try:
        m = db.get(McpServer, mcp_id)
        m.tools_json, m.status, m.last_error = tools_json, status, last_error
        db.commit()
        return {"status": status, "error": last_error,
                "tools": [{"name": t.get("name"), "description": t.get("description", "")}
                          for t in tools]}
    finally:
        db.close()


@app.post("/api/mcp/{mcp_id}/call")
async def mcp_call(mcp_id: int, call: McpCall):
    """Ruft ein MCP-Tool manuell auf (zum Testen)."""
    db = SessionLocal()
    try:
        m = db.get(McpServer, mcp_id)
        if not m:
            raise HTTPException(404, "MCP-Server nicht gefunden")
        transport, command, url = m.transport, m.command, m.url
    finally:
        db.close()
    try:
        result = await mcp_client.call_tool(transport, call.tool, call.arguments,
                                            command=command, url=url)
        return {"ok": True, "text": mcp_client.result_to_text(result)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# E-Mail & Daily-Assistant
# --------------------------------------------------------------------------- #
class EmailOut(BaseModel):
    to: str
    subject: str = ""
    body: str = ""


class ChatIn(BaseModel):
    message: str


@app.post("/api/email/send")
def email_send(m: EmailOut):
    return email_util.send_email(m.to, m.subject, m.body)


@app.get("/api/assistant/status")
def assistant_status():
    db = SessionLocal()
    try:
        s = orch.get_settings(db)
        return {"email_access": s.assistant_email_access,
                "smtp": email_util.smtp_configured(),
                "imap": email_util.imap_configured()}
    finally:
        db.close()


@app.get("/api/assistant/emails")
def assistant_emails(limit: int = 10):
    db = SessionLocal()
    try:
        s = orch.get_settings(db)
        if not s.assistant_email_access:
            return {"ok": False, "error": "E-Mail-Zugang für den Assistenten nicht aktiviert.", "emails": []}
    finally:
        db.close()
    return email_util.fetch_recent(min(limit, 30))


@app.post("/api/assistant/summarize")
async def assistant_summarize(limit: int = 10):
    db = SessionLocal()
    try:
        return await assistant_mod.summarize(db, min(limit, 30))
    finally:
        db.close()


@app.post("/api/assistant/chat")
async def assistant_chat(c: ChatIn):
    db = SessionLocal()
    try:
        return await assistant_mod.chat(db, c.message)
    finally:
        db.close()


@app.post("/api/assistant/send")
def assistant_send(m: EmailOut):
    return email_util.send_email(m.to, m.subject, m.body)


# --------------------------------------------------------------------------- #
# Web-UI
# --------------------------------------------------------------------------- #
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
