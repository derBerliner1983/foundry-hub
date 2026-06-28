"""Orchestrator: lässt Agenten in Runden arbeiten und führt ihre Aktionen aus."""
import json
import re

from sqlalchemy import func, or_

from . import providers
from . import workspace
from .config import config
from .models import (
    Agent,
    Event,
    Message,
    PendingApproval,
    Rating,
    Settings,
    Task,
)
from .prompts import build_system_prompt
from .roles import ROLES, can_hire, role_title

MAX_ACTIONS_PER_TURN = 6


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def get_settings(db) -> Settings:
    s = db.get(Settings, 1)
    if not s:
        s = Settings(id=1)
        db.add(s)
        db.commit()
    return s


def log(db, kind, text, agent_id=None):
    db.add(Event(kind=kind, text=text, agent_id=agent_id))


def send_message(db, *, sender_kind, sender_agent_id, recipient_kind,
                 recipient_agent_id, subject, body, project_id=None,
                 requires_answer=False):
    msg = Message(
        sender_kind=sender_kind,
        sender_agent_id=sender_agent_id,
        recipient_kind=recipient_kind,
        recipient_agent_id=recipient_agent_id,
        subject=subject or "",
        body=body or "",
        project_id=project_id,
        requires_answer=requires_answer,
    )
    db.add(msg)
    log(db, "message", f"{subject}: {body[:80]}", agent_id=sender_agent_id)
    return msg


def avg_rating(db, agent_id):
    val = db.query(func.avg(Rating.score)).filter(Rating.ratee_agent_id == agent_id).scalar()
    return round(val, 2) if val is not None else None


def team_summary(db, viewer: Agent) -> str:
    agents = db.query(Agent).filter(Agent.status == "employed").all()
    lines = []
    for a in agents:
        if a.id == viewer.id:
            continue
        rel = ""
        if a.manager_id == viewer.id:
            rel = " [dein Mitarbeiter]"
        elif viewer.manager_id == a.id:
            rel = " [dein Vorgesetzter]"
        r = avg_rating(db, a.id)
        rtxt = f", Bewertung {r}" if r is not None else ""
        lines.append(f"  #{a.id} {a.name} – {role_title(a.role)} ({a.provider}/{a.model}{rtxt}){rel}")
    return "\n".join(lines) if lines else "  (noch keine weiteren Mitarbeiter)"


# --------------------------------------------------------------------------- #
# JSON-Parsing der Modellantwort
# --------------------------------------------------------------------------- #
def parse_actions(text: str) -> dict:
    if not text:
        return {"thoughts": "", "actions": []}
    # JSON-Block extrahieren (auch wenn Modell drumherum schreibt)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    raw = m.group(0) if m else text
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "actions" in data:
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"thoughts": text[:200], "actions": []}


# --------------------------------------------------------------------------- #
# Aktionen ausführen
# --------------------------------------------------------------------------- #
def _resolve_model(settings, role, provider, model):
    if not provider:
        provider = settings.default_chef_provider if role == "ceo" else settings.default_worker_provider
    if not model:
        model = settings.default_chef_model if role == "ceo" else settings.default_worker_model
    return provider, model


