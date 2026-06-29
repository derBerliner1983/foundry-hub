"""FastAPI-App: REST-API, Hintergrund-Orchestrator und Auslieferung der Web-UI."""
import asyncio
import json
import os

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant as assistant_mod
from . import auth
from . import context
from . import email_util
from . import knowledge
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

app = FastAPI(title="Foundry-Hub", version="1.0")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


# --------------------------------------------------------------------------- #
# Lebenszyklus
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    from .migrate import ensure_columns
    changed = ensure_columns()
    if changed:
        print("Migration: neue Spalten ->", ", ".join(changed))
    db = SessionLocal()
    try:
        # Pro vorhandenem Nutzer dessen Firma initialisieren
        from .models import User
        users = db.query(User).all()
        for u in users:
            ensure_seed(db, u.id)
    finally:
        db.close()
    secrets_mod.apply_to_environ()  # GUI-Zugangsdaten (Owner) für Subprozesse
    asyncio.create_task(orchestrator_loop())
    asyncio.create_task(_startup_ollama())
    asyncio.create_task(_startup_mcp())


# Öffentliche Pfade (ohne Login erreichbar)
_PUBLIC = {"/api/health", "/api/auth/login", "/api/auth/setup",
           "/api/auth/status", "/api/auth/me"}


# --------------------------------------------------------------------------- #
# Rate-Limiting (in-memory, je Prozess) + Client-IP + IP-Allowlist
# --------------------------------------------------------------------------- #
import time as _time

_rate_hits: dict = {}