def execute_actions(db, agent: Agent, settings: Settings, parsed: dict, current_task: Task):
    actions = parsed.get("actions", [])[:MAX_ACTIONS_PER_TURN]
    last_hired_id = None

    for act in actions:
        atype = act.get("type")

        # ---------- Nachrichten ----------
        if atype == "message":
            to = act.get("to")
            rk, rid = _resolve_recipient(agent, to)
            send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                         recipient_kind=rk, recipient_agent_id=rid,
                         subject=act.get("subject", ""), body=act.get("body", ""),
                         project_id=agent.project_id)

        elif atype == "ask_user":
            send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                         recipient_kind="user", recipient_agent_id=None,
                         subject="❓ " + act.get("subject", "Rückfrage"),
                         body=act.get("body", ""), project_id=agent.project_id,
                         requires_answer=True)

        # ---------- Einstellen ----------
        elif atype == "hire":
            new_id = _do_hire(db, agent, settings, act)
            if new_id:
                last_hired_id = new_id

        # ---------- Kündigen ----------
        elif atype == "fire":
            _do_fire(db, agent, settings, act)

        elif atype == "resign":
            agent.status = "resigned"
            log(db, "resign", f"{agent.name} hat gekündigt: {act.get('reason','')}", agent_id=agent.id)
            if agent.manager_id:
                send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                             recipient_kind="agent", recipient_agent_id=agent.manager_id,
                             subject="Kündigung", body=act.get("reason", ""))
            else:
                send_message(db, sender_kind="system", sender_agent_id=None,
                             recipient_kind="user", recipient_agent_id=None,
                             subject="Chef hat gekündigt",
                             body=f"{agent.name}: {act.get('reason','')}")

        # ---------- Aufgaben ----------
        elif atype == "create_task":
            assign = act.get("assign_to")
            if assign == "last_hired":
                assign = last_hired_id
            try:
                assign = int(assign) if assign is not None else None
            except (ValueError, TypeError):
                assign = None
            # Fallback: neuestem beschäftigten Teammitglied zuweisen
            if assign is None:
                newest = (db.query(Agent)
                          .filter(Agent.manager_id == agent.id, Agent.status == "employed")
                          .order_by(Agent.id.desc()).first())
                assign = newest.id if newest else None
            t = Task(project_id=agent.project_id, title=act.get("title", "Aufgabe"),
                     description=act.get("description", ""), assigned_agent_id=assign,
                     created_by_agent_id=agent.id, status="todo")
            db.add(t)
            log(db, "task", f"Neue Aufgabe '{t.title}' an #{assign}", agent_id=agent.id)
            if assign:
                send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                             recipient_kind="agent", recipient_agent_id=assign,
                             subject="Neue Aufgabe: " + t.title,
                             body=t.description, project_id=agent.project_id)

        elif atype == "complete_task":
            tid = act.get("task_id")
            task = current_task if tid in ("current", None) else db.get(Task, _as_int(tid))
            if task:
                task.status = "done"
                task.result = act.get("result", "")
                log(db, "task", f"Aufgabe '{task.title}' erledigt", agent_id=agent.id)
                if task.created_by_agent_id and task.created_by_agent_id != agent.id:
                    send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                                 recipient_kind="agent", recipient_agent_id=task.created_by_agent_id,
                                 subject="Erledigt: " + task.title,
                                 body=task.result, project_id=agent.project_id)

        # ---------- Bewerten ----------
        elif atype == "rate":
            ratee = _as_int(act.get("agent_id"))
            score = max(1, min(5, _as_int(act.get("score"), 3)))
            db.add(Rating(ratee_agent_id=ratee, rater_kind="agent",
                          rater_agent_id=agent.id, score=score,
                          feedback=act.get("feedback", "")))
            log(db, "rating", f"#{ratee} mit {score}/5 bewertet", agent_id=agent.id)
            _maybe_auto_fire(db, agent, settings, ratee)

        # ---------- Code-Werkstatt ----------
        elif atype == "write_file":
            if not settings.enable_code_exec:
                log(db, "error", "Datei schreiben gesperrt (Einstellungen)", agent_id=agent.id)
                continue
            try:
                rel = workspace.write_file(agent.project_id, act.get("path", "datei.txt"),
                                           act.get("content", ""))
                log(db, "file", f"Datei geschrieben: {rel}", agent_id=agent.id)
            except Exception as e:  # noqa: BLE001
                log(db, "error", f"Datei-Fehler: {e}", agent_id=agent.id)

        elif atype == "run_command":
            _do_run_command(db, agent, settings, act, current_task)

        elif atype == "read_file":
            content = workspace.read_file(agent.project_id, act.get("path", ""))
            log(db, "file", f"Datei gelesen: {act.get('path','')} ({len(content)} Z.)", agent_id=agent.id)
            # Inhalt dem Agenten als Systemnachricht zurückgeben
            send_message(db, sender_kind="system", sender_agent_id=None,
                         recipient_kind="agent", recipient_agent_id=agent.id,
                         subject=f"Inhalt {act.get('path','')}", body=content[:4000])

    # Eingehende Aufgabe als in Bearbeitung markieren, falls nichts abgeschlossen
    db.commit()


def _do_run_command(db, agent, settings, act, current_task):
    if not settings.enable_code_exec:
        log(db, "error", "Befehlsausführung gesperrt (Einstellungen)", agent_id=agent.id)
        return
    if current_task and current_task.exec_count >= config.MAX_EXEC_PER_TASK:
        log(db, "error", f"Befehlslimit ({config.MAX_EXEC_PER_TASK}) erreicht", agent_id=agent.id)
        return
    cmd = act.get("cmd") or act.get("command") or ""
    res = workspace.run_command(agent.project_id, cmd)
    if current_task:
        current_task.exec_count = (current_task.exec_count or 0) + 1
    status = "ok" if res["ok"] else f"Fehler ({res['code']})"
    out = (res["stdout"] + ("\n" + res["stderr"] if res["stderr"] else ""))[:1500]
    log(db, "exec", f"$ {cmd}  → {status}\n{out}", agent_id=agent.id)
    # Ergebnis dem Agenten zurückspielen, damit er iterieren kann (Cap schützt vor Endlosschleife)
    if not current_task or current_task.exec_count < config.MAX_EXEC_PER_TASK:
        send_message(db, sender_kind="system", sender_agent_id=None,
                     recipient_kind="agent", recipient_agent_id=agent.id,
                     subject=f"Befehlsergebnis ({status})",
                     body=f"$ {cmd}\n{out}", project_id=agent.project_id)


def _resolve_recipient(agent, to):
    if to in ("user", None):
        return "user", None
    if to == "manager":
        if agent.manager_id:
            return "agent", agent.manager_id
        return "user", None
    return "agent", _as_int(to)


def _as_int(v, default=None):
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _do_hire(db, agent, settings, act):
    target_role = act.get("role", "")
    if not can_hire(agent.role, target_role):
        log(db, "error", f"{agent.name} darf Rolle '{target_role}' nicht einstellen", agent_id=agent.id)
        return None
    if db.query(Agent).filter(Agent.status == "employed").count() >= config.MAX_AGENTS:
        log(db, "error", "Maximale Mitarbeiterzahl erreicht", agent_id=agent.id)
        return None

    provider, model = _resolve_model(settings, target_role, act.get("provider"), act.get("model"))
    if provider not in settings.allowed_providers.split(","):
        provider, model = _resolve_model(settings, target_role, None, None)

    # Freigabe nötig?
    if settings.require_approval_hire and settings.autonomy_level != "full":
        approval = PendingApproval(
            action_json=json.dumps({"type": "hire", "role": target_role,
                                    "name": act.get("name", role_title(target_role)),
                                    "provider": provider, "model": model,
                                    "manager_id": agent.id, "project_id": agent.project_id}),
            requested_by_agent_id=agent.id,
            summary=f"{agent.name} möchte {role_title(target_role)} einstellen ({act.get('name','')})",
        )
        db.add(approval)
        log(db, "hire", f"Freigabe angefragt: {approval.summary}", agent_id=agent.id)
        send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                     recipient_kind="user", recipient_agent_id=None,
                     subject="🔐 Freigabe: Einstellung",
                     body=approval.summary + " – bitte in den Freigaben bestätigen.",
                     requires_answer=True)
        return None

    return _create_agent(db, target_role, act.get("name"), provider, model,
                         agent.id, agent.project_id)


def _create_agent(db, role, name, provider, model, manager_id, project_id):
    a = Agent(name=name or role_title(role), role=role, title=role_title(role),
              provider=provider, model=model, status="employed",
              manager_id=manager_id, project_id=project_id)
    db.add(a)
    db.flush()
    log(db, "hire", f"{a.name} ({role_title(role)}) eingestellt – {provider}/{model}", agent_id=a.id)
    # Begrüßung / Auftrag an den neuen Mitarbeiter
    send_message(db, sender_kind="agent", sender_agent_id=manager_id,
                 recipient_kind="agent", recipient_agent_id=a.id,
                 subject="Willkommen im Team",
                 body="Du bist eingestellt. Bitte verschaffe dir einen Überblick und lege los.",
                 project_id=project_id)
    return a.id