def _client_ip(request) -> str:
    """Echte Client-IP – respektiert X-Forwarded-For (hinter Pangolin/Newt)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return getattr(getattr(request, "client", None), "host", "") or ""


def _rate_ok(key: str, limit: int, window: int) -> tuple:
    """True wenn unter dem Limit. Gibt (ok, retry_after_seconds)."""
    now = _time.time()
    hits = [t for t in _rate_hits.get(key, []) if now - t < window]
    if len(hits) >= limit:
        retry = int(window - (now - hits[0])) + 1
        _rate_hits[key] = hits
        return False, retry
    hits.append(now)
    _rate_hits[key] = hits
    return True, 0


def _ip_allowlist() -> list:
    raw = os.getenv("IP_ALLOWLIST", "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def _ip_allowed(ip: str) -> bool:
    allow = _ip_allowlist()
    if not allow:
        return True
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allow:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == entry:
                return True
        except ValueError:
            continue
    return False


def _harden(resp, https: bool):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if https:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


@app.middleware("http")
async def auth_and_tenant(request, call_next):
    from fastapi.responses import JSONResponse
    path = request.url.path
    https = request.url.scheme == "https"
    # IP-Allowlist (falls per Env gesetzt) – gilt für alles
    if not _ip_allowed(_client_ip(request)):
        return _harden(JSONResponse({"error": "Zugriff von dieser IP nicht erlaubt"},
                                    status_code=403), https)
    # Statische UI und öffentliche Auth-Routen frei
    if not path.startswith("/api/") or path in _PUBLIC:
        return _harden(await call_next(request), https)
    # Allgemeines Rate-Limit pro IP für API-Aufrufe
    ok, retry = _rate_ok("api:" + _client_ip(request), limit=300, window=60)
    if not ok:
        return _harden(JSONResponse({"error": "Zu viele Anfragen", "retry_after": retry},
                                    status_code=429), https)
    ctx = auth.current(request)
    if not ctx:
        from fastapi.responses import JSONResponse
        return _harden(JSONResponse({"error": "Nicht angemeldet"}, status_code=401), https)
    context.set_tenant(ctx["tenant_id"])
    request.state.user = ctx
    return _harden(await call_next(request), https)


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
                orch.run_recurring(db)
                orch.poll_telegram(db)
                orch.check_digests(db)
                check_auto_backups()
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
    model_config = {"protected_namespaces": ()}
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
    budget_limit: float | None = None
    thinking_mode: str | None = None
    require_verification: bool | None = None
    incremental_mode: bool | None = None
    model_routing: bool | None = None
    require_review: bool | None = None
    risk_approval: bool | None = None
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    schedule_mode: str | None = None
    active_from: int | None = None
    active_to: int | None = None
    tick_seconds: float | None = None
    user_email: str | None = None
    email_notifications: bool | None = None
    notify_overdue: bool | None = None
    notify_questions: bool | None = None
    daily_digest: bool | None = None
    assistant_email_access: bool | None = None
    auto_backup: bool | None = None
    backup_keep: int | None = None


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


# --------------------------------------------------------------------------- #
# Authentifizierung & Nutzerverwaltung
# --------------------------------------------------------------------------- #
class Credentials(BaseModel):
    username: str
    password: str
    code: str | None = None


class ShareIn(BaseModel):
    username: str


class SwitchIn(BaseModel):
    tenant_id: int


def _set_cookie(resp: Response, token: str, secure: bool):
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax",
                    secure=secure, max_age=auth.SESSION_DAYS * 86400)


@app.get("/api/auth/status")
def auth_status():
    return {"needs_setup": not auth.has_users()}


@app.post("/api/auth/setup")
def auth_setup(c: Credentials, request: Request, response: Response):
    """Erstellt das Owner-Konto – nur möglich, solange es noch keine Nutzer gibt."""
    if auth.has_users():
        raise HTTPException(403, "Setup bereits abgeschlossen")
    if len(c.password) < 6:
        raise HTTPException(400, "Passwort zu kurz (min. 6 Zeichen)")
    uid, err = auth.create_user(c.username, c.password, is_owner=True)
    if err:
        raise HTTPException(400, err)
    db = SessionLocal()
    try:
        ensure_seed(db, uid)
    finally:
        db.close()
    token, _ = auth.login(c.username, c.password)
    _set_cookie(response, token, request.url.scheme == "https")
    return {"ok": True, "owner": True}


@app.post("/api/auth/login")
def auth_login(c: Credentials, request: Request, response: Response):
    ok, retry = _rate_ok("login:" + _client_ip(request), limit=10, window=300)
    if not ok:
        raise HTTPException(429, f"Zu viele Anmeldeversuche – in {retry}s erneut versuchen")
    token, err = auth.login(c.username, c.password, c.code,
                            user_agent=request.headers.get("user-agent", ""),
                            ip=_client_ip(request))
    if err == "locked":
        raise HTTPException(429, "Zu viele Fehlversuche – kurz warten und erneut versuchen")
    if err == "2fa":
        raise HTTPException(401, "2fa")  # Frontend fragt dann den 6-stelligen Code ab
    if not token:
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    _set_cookie(response, token, request.url.scheme == "https")
    return {"ok": True}


class TotpCode(BaseModel):
    code: str


@app.post("/api/auth/2fa/setup")
def totp_setup(request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    from .models import User
    db = SessionLocal()
    try:
        u = db.get(User, ctx["user_id"])
        u.totp_secret = auth.gen_totp_secret()
        u.totp_enabled = False
        db.commit()
        return {"secret": u.totp_secret, "otpauth": auth.otpauth_uri(u.username, u.totp_secret)}
    finally:
        db.close()


@app.post("/api/auth/2fa/enable")
def totp_enable(t: TotpCode, request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    from .models import User
    db = SessionLocal()
    try:
        u = db.get(User, ctx["user_id"])
        if not auth.totp_verify(u.totp_secret, t.code):
            raise HTTPException(400, "Code falsch")
        u.totp_enabled = True
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.post("/api/auth/2fa/disable")
def totp_disable(request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    from .models import User
    db = SessionLocal()
    try:
        u = db.get(User, ctx["user_id"])
        u.totp_enabled = False
        u.totp_secret = ""
        db.commit()
        return {"ok": True}
    finally:
        db.close()


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class PasswordReset(BaseModel):
    new_password: str


@app.post("/api/auth/password")
def change_own_password(p: PasswordChange, request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    ok, err = auth.change_password(ctx["user_id"], p.old_password, p.new_password)
    if not ok:
        raise HTTPException(400, err)
    return {"ok": True}


@app.post("/api/users/{user_id}/reset-password")
def reset_user_password(user_id: int, p: PasswordReset, request: Request):
    _require_owner(request)
    ok, err = auth.reset_password(user_id, p.new_password)
    if not ok:
        raise HTTPException(400, err)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    ctx = auth.current(request)
    if ctx:
        auth.logout(ctx["token"])
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/auth/sessions")
def list_my_sessions(request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    return {"sessions": auth.list_sessions(ctx["user_id"], ctx["token"])}


@app.delete("/api/auth/sessions/{session_id}")
def revoke_my_session(session_id: str, request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    ok = auth.revoke_session(ctx["user_id"], session_id)
    if not ok:
        raise HTTPException(404, "Sitzung nicht gefunden")
    return {"ok": True}


@app.post("/api/auth/sessions/revoke-others")
def revoke_other_sessions(request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    n = auth.revoke_other_sessions(ctx["user_id"], ctx["token"])
    return {"ok": True, "revoked": n}


@app.get("/api/auth/me")
def auth_me(request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    from .models import User
    db = SessionLocal()
    try:
        tenants = []
        for tid in sorted(auth.accessible_tenants(ctx["user_id"])):
            owner = db.get(User, tid)
            tenants.append({"tenant_id": tid,
                            "name": (owner.username + " (Firma)") if owner else f"Firma {tid}",
                            "own": tid == ctx["user_id"]})
        me_user = db.get(User, ctx["user_id"])
        return {"user_id": ctx["user_id"], "username": ctx["username"],
                "is_owner": ctx["is_owner"], "active_tenant": ctx["tenant_id"],
                "totp_enabled": bool(me_user and me_user.totp_enabled),
                "tenants": tenants}
    finally:
        db.close()


@app.post("/api/auth/switch")
def auth_switch(s: SwitchIn, request: Request):
    ctx = auth.current(request)
    if not ctx:
        raise HTTPException(401, "Nicht angemeldet")
    if not auth.set_active_tenant(ctx["token"], s.tenant_id):
        raise HTTPException(403, "Kein Zugriff auf diese Firma")
    return {"ok": True}


def _require_owner(request: Request):
    ctx = auth.current(request)
    if not ctx or not ctx["is_owner"]:
        raise HTTPException(403, "Nur der Owner darf das")
    return ctx


def _audit(request, text):
    ctx = auth.current(request)
    if not ctx:
        return
    context.set_tenant(ctx["tenant_id"])  # ensure_seed kann den Context verstellt haben
    db = SessionLocal()
    try:
        orch.log(db, "audit", f"{ctx['username']}: {text}")
        db.commit()
    finally:
        db.close()


@app.get("/api/users")
def list_users(request: Request):
    _require_owner(request)
    from .models import User, Access
    db = SessionLocal()
    try:
        owner = _require_owner(request)
        users = db.query(User).order_by(User.id).all()
        shared = {a.user_id for a in db.query(Access).filter(Access.tenant_id == owner["user_id"]).all()}
        return [{"id": u.id, "username": u.username, "is_owner": u.is_owner,
                 "has_access_to_my_firm": u.id in shared} for u in users]
    finally:
        db.close()


@app.post("/api/users")
def create_user(c: Credentials, request: Request):
    _require_owner(request)
    if len(c.password) < 6:
        raise HTTPException(400, "Passwort zu kurz (min. 6 Zeichen)")
    uid, err = auth.create_user(c.username, c.password, is_owner=False)
    if err:
        raise HTTPException(400, err)
    db = SessionLocal()
    try:
        ensure_seed(db, uid)   # eigene Firma für den neuen Nutzer
    finally:
        db.close()
    _audit(request, f"Nutzer '{c.username}' angelegt")
    return {"ok": True, "id": uid}


@app.post("/api/access")
def share_firm(s: ShareIn, request: Request):
    """Owner teilt SEINE Firma mit einem anderen Nutzer."""
    owner = _require_owner(request)
    ok, msg = auth.grant_access(owner["user_id"], s.username)
    if not ok:
        raise HTTPException(400, msg)
    _audit(request, f"Firma mit '{s.username}' geteilt")
    return {"ok": True, "note": msg}


@app.delete("/api/access/{user_id}")
def unshare_firm(user_id: int, request: Request):
    owner = _require_owner(request)
    auth.revoke_access(owner["user_id"], user_id)
    return {"ok": True}


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
        projects = db.query(Project).filter(Project.status == "active", Project.tenant_id == context.tid()).order_by(Project.id.desc()).all()
        agents = db.query(Agent).filter(Agent.status == "employed", Agent.tenant_id == context.tid()).all()
        all_tasks = db.query(Task).filter(Task.tenant_id == context.tid()).all()
        all_ms = db.query(Milestone).filter(Milestone.tenant_id == context.tid()).all()

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
                     .filter(Message.tenant_id == context.tid(),
                             Message.recipient_kind == "user",
                             Message.requires_answer == True,  # noqa: E712
                             Message.answered == False)  # noqa: E712
                     .order_by(Message.id.desc()).limit(10).all())
        approvals = (db.query(PendingApproval)
                     .filter(PendingApproval.status == "pending",
                             PendingApproval.tenant_id == context.tid())
                     .order_by(PendingApproval.id).all())
        events = db.query(Event).filter(Event.tenant_id == context.tid()).order_by(Event.id.desc()).limit(8).all()

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
        chef = db.query(Agent).filter(Agent.role == "ceo", Agent.tenant_id == context.tid()).first()
        agents = db.query(Agent).filter(Agent.tenant_id == context.tid()).order_by(Agent.id).all()
        return {
            "chef_id": chef.id if chef else None,
            "agents": [agent_dict(db, a) for a in agents],
            "open_questions": db.query(Message).filter(
                Message.tenant_id == context.tid(),
                Message.recipient_kind == "user",
                Message.requires_answer == True,  # noqa: E712
                Message.answered == False).count(),  # noqa: E712
            "pending_approvals": db.query(PendingApproval).filter(
                PendingApproval.status == "pending",
                PendingApproval.tenant_id == context.tid()).count(),
        }
    finally:
        db.close()


@app.post("/api/requests")
def create_request(req: NewRequest):
    """Neue Anfrage des Nutzers an den Chef."""
    db = SessionLocal()
    try:
        chef = ensure_seed(db, context.tid())
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
            chef = db.query(Agent).filter(Agent.role == "ceo", Agent.tenant_id == context.tid()).first()
            target_id = chef.id if chef else None
        else:
            target_id = m.to_agent_id
        if not target_id:
            raise HTTPException(404, "Kein Empfänger")
        # Empfänger muss zur eigenen Firma gehören
        ta = db.get(Agent, target_id)
        if not ta or ta.tenant_id != context.tid():
            raise HTTPException(404, "Empfänger nicht gefunden")
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
        q = db.query(Message).filter(Message.tenant_id == context.tid())
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
        if not a or a.tenant_id != context.tid():
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
        if not a or a.tenant_id != context.tid():
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
        tasks = db.query(Task).filter(Task.tenant_id == context.tid()).order_by(Task.id.desc()).limit(200).all()
        return [{"id": t.id, "title": t.title, "description": t.description,
                 "status": t.status, "assigned_agent_id": t.assigned_agent_id,
                 "milestone_id": t.milestone_id, "result": t.result,
                 "depends_on": t.depends_on or "",
                 "blocked": (t.status in ("todo", "in_progress") and not orch.task_deps_met(db, t))}
                for t in tasks]
    finally:
        db.close()


class TaskUpdate(BaseModel):
    status: str | None = None
    depends_on: str | None = None


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, u: TaskUpdate):
    db = SessionLocal()
    try:
        t = db.get(Task, task_id)
        if not t or t.tenant_id != context.tid():
            raise HTTPException(404, "Aufgabe nicht gefunden")
        if u.status in ("todo", "in_progress", "review", "done", "failed"):
            t.status = u.status
            if u.status == "done":
                t.verified = True
                orch._refresh_milestone_status(db, t.milestone_id, None)
        if u.depends_on is not None:
            # nur gültige, andere Task-IDs der gleichen Firma zulassen (keine Selbst-Abhängigkeit)
            ids = []
            for p in u.depends_on.replace(" ", "").split(","):
                if p.isdigit() and int(p) != task_id:
                    dt = db.get(Task, int(p))
                    if dt and dt.tenant_id == context.tid():
                        ids.append(p)
            t.depends_on = ",".join(ids)
        db.commit()
        return {"ok": True}
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
            PendingApproval.status == "pending",
            PendingApproval.tenant_id == context.tid()).order_by(PendingApproval.id).all()
        return [{"id": a.id, "summary": a.summary,
                 "action": json.loads(a.action_json)} for a in items]
    finally:
        db.close()


@app.post("/api/approvals/{approval_id}/{decision}")
def decide_approval(approval_id: int, decision: str):
    db = SessionLocal()
    try:
        ap = db.get(PendingApproval, approval_id)
        if not ap or ap.tenant_id != context.tid() or ap.status != "pending":
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
            elif action.get("type") == "run_command":
                res = workspace.run_command(action.get("pctx"), action.get("cmd", ""))
                orch.log(db, "exec", f"$ {action.get('cmd','')} (freigegeben) → "
                         f"{'ok' if res.get('ok') else 'Fehler'}")
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
        evs = db.query(Event).filter(Event.tenant_id == context.tid()).order_by(Event.id.desc()).limit(100).all()
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
            "budget_limit": s.budget_limit,
            "thinking_mode": s.thinking_mode,
            "require_verification": s.require_verification,
            "incremental_mode": s.incremental_mode,
            "model_routing": s.model_routing,
            "require_review": s.require_review,
            "risk_approval": s.risk_approval,
            "telegram_token": s.telegram_token,
            "telegram_chat_id": s.telegram_chat_id,
            "schedule_mode": s.schedule_mode,
            "active_from": s.active_from,
            "active_to": s.active_to,
            "tick_seconds": s.tick_seconds,
            "user_email": s.user_email,
            "email_notifications": s.email_notifications,
            "notify_overdue": s.notify_overdue,
            "notify_questions": s.notify_questions,
            "daily_digest": s.daily_digest,
            "assistant_email_access": s.assistant_email_access,
            "auto_backup": s.auto_backup,
            "backup_keep": s.backup_keep,
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
        data = upd.model_dump(exclude_none=True)
        if "budget_limit" in data:
            s.budget_notified = False  # bei neuem Budget Pausierung aufheben
        for field, value in data.items():
            setattr(s, field, value)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/budget")
def budget():
    """Verbrauch (USD) der aktuellen Firma – gesamt, je Modell, je Projekt."""
    from .models import Usage
    db = SessionLocal()
    try:
        s = orch.get_settings(db)
        rows = db.query(Usage).filter(Usage.tenant_id == context.tid()).all()
        total = round(sum(r.cost for r in rows), 4)
        in_tok = sum(r.input_tokens for r in rows)
        out_tok = sum(r.output_tokens for r in rows)
        by_model = {}
        for r in rows:
            by_model.setdefault(r.model, 0.0)
            by_model[r.model] += r.cost
        return {"spent": total, "limit": s.budget_limit or 0.0,
                "input_tokens": in_tok, "output_tokens": out_tok,
                "calls": len(rows),
                "by_model": [{"model": k, "cost": round(v, 4)} for k, v in
                             sorted(by_model.items(), key=lambda x: -x[1])],
                "paused": bool(s.budget_limit and total >= s.budget_limit > 0)}
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
                for p in db.query(Project).filter(Project.tenant_id == context.tid()).order_by(Project.id.desc()).all()]
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
        msq = db.query(Milestone).filter(Milestone.tenant_id == context.tid())
        tq = db.query(Task).filter(Task.tenant_id == context.tid())
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
        q = db.query(Milestone).filter(Milestone.tenant_id == context.tid())
        if project_id is not None:
            q = q.filter(Milestone.project_id == project_id)
        return [_ms_dict(m) for m in q.order_by(Milestone.order_index, Milestone.id).all()]
    finally:
        db.close()


@app.post("/api/milestones")
def create_milestone(m: MilestoneIn):
    db = SessionLocal()
    try:
        n = db.query(Milestone).filter(Milestone.project_id == m.project_id, Milestone.tenant_id == context.tid()).count()
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
        if not ms or ms.tenant_id != context.tid():
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
        if ms and ms.tenant_id == context.tid():
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
        q = db.query(Decision).filter(Decision.tenant_id == context.tid())
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


@app.post("/api/workspace/upload")
async def workspace_upload(project_id: int | None = Form(None), file: UploadFile = File(...)):
    """Lädt eine Datei in den Projekt-Workspace (für Specs, Designs, Daten)."""
    data = await file.read()
    try:
        rel = workspace.save_bytes(project_id, file.filename or "upload.bin", data)
        return {"ok": True, "path": rel, "size": len(data)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.get("/api/workspace/download")
def workspace_download(path: str, project_id: int | None = None, inline: int = 0):
    """Lädt eine Datei herunter (inline=1 zeigt sie im Browser, z. B. HTML-Vorschau)."""
    try:
        target = workspace.safe_abspath(project_id, path)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Ungültiger Pfad")
    if not os.path.isfile(target):
        raise HTTPException(404, "Datei nicht gefunden")
    if inline:
        import mimetypes
        mt = mimetypes.guess_type(target)[0] or "text/plain"
        return FileResponse(target, media_type=mt)
    return FileResponse(target, filename=os.path.basename(target))


@app.get("/api/workspace/zip")
def workspace_zip(project_id: int | None = None):
    """Lädt den gesamten Projekt-Workspace als ZIP herunter."""
    path = workspace.make_zip(project_id)
    return FileResponse(path, filename=f"project_{project_id or 'shared'}.zip",
                        media_type="application/zip")


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


@app.get("/api/github/status")
def github_status():
    from . import github_util
    return github_util.status()


class GithubPush(BaseModel):
    project_id: int | None = None
    repo_name: str
    private: bool = True


@app.post("/api/github/push")
def github_push(g: GithubPush):
    from . import github_util
    return github_util.push_project(g.project_id, g.repo_name, g.private)


class ProjectCfg(BaseModel):
    test_command: str | None = None
    deploy_command: str | None = None


@app.put("/api/projects/{project_id}")
def update_project(project_id: int, cfg: ProjectCfg):
    db = SessionLocal()
    try:
        p = db.get(Project, project_id)
        if not p or p.tenant_id != context.tid():
            raise HTTPException(404, "Projekt nicht gefunden")
        if cfg.test_command is not None:
            p.test_command = cfg.test_command
        if cfg.deploy_command is not None:
            p.deploy_command = cfg.deploy_command
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    db = SessionLocal()
    try:
        p = db.get(Project, project_id)
        if not p or p.tenant_id != context.tid():
            raise HTTPException(404, "Projekt nicht gefunden")
        return {"id": p.id, "title": p.title, "test_command": p.test_command,
                "deploy_command": p.deploy_command}
    finally:
        db.close()


@app.post("/api/deploy")
def deploy(project_id: int | None = None):
    """Führt den Deploy-Befehl des Projekts aus (Sandbox/lokal)."""
    db = SessionLocal()
    try:
        cmd = ""
        if project_id is not None:
            p = db.get(Project, project_id)
            if not p or p.tenant_id != context.tid():
                raise HTTPException(404, "Projekt nicht gefunden")
            cmd = p.deploy_command
    finally:
        db.close()
    if not cmd:
        return {"ok": False, "error": "Kein Deploy-Befehl für dieses Projekt gesetzt."}
    res = workspace.run_command(project_id, cmd)
    return {"ok": res["ok"], "output": (res["stdout"] + "\n" + res["stderr"])[-4000:]}


# --- Projekt-Vorlagen ---
TEMPLATES = {
    "landingpage": {"title": "Landingpage", "milestones": ["Design & Wireframe", "Inhalte", "Umsetzung (HTML/CSS)", "Test & Launch"],
                    "brief": "Erstelle eine moderne, responsive Landingpage."},
    "webapp": {"title": "Kleine Web-App", "milestones": ["Konzept & Datenmodell", "Backend/API", "Frontend", "Tests", "Deploy"],
               "brief": "Baue eine kleine Web-App mit Backend und Frontend."},
    "report": {"title": "Recherche-Report", "milestones": ["Recherche", "Struktur", "Schreiben", "Review"],
               "brief": "Erstelle einen strukturierten Recherche-Report zum Thema."},
    "automation": {"title": "Automatisierungs-Skript", "milestones": ["Anforderungen", "Skript", "Tests", "Doku"],
                   "brief": "Entwickle ein Skript, das eine Aufgabe automatisiert."},
}


@app.get("/api/templates")
def list_templates():
    return [{"key": k, "title": v["title"], "milestones": v["milestones"]} for k, v in TEMPLATES.items()]


class FromTemplate(BaseModel):
    template: str
    title: str
    description: str = ""


@app.post("/api/projects/from-template")
def project_from_template(t: FromTemplate):
    from .models import Milestone
    tpl = TEMPLATES.get(t.template)
    if not tpl:
        raise HTTPException(400, "Unbekannte Vorlage")
    db = SessionLocal()
    try:
        chef = ensure_seed(db, context.tid())
        context.set_tenant(context.tid())
        project = Project(title=t.title, description=t.description or tpl["brief"])
        db.add(project)
        db.flush()
        for i, m in enumerate(tpl["milestones"]):
            db.add(Milestone(project_id=project.id, title=m, status="planned", order_index=i))
        orch.send_message(db, sender_kind="user", sender_agent_id=None,
                          recipient_kind="agent", recipient_agent_id=chef.id,
                          subject="Neues Projekt: " + t.title,
                          body=(t.description or tpl["brief"]) +
                          "\n\nGeplante Schritte: " + ", ".join(tpl["milestones"]),
                          project_id=project.id)
        db.commit()
        return {"ok": True, "project_id": project.id}
    finally:
        db.close()


_local_preview = {"proc": None}


class PreviewIn(BaseModel):
    project_id: int | None = None
    cmd: str = ""


@app.post("/api/preview/start")
def preview_start(p: PreviewIn):
    """Startet einen Live-Vorschau-Server für das Projekt (Sandbox oder lokal)."""
    rel = f"project_{p.project_id if p.project_id is not None else 'shared'}"
    port = config.PREVIEW_PORT
    if config.SANDBOX_URL:
        try:
            import httpx
            httpx.post(f"{config.SANDBOX_URL}/serve",
                       json={"rel": rel, "cmd": p.cmd, "port": port}, timeout=15)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    else:
        import subprocess
        if _local_preview["proc"] and _local_preview["proc"].poll() is None:
            _local_preview["proc"].terminate()
        cwd = workspace.safe_abspath(p.project_id, "")
        cmd = p.cmd or f"python -m http.server {port} --bind 0.0.0.0"
        _local_preview["proc"] = subprocess.Popen(cmd, shell=True, cwd=cwd)
    return {"ok": True, "port": port, "url": f"http://localhost:{port}"}


@app.post("/api/preview/stop")
def preview_stop():
    if config.SANDBOX_URL:
        try:
            import httpx
            httpx.post(f"{config.SANDBOX_URL}/serve/stop", timeout=10)
        except Exception:  # noqa: BLE001
            pass
    elif _local_preview["proc"]:
        _local_preview["proc"].terminate()
        _local_preview["proc"] = None
    return {"ok": True}


@app.get("/api/git/history")
def git_history(project_id: int | None = None):
    return {"history": workspace.git_history(project_id)}


@app.get("/api/git/diff")
def git_diff(commit: str, project_id: int | None = None, base: str = ""):
    return workspace.git_diff(project_id, commit, base)


class RollbackIn(BaseModel):
    project_id: int | None = None
    commit: str


@app.post("/api/git/rollback")
def git_rollback(r: RollbackIn):
    res = workspace.git_rollback(r.project_id, r.commit)
    return res


@app.get("/api/console")
def console(project_id: int | None = None):
    """Letzte Befehlsausführungen (aus dem Event-Log)."""
    db = SessionLocal()
    try:
        evs = (db.query(Event).filter(Event.kind.in_(["exec", "file"]), Event.tenant_id == context.tid())
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
        chef = ensure_seed(db, context.tid())
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
        chef = ensure_seed(db, context.tid())
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
        return [_rule_dict(r) for r in db.query(Rule).filter(Rule.tenant_id == context.tid()).order_by(Rule.id.desc()).all()]
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
        if not rule or rule.tenant_id != context.tid():
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
        if rule and rule.tenant_id == context.tid():
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
        return [_skill_dict(s) for s in db.query(Skill).filter(Skill.tenant_id == context.tid()).order_by(Skill.id).all()]
    finally:
        db.close()


@app.post("/api/skills")
def create_skill(s: SkillIn):
    db = SessionLocal()
    try:
        existing = db.query(Skill).filter(Skill.name == s.name, Skill.tenant_id == context.tid()).first()
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
        if s and s.tenant_id == context.tid():
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
        return [_mcp_dict(m) for m in db.query(McpServer).filter(McpServer.tenant_id == context.tid()).order_by(McpServer.id).all()]
    finally:
        db.close()


@app.post("/api/mcp")
def create_mcp(m: McpIn):
    db = SessionLocal()
    try:
        existing = db.query(McpServer).filter(McpServer.name == m.name, McpServer.tenant_id == context.tid()).first()
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
        if m and m.tenant_id == context.tid():
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
# Wiederkehrende Aufträge, Kosten-Verlauf, Backup, Audit
# --------------------------------------------------------------------------- #
class RecurringIn(BaseModel):
    title: str
    description: str = ""
    as_project: bool = False
    interval: str = "daily"
    hour: int = 9
    weekday: int = 0
    enabled: bool | None = None


@app.get("/api/recurring")
def list_recurring():
    from .models import RecurringJob
    db = SessionLocal()
    try:
        return [{"id": j.id, "title": j.title, "description": j.description,
                 "as_project": j.as_project, "interval": j.interval, "hour": j.hour,
                 "weekday": j.weekday, "enabled": j.enabled,
                 "last_run": j.last_run.isoformat() if j.last_run else None}
                for j in db.query(RecurringJob).filter(RecurringJob.tenant_id == context.tid())
                .order_by(RecurringJob.id).all()]
    finally:
        db.close()


@app.post("/api/recurring")
def create_recurring(r: RecurringIn):
    from .models import RecurringJob
    db = SessionLocal()
    try:
        j = RecurringJob(title=r.title, description=r.description, as_project=r.as_project,
                         interval=r.interval, hour=r.hour, weekday=r.weekday,
                         enabled=True if r.enabled is None else r.enabled)
        db.add(j)
        db.commit()
        return {"ok": True, "id": j.id}
    finally:
        db.close()


@app.delete("/api/recurring/{job_id}")
def delete_recurring(job_id: int):
    from .models import RecurringJob
    db = SessionLocal()
    try:
        j = db.get(RecurringJob, job_id)
        if j and j.tenant_id == context.tid():
            db.delete(j)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


class DocIn(BaseModel):
    title: str
    content: str = ""
    project_id: int | None = None


@app.get("/api/knowledge")
def list_knowledge():
    from .models import Document
    db = SessionLocal()
    try:
        return [{"id": d.id, "title": d.title, "source": d.source,
                 "chars": len(d.content or ""), "project_id": d.project_id}
                for d in db.query(Document).filter(Document.tenant_id == context.tid())
                .order_by(Document.id.desc()).all()]
    finally:
        db.close()


def _embed_json(title, content):
    """Chunk-basiertes Embedding (RAG) für ein Dokument."""
    from . import knowledge as _kn
    return _kn.embed_doc_json(title, content)


@app.post("/api/knowledge")
def add_knowledge(d: DocIn):
    from .models import Document
    db = SessionLocal()
    try:
        doc = Document(title=d.title, content=d.content, project_id=d.project_id,
                       source="note", embedding=_embed_json(d.title, d.content))
        db.add(doc)
        db.commit()
        return {"ok": True, "id": doc.id}
    finally:
        db.close()


@app.post("/api/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...)):
    from .models import Document
    raw = await file.read()
    fn = (file.filename or "").lower()
    text = ""
    if fn.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except Exception:  # noqa: BLE001
            text = ""
    elif fn.endswith(".docx"):
        try:
            import io
            import re as _re
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            xml = _re.sub(r"</w:p>", "\n", xml)
            text = _re.sub(r"(?s)<[^>]+>", "", xml)
        except Exception:  # noqa: BLE001
            text = ""
    if not text:
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
    db = SessionLocal()
    try:
        doc = Document(title=file.filename or "Dokument", content=text[:200000],
                       source="upload", embedding=_embed_json(file.filename, text[:200000]))
        db.add(doc)
        db.commit()
        return {"ok": True, "id": doc.id, "chars": len(text)}
    finally:
        db.close()


@app.post("/api/knowledge/reindex")
def reindex_knowledge():
    """Berechnet Embeddings für alle Dokumente neu (z. B. nach Key-Eingabe)."""
    from .models import Document
    from . import embeddings
    db = SessionLocal()
    try:
        n = 0
        if embeddings.available():
            for d in db.query(Document).filter(Document.tenant_id == context.tid()).all():
                d.embedding = _embed_json(d.title, d.content)
                n += 1
            db.commit()
        return {"ok": True, "indexed": n, "available": embeddings.available()}
    finally:
        db.close()


class WebIngest(BaseModel):
    url: str


@app.post("/api/knowledge/web")
def knowledge_web(w: WebIngest):
    """Lädt eine Webseite, extrahiert den Text und legt ihn als Wissen ab."""
    import re as _re
    import httpx
    from .models import Document
    try:
        r = httpx.get(w.url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "foundry-hub/1.0"})
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Konnte URL nicht laden: {e}")
    html = _re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = _re.sub(r"(?s)<[^>]+>", " ", html)
    import html as _h
    text = _re.sub(r"\s+", " ", _h.unescape(text)).strip()[:200000]
    title = (_re.search(r"<title>(.*?)</title>", html, _re.I | _re.S) or [None, w.url])[1].strip()[:120]
    db = SessionLocal()
    try:
        doc = Document(title="🌐 " + title, content=text, source="upload",
                       embedding=_embed_json(title, text[:200000]))
        db.add(doc)
        db.commit()
        return {"ok": True, "id": doc.id, "chars": len(text), "title": title}
    finally:
        db.close()


@app.delete("/api/knowledge/{doc_id}")
def delete_knowledge(doc_id: int):
    from .models import Document
    db = SessionLocal()
    try:
        d = db.get(Document, doc_id)
        if d and d.tenant_id == context.tid():
            db.delete(d)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/knowledge/search")
def knowledge_search(q: str):
    from . import knowledge
    return {"results": knowledge.search(q)}


@app.get("/api/vault")
def vault_list():
    from . import vault
    return {"enabled": vault.enabled(), "notes": vault.list_notes()}


@app.get("/api/vault/note")
def vault_note(name: str):
    from . import vault
    return {"name": name, "content": vault.read_note(name)}


class NoteIn(BaseModel):
    title: str
    content: str = ""


@app.post("/api/vault/note")
def vault_write(n: NoteIn):
    from . import vault
    if not vault.enabled():
        raise HTTPException(400, "Keine Obsidian-Vault konfiguriert (OBSIDIAN_VAULT).")
    rel = vault.write_note(n.title, n.content)
    return {"ok": True, "name": rel}


@app.post("/api/digest/send")
def digest_send():
    db = SessionLocal()
    try:
        text = orch.build_digest(db, context.tid())
        orch.maybe_notify(db, "digest", "Tagesüberblick (manuell)", text)
        return {"ok": True, "preview": text}
    finally:
        db.close()


@app.get("/api/budget/history")
def budget_history(days: int = 30):
    """Tägliche Kosten der aktuellen Firma (für ein Diagramm)."""
    from .models import Usage
    db = SessionLocal()
    try:
        from datetime import datetime as _dt
        rows = db.query(Usage).filter(Usage.tenant_id == context.tid()).all()
        by_day = {}
        for r in rows:
            d = (r.created_at or _dt.utcnow()).date().isoformat()
            by_day[d] = round(by_day.get(d, 0.0) + r.cost, 4)
        series = [{"date": k, "cost": v} for k, v in sorted(by_day.items())][-days:]
        return {"series": series}
    finally:
        db.close()


def _snapshot_data():
    """Vollständiger JSON-Snapshot der aktuellen Firma (Tenant aus Context)."""
    from .models import (Agent as A, Project as P, Task as T, Milestone as Mi,
                         Rule as Ru, Skill as Sk, McpServer as Mc, Settings as Se)
    db = SessionLocal()
    try:
        t = context.tid()

        def dump(model, cols):
            return [{c: getattr(o, c) for c in cols}
                    for o in db.query(model).filter(model.tenant_id == t).all()]
        return {
            "tenant": t,
            "settings": dump(Se, ["autonomy_level", "default_chef_provider", "default_chef_model",
                                  "default_worker_provider", "default_worker_model", "thinking_mode",
                                  "require_verification", "incremental_mode", "model_routing",
                                  "require_review", "risk_approval", "budget_limit"]),
            "agents": dump(A, ["id", "name", "role", "provider", "model", "status", "manager_id", "project_id"]),
            "projects": dump(P, ["id", "title", "description", "status", "test_command"]),
            "tasks": dump(T, ["id", "title", "description", "status", "project_id", "milestone_id"]),
            "milestones": dump(Mi, ["id", "title", "status", "project_id", "order_index"]),
            "rules": dump(Ru, ["title", "content", "scope", "role", "active"]),
            "skills": dump(Sk, ["name", "description", "instructions", "command", "enabled"]),
            "mcp": dump(Mc, ["name", "description", "transport", "command", "url", "enabled"]),
        }
    finally:
        db.close()


def _build_full_backup_zip(dest_path: str = None) -> str:
    """Schreibt ein Voll-Backup (Snapshot + Workspaces + Vault) als ZIP und gibt
    den Pfad zurück. Operiert auf dem Tenant im aktuellen Context."""
    import json as _json
    import tempfile
    import zipfile
    from .models import Project as P
    t = context.tid()
    snapshot = _snapshot_data()
    db = SessionLocal()
    try:
        project_ids = [p.id for p in db.query(P).filter(P.tenant_id == t).all()]
    finally:
        db.close()
    if dest_path is None:
        fd, dest_path = tempfile.mkstemp(suffix=".zip", prefix=f"backup_tenant_{t}_")
        os.close(fd)
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("snapshot.json", _json.dumps(snapshot, default=str, ensure_ascii=False, indent=2))
        for pid in project_ids + ["shared"]:
            root = os.path.join(config.WORKSPACE_DIR, f"project_{pid}")
            if os.path.isdir(root):
                for base, _d, files in os.walk(root):
                    for fn in files:
                        full = os.path.join(base, fn)
                        z.write(full, "workspace/" + os.path.relpath(full, config.WORKSPACE_DIR))
        vroot = os.path.join(config.OBSIDIAN_VAULT, "Foundry-Hub", f"tenant_{t}")
        if os.path.isdir(vroot):
            for base, _d, files in os.walk(vroot):
                for fn in files:
                    full = os.path.join(base, fn)
                    z.write(full, "vault/" + os.path.relpath(full, vroot))
    return dest_path


@app.get("/api/backup/export")
def backup_export(request: Request):
    """Vollständiger JSON-Snapshot der aktuellen Firma (Backup)."""
    return _snapshot_data()


@app.get("/api/backup/full")
def backup_full(request: Request):
    """Vollständiges Backup als ZIP: DB-Snapshot (JSON) + Workspaces + Vault."""
    t = context.tid()
    path = _build_full_backup_zip()
    return FileResponse(path, filename=f"foundry-hub-backup-tenant-{t}.zip", media_type="application/zip")


class ConfigImport(BaseModel):
    rules: list = []
    skills: list = []
    mcp: list = []


@app.post("/api/backup/import-config")
def backup_import_config(data: ConfigImport):
    """Importiert Regeln/Skills/MCP-Server in die aktuelle Firma (z. B. aus einem Export)."""
    from .models import Rule as Ru, Skill as Sk, McpServer as Mc
    db = SessionLocal()
    try:
        for r in data.rules[:200]:
            db.add(Ru(title=r.get("title", "Regel"), content=r.get("content", ""),
                      scope=r.get("scope", "global"), role=r.get("role"),
                      active=r.get("active", True), source="user"))
        for s in data.skills[:200]:
            if not db.query(Sk).filter(Sk.name == s.get("name"), Sk.tenant_id == context.tid()).first():
                db.add(Sk(name=s.get("name"), description=s.get("description", ""),
                          instructions=s.get("instructions", ""), command=s.get("command", ""),
                          enabled=s.get("enabled", True)))
        for m in data.mcp[:50]:
            if not db.query(Mc).filter(Mc.name == m.get("name"), Mc.tenant_id == context.tid()).first():
                db.add(Mc(name=m.get("name"), description=m.get("description", ""),
                          transport=m.get("transport", "stdio"), command=m.get("command", ""),
                          url=m.get("url", ""), enabled=m.get("enabled", True)))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def _restore_snapshot(snapshot: dict) -> dict:
    """Stellt Konfiguration aus einem Snapshot in der AKTUELLEN Firma wieder her.
    Konservativ: legt Regeln/Skills/MCP/Projekte/Settings an bzw. aktualisiert sie,
    löscht aber nichts Bestehendes (kein destruktives Überschreiben)."""
    from .models import (Project as P, Rule as Ru, Skill as Sk, McpServer as Mc,
                         Settings as Se)
    counts = {"projects": 0, "rules": 0, "skills": 0, "mcp": 0, "settings": 0}
    db = SessionLocal()
    try:
        t = context.tid()
        for p in snapshot.get("projects", []):
            if not db.query(P).filter(P.tenant_id == t, P.title == p.get("title")).first():
                db.add(P(title=p.get("title", "Projekt"), description=p.get("description", ""),
                         status=p.get("status", "active"), test_command=p.get("test_command", "")))
                counts["projects"] += 1
        for r in snapshot.get("rules", []):
            if not db.query(Ru).filter(Ru.tenant_id == t, Ru.title == r.get("title")).first():
                db.add(Ru(title=r.get("title", "Regel"), content=r.get("content", ""),
                          scope=r.get("scope", "global"), role=r.get("role"),
                          active=r.get("active", True), source="user"))
                counts["rules"] += 1
        for s in snapshot.get("skills", []):
            if not db.query(Sk).filter(Sk.tenant_id == t, Sk.name == s.get("name")).first():
                db.add(Sk(name=s.get("name"), description=s.get("description", ""),
                          instructions=s.get("instructions", ""), command=s.get("command", ""),
                          enabled=s.get("enabled", True)))
                counts["skills"] += 1
        for m in snapshot.get("mcp", []):
            if not db.query(Mc).filter(Mc.tenant_id == t, Mc.name == m.get("name")).first():
                db.add(Mc(name=m.get("name"), description=m.get("description", ""),
                          transport=m.get("transport", "stdio"), command=m.get("command", ""),
                          url=m.get("url", ""), enabled=m.get("enabled", True)))
                counts["mcp"] += 1
        sset = snapshot.get("settings", [])
        if sset:
            cur = db.query(Se).filter(Se.tenant_id == t).first()
            if cur:
                for k, v in sset[0].items():
                    if hasattr(cur, k):
                        setattr(cur, k, v)
                counts["settings"] = 1
        db.commit()
        return counts
    finally:
        db.close()


@app.post("/api/backup/restore-full")
async def backup_restore_full(file: UploadFile = File(...)):
    """Stellt aus einem Voll-Backup-ZIP wieder her: Snapshot (Konfiguration),
    Workspaces und Vault-Notizen."""
    import io as _io
    import json as _json
    import zipfile
    raw = await file.read()
    try:
        z = zipfile.ZipFile(_io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Keine gültige ZIP-Datei")
    names = z.namelist()
    counts = {}
    if "snapshot.json" in names:
        try:
            snapshot = _json.loads(z.read("snapshot.json").decode("utf-8"))
            counts = _restore_snapshot(snapshot)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Snapshot fehlerhaft: {e}")
    files_written = 0
    t = context.tid()
    for name in names:
        try:
            if name.startswith("workspace/"):
                rel = name[len("workspace/"):]
                if not rel or rel.endswith("/"):
                    continue
                dest = os.path.realpath(os.path.join(config.WORKSPACE_DIR, rel))
                if not dest.startswith(os.path.realpath(config.WORKSPACE_DIR)):
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(name))
                files_written += 1
            elif name.startswith("vault/"):
                rel = name[len("vault/"):]
                if not rel or rel.endswith("/"):
                    continue
                vroot = os.path.join(config.OBSIDIAN_VAULT, "Foundry-Hub", f"tenant_{t}")
                dest = os.path.realpath(os.path.join(vroot, rel))
                if not dest.startswith(os.path.realpath(vroot)):
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(name))
                files_written += 1
        except Exception:  # noqa: BLE001
            continue
    return {"ok": True, "restored": counts, "files": files_written}


def _backup_dir(tenant_id: int) -> str:
    base = os.path.join(os.path.dirname(config.DATABASE_URL.split("///")[-1])
                        if config.DATABASE_URL.startswith("sqlite") else "/data",
                        "backups", f"tenant_{tenant_id}")
    return base


def _make_auto_backup(tenant_id: int, keep: int = 7) -> str:
    """Erstellt eine Voll-Sicherung im Backup-Ordner der Firma und löscht alte
    (über ``keep`` hinaus). Erwartet, dass der Context auf den Tenant gesetzt ist."""
    from datetime import datetime as _d
    d = _backup_dir(tenant_id)
    os.makedirs(d, exist_ok=True)
    ts = _d.utcnow().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(d, f"backup-{ts}.zip")
    try:
        _build_full_backup_zip(dest)
    except Exception as e:  # noqa: BLE001
        print("Auto-Backup-Fehler:", e)
        return ""
    # Rotation: nur die neuesten `keep` behalten
    zips = sorted([f for f in os.listdir(d) if f.endswith(".zip")], reverse=True)
    for old in zips[max(1, keep):]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return dest


# letzte automatische Sicherung je Tenant (Datum), verhindert Mehrfach-Backups/Tag
_auto_backup_done: dict = {}


def check_auto_backups():
    """Prüft je Firma, ob heute schon gesichert wurde – wenn nicht und aktiviert,
    legt eine Sicherung an. Wird im Orchestrator-Takt aufgerufen."""
    from datetime import datetime as _d
    from .models import Settings as Se, User
    today = _d.utcnow().date().isoformat()
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User).all()]
    finally:
        db.close()
    for tid in user_ids:
        prev = context.tid()
        try:
            context.set_tenant(tid)
            db = SessionLocal()
            try:
                s = db.query(Se).filter(Se.tenant_id == tid).first()
                if not s or not getattr(s, "auto_backup", False):
                    continue
                keep = getattr(s, "backup_keep", 7) or 7
            finally:
                db.close()
            if _auto_backup_done.get(tid) == today:
                continue
            _make_auto_backup(tid, keep)
            _auto_backup_done[tid] = today
        except Exception as e:  # noqa: BLE001
            print("Auto-Backup-Prüfung-Fehler:", e)
        finally:
            context.set_tenant(prev)


@app.get("/api/backup/auto/list")
def backup_auto_list():
    """Listet die automatisch erstellten Sicherungen der Firma."""
    from datetime import datetime as _d
    d = _backup_dir(context.tid())
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d), reverse=True):
            full = os.path.join(d, fn)
            if os.path.isfile(full) and fn.endswith(".zip"):
                st = os.stat(full)
                out.append({"name": fn, "size": st.st_size,
                            "created": _d.utcfromtimestamp(st.st_mtime).isoformat()})
    return {"backups": out, "dir": d}


@app.post("/api/backup/auto/now")
def backup_auto_now():
    """Erstellt sofort eine automatische Voll-Sicherung."""
    path = _make_auto_backup(context.tid())
    return {"ok": bool(path), "file": os.path.basename(path) if path else ""}


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


class EmailTask(BaseModel):
    subject: str
    body: str = ""


@app.post("/api/assistant/email-to-task")
def email_to_task(e: EmailTask):
    """Macht aus einer E-Mail eine Einzelaufgabe an die Firma."""
    db = SessionLocal()
    try:
        chef = ensure_seed(db, context.tid())
        context.set_tenant(context.tid())
        orch.send_message(db, sender_kind="user", sender_agent_id=None,
                          recipient_kind="agent", recipient_agent_id=chef.id,
                          subject="Einzelaufgabe (aus E-Mail): " + e.subject,
                          body=e.body or e.subject)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Globale Suche
# --------------------------------------------------------------------------- #
@app.get("/api/search")
def global_search(q: str, limit: int = 8):
    """Durchsucht Projekte, Aufgaben, Nachrichten, Agenten, Regeln & Wissen."""
    from .models import (Project as P, Task as T, Message as Me, Agent as A,
                         Rule as Ru)
    term = (q or "").strip()
    if len(term) < 2:
        return {"results": []}
    like = f"%{term}%"
    t = context.tid()
    out = []
    db = SessionLocal()
    try:
        for p in (db.query(P).filter(P.tenant_id == t)
                  .filter(P.title.ilike(like) | P.description.ilike(like)).limit(limit).all()):
            out.append({"type": "Projekt", "icon": "folder", "id": p.id,
                        "title": p.title, "snippet": (p.description or "")[:160],
                        "view": "projects", "ref": p.id})
        for tk in (db.query(T).filter(T.tenant_id == t)
                   .filter(T.title.ilike(like) | T.description.ilike(like)).limit(limit).all()):
            out.append({"type": "Aufgabe", "icon": "check-square", "id": tk.id,
                        "title": tk.title, "snippet": (tk.description or "")[:160],
                        "view": "projects", "ref": tk.project_id})
        for m in (db.query(Me).filter(Me.tenant_id == t)
                  .filter(Me.subject.ilike(like) | Me.body.ilike(like))
                  .order_by(Me.id.desc()).limit(limit).all()):
            out.append({"type": "Nachricht", "icon": "mail", "id": m.id,
                        "title": m.subject or "(ohne Betreff)", "snippet": (m.body or "")[:160],
                        "view": "inbox", "ref": None})
        for a in (db.query(A).filter(A.tenant_id == t)
                  .filter(A.name.ilike(like) | A.role.ilike(like)).limit(limit).all()):
            out.append({"type": "Agent", "icon": "user", "id": a.id,
                        "title": a.name, "snippet": a.role, "view": "org", "ref": a.id})
        for r in (db.query(Ru).filter(Ru.tenant_id == t)
                  .filter(Ru.title.ilike(like) | Ru.content.ilike(like)).limit(limit).all()):
            out.append({"type": "Regel", "icon": "book", "id": r.id,
                        "title": r.title, "snippet": (r.content or "")[:160],
                        "view": "cookbook", "ref": None})
    finally:
        db.close()
    # Wissensspeicher (semantisch)
    try:
        for h in knowledge.search(term, limit):
            out.append({"type": "Wissen", "icon": "brain", "id": None,
                        "title": h["source"], "snippet": h["snippet"],
                        "view": "knowledge", "ref": None})
    except Exception:  # noqa: BLE001
        pass
    return {"results": out[:40], "query": term}


# --------------------------------------------------------------------------- #
# Metriken / Observability
# --------------------------------------------------------------------------- #
@app.get("/api/metrics")
def metrics(request: Request):
    """Kennzahlen der aktuellen Firma (für Monitoring/Beobachtung)."""
    from datetime import datetime as _d
    from .models import (Agent as A, Project as P, Task as T, Message as Me,
                         Usage as U)
    t = context.tid()
    db = SessionLocal()
    try:
        def cnt(model, *filters):
            q = db.query(model).filter(model.tenant_id == t)
            for f in filters:
                q = q.filter(f)
            return q.count()
        usages = db.query(U).filter(U.tenant_id == t).all()
        tokens_in = sum(u.input_tokens or 0 for u in usages)
        tokens_out = sum(u.output_tokens or 0 for u in usages)
        cost = round(sum(u.cost or 0 for u in usages), 4)
        return {
            "tenant": t,
            "agents": {"total": cnt(A), "working": cnt(A, A.status == "working"),
                       "active": cnt(A, A.status != "fired")},
            "projects": {"total": cnt(P), "active": cnt(P, P.status == "active"),
                         "done": cnt(P, P.status == "done")},
            "tasks": {"total": cnt(T), "done": cnt(T, T.status == "done"),
                      "in_progress": cnt(T, T.status == "in_progress"),
                      "open": cnt(T, T.status == "todo")},
            "messages": cnt(Me),
            "usage": {"calls": len(usages), "tokens_in": tokens_in,
                      "tokens_out": tokens_out, "cost_usd": cost},
            "sessions": len(auth.list_sessions(request.state.user["user_id"]))
            if hasattr(request.state, "user") else 0,
            "time": _d.utcnow().isoformat(),
        }
    finally:
        db.close()


@app.get("/api/metrics/prometheus")
def metrics_prometheus(request: Request):
    """Metriken im Prometheus-Textformat (für Scraper)."""
    from fastapi.responses import PlainTextResponse
    m = metrics(request)
    lines = [
        "# HELP foundryhub_agents_total Anzahl Agenten",
        f'foundryhub_agents_total{{tenant="{m["tenant"]}"}} {m["agents"]["total"]}',
        f'foundryhub_agents_working{{tenant="{m["tenant"]}"}} {m["agents"]["working"]}',
        f'foundryhub_projects_active{{tenant="{m["tenant"]}"}} {m["projects"]["active"]}',
        f'foundryhub_tasks_done{{tenant="{m["tenant"]}"}} {m["tasks"]["done"]}',
        f'foundryhub_tasks_open{{tenant="{m["tenant"]}"}} {m["tasks"]["open"]}',
        f'foundryhub_cost_usd{{tenant="{m["tenant"]}"}} {m["usage"]["cost_usd"]}',
        f'foundryhub_tokens_in{{tenant="{m["tenant"]}"}} {m["usage"]["tokens_in"]}',
        f'foundryhub_tokens_out{{tenant="{m["tenant"]}"}} {m["usage"]["tokens_out"]}',
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Web-UI
# --------------------------------------------------------------------------- #
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