def _do_fire(db, agent, settings, act):
    target = db.get(Agent, _as_int(act.get("agent_id")))
    if not target or target.status != "employed":
        return
    if target.manager_id != agent.id and agent.role != "ceo":
        log(db, "error", f"{agent.name} darf #{target.id} nicht kündigen", agent_id=agent.id)
        return
    if settings.require_approval_fire and settings.autonomy_level != "full":
        approval = PendingApproval(
            action_json=json.dumps({"type": "fire", "agent_id": target.id}),
            requested_by_agent_id=agent.id,
            summary=f"{agent.name} möchte {target.name} kündigen",
        )
        db.add(approval)
        send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                     recipient_kind="user", recipient_agent_id=None,
                     subject="🔐 Freigabe: Kündigung", body=approval.summary,
                     requires_answer=True)
        return
    target.status = "fired"
    log(db, "fire", f"{target.name} gekündigt: {act.get('reason','')}", agent_id=target.id)


def _maybe_auto_fire(db, agent, settings, ratee_id):
    """Manager darf bei dauerhaft schlechter Bewertung kündigen (Hinweis-Log)."""
    avg = avg_rating(db, ratee_id)
    count = db.query(Rating).filter(Rating.ratee_agent_id == ratee_id).count()
    if avg is not None and count >= 2 and avg <= settings.fire_threshold:
        log(db, "info", f"#{ratee_id} unter Bewertungsschwelle ({avg}). Kündigung möglich.", agent_id=ratee_id)


# --------------------------------------------------------------------------- #
# Eine Runde (Tick)
# --------------------------------------------------------------------------- #
def _next_agent_to_act(db):
    """Wählt einen beschäftigten Agenten mit offener Arbeit (Nachricht oder Aufgabe)."""
    # Agenten mit ungelesener Nachricht
    sub = (
        db.query(Message.recipient_agent_id)
        .filter(Message.recipient_kind == "agent", Message.is_read == False)  # noqa: E712
        .subquery()
    )
    agent = (
        db.query(Agent)
        .filter(Agent.status == "employed", Agent.id.in_(sub))
        .order_by(Agent.id)
        .first()
    )
    if agent:
        return agent
    # Agenten mit offener Aufgabe
    task = (
        db.query(Task)
        .filter(Task.status == "todo", Task.assigned_agent_id.isnot(None))
        .order_by(Task.id)
        .first()
    )
    if task:
        a = db.get(Agent, task.assigned_agent_id)
        if a and a.status == "employed":
            return a
    return None


async def run_agent_turn(db, agent: Agent):
    settings = get_settings(db)

    # Kontext sammeln: ungelesene Nachrichten + offene Aufgaben
    msgs = (
        db.query(Message)
        .filter(Message.recipient_kind == "agent",
                Message.recipient_agent_id == agent.id,
                Message.is_read == False)  # noqa: E712
        .order_by(Message.created_at)
        .all()
    )
    tasks = (
        db.query(Task)
        .filter(Task.assigned_agent_id == agent.id, Task.status.in_(["todo", "in_progress"]))
        .order_by(Task.id)
        .all()
    )

    current_task = None
    context_lines = []
    for m in msgs:
        sender = "Nutzer" if m.sender_kind == "user" else (
            f"#{m.sender_agent_id} " + (db.get(Agent, m.sender_agent_id).name if m.sender_agent_id else "")
        )
        context_lines.append(f"NACHRICHT von {sender}: [{m.subject}] {m.body}")
        m.is_read = True
    for t in tasks:
        context_lines.append(f"OFFENE AUFGABE #{t.id}: [{t.title}] {t.description}")
        if t.status == "todo":
            t.status = "in_progress"
        current_task = current_task or t

    if not context_lines:
        db.commit()
        return None

    system = build_system_prompt(agent, settings, team_summary(db, agent))
    user_msg = "Bearbeite das Folgende und antworte als JSON:\n\n" + "\n".join(context_lines)

    result = await providers.chat(agent.provider, agent.model, system,
                                  [{"role": "user", "content": user_msg}])
    if not result.ok:
        log(db, "error", f"{agent.name}: LLM-Fehler {result.error}", agent_id=agent.id)
        db.commit()
        return None

    parsed = parse_actions(result.text)
    execute_actions(db, agent, settings, parsed, current_task)
    return {"agent": agent.name, "provider": result.provider,
            "thoughts": parsed.get("thoughts", ""), "actions": parsed.get("actions", [])}


async def tick(db):
    """Eine Arbeitseinheit. Gibt zurück, was passiert ist (oder None)."""
    settings = get_settings(db)
    if not settings.auto_run:
        return None
    agent = _next_agent_to_act(db)
    if not agent:
        return None
    return await run_agent_turn(db, agent)
