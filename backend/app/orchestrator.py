"""Orchestrator: lässt Agenten in Runden arbeiten und führt ihre Aktionen aus."""
import json
import re

from sqlalchemy import func, or_

from . import context
from . import email_util
from . import mcp_client
from . import providers
from . import workspace
from .config import config
from .models import (
    Agent,
    Decision,
    Event,
    McpServer,
    Message,
    Milestone,
    PendingApproval,
    Rating,
    Rule,
    Settings,
    Skill,
    Task,
)
from .prompts import build_system_prompt
from .roles import ROLES, can_hire, role_title

MAX_ACTIONS_PER_TURN = 6


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def get_settings(db, tenant_id=None) -> Settings:
    t = tenant_id if tenant_id is not None else context.tid()
    s = db.query(Settings).filter(Settings.tenant_id == t).first()
    if not s:
        s = Settings(tenant_id=t)
        db.add(s)
        db.commit()
    return s


def log(db, kind, text, agent_id=None):
    db.add(Event(kind=kind, text=text, agent_id=agent_id))


def maybe_notify(db, kind, subject, body):
    """Schickt – falls aktiviert – eine E-Mail-Benachrichtigung an den Nutzer.
    kind: 'question' | 'overdue'."""
    s = db.get(Settings, 1)
    if not s or not s.email_notifications:
        return
    if kind == "question" and not s.notify_questions:
        return
    if kind == "overdue" and not s.notify_overdue:
        return
    to = s.user_email or config.NOTIFY_EMAIL or config.SMTP_FROM
    if not to or not email_util.smtp_configured():
        return
    try:
        email_util.send_email(to, "[AI-Hub] " + subject, body)
        log(db, "email", f"Benachrichtigung gesendet: {subject}")
    except Exception as e:  # noqa: BLE001
        log(db, "error", f"E-Mail-Fehler: {e}")


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


def rules_for(db, agent: Agent, project_ctx) -> str:
    """Aktive Regeln, die für diesen Agenten gelten (global + Rolle + Projekt)."""
    rules = db.query(Rule).filter(Rule.active == True,  # noqa: E712
                                  Rule.tenant_id == agent.tenant_id).all()
    out = []
    for r in rules:
        if r.scope == "global" \
           or (r.scope == "role" and r.role == agent.role) \
           or (r.scope == "project" and r.project_id == project_ctx):
            out.append(f"  • [{r.title}] {r.content}")
    return "\n".join(out)


def skills_text(db) -> str:
    skills = db.query(Skill).filter(Skill.enabled == True,  # noqa: E712
                                    Skill.tenant_id == context.tid()).all()
    return "\n".join(f"  • {s.name}: {s.description}" for s in skills)


def mcp_text(db) -> str:
    servers = db.query(McpServer).filter(McpServer.enabled == True,  # noqa: E712
                                         McpServer.tenant_id == context.tid()).all()
    lines = []
    for m in servers:
        try:
            tools = json.loads(m.tools_json or "[]")
        except Exception:  # noqa: BLE001
            tools = []
        tnames = ", ".join(t.get("name", "") for t in tools)
        suffix = f" – Tools: {tnames}" if tnames else " (noch nicht verbunden)"
        lines.append(f"  • {m.name} ({m.transport}): {m.description}{suffix}")
    return "\n".join(lines)


def team_summary(db, viewer: Agent) -> str:
    agents = db.query(Agent).filter(Agent.status == "employed",
                                    Agent.tenant_id == viewer.tenant_id).all()
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


async def execute_actions(db, agent: Agent, settings: Settings, parsed: dict,
                          current_task: Task, project_ctx=None):
    actions = parsed.get("actions", [])[:MAX_ACTIONS_PER_TURN]
    last_hired_id = None
    # Projektkontext: Projekt der ausgelösten Nachricht/Aufgabe, sonst eigenes Projekt
    pctx = project_ctx if project_ctx is not None else agent.project_id

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
            subj = act.get("subject", "Rückfrage")
            send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                         recipient_kind="user", recipient_agent_id=None,
                         subject="❓ " + subj,
                         body=act.get("body", ""), project_id=agent.project_id,
                         requires_answer=True)
            maybe_notify(db, "question", f"Rückfrage von {agent.name}: {subj}",
                         act.get("body", ""))

        # ---------- Einstellen ----------
        elif atype == "hire":
            new_id = _do_hire(db, agent, settings, act, pctx)
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
            ms = _find_milestone(db, pctx, {"milestone_id": act.get("milestone_id"),
                                            "title": act.get("milestone", "")})
            t = Task(project_id=pctx, title=act.get("title", "Aufgabe"),
                     description=act.get("description", ""), assigned_agent_id=assign,
                     created_by_agent_id=agent.id, status="todo",
                     milestone_id=ms.id if ms else None)
            db.add(t)
            if ms and ms.status == "planned":
                ms.status = "in_progress"
            log(db, "task", f"Neue Aufgabe '{t.title}' an #{assign}"
                + (f" [Meilenstein: {ms.title}]" if ms else ""), agent_id=agent.id)
            if assign:
                send_message(db, sender_kind="agent", sender_agent_id=agent.id,
                             recipient_kind="agent", recipient_agent_id=assign,
                             subject="Neue Aufgabe: " + t.title,
                             body=t.description, project_id=pctx)

        elif atype == "complete_task":
            tid = act.get("task_id")
            task = current_task if tid in ("current", None) else db.get(Task, _as_int(tid))
            # Regressions-Schutz: Entwickler/QA müssen vorher verifizieren
            if task and settings.require_verification and agent.role in ("developer", "qa") \
                    and not task.verified:
                log(db, "info", f"{agent.name}: Abschluss blockiert – erst verifizieren "
                    f"(Tests/Smoke-Check)", agent_id=agent.id)
                send_message(db, sender_kind="system", sender_agent_id=None,
                             recipient_kind="agent", recipient_agent_id=agent.id,
                             subject="Bitte erst verifizieren",
                             body=f"Bevor '{task.title}' als erledigt gilt: führe mit run_command "
                                  "die Tests/einen Smoke-Check aus und stelle sicher, dass nichts "
                                  "Bestehendes kaputtgeht. Danach erneut abschließen.",
                             project_id=pctx)
                task = None  # nicht abschließen
            if task:
                task.status = "done"
                task.result = act.get("result", "")
                log(db, "task", f"Aufgabe '{task.title}' erledigt", agent_id=agent.id)
                _refresh_milestone_status(db, task.milestone_id, agent.id)
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
                rel = workspace.write_file(pctx, act.get("path", "datei.txt"),
                                           act.get("content", ""))
                log(db, "file", f"Datei geschrieben: {rel}", agent_id=agent.id)
            except Exception as e:  # noqa: BLE001
                log(db, "error", f"Datei-Fehler: {e}", agent_id=agent.id)

        elif atype == "run_command":
            _do_run_command(db, agent, settings, act, current_task, pctx)

        elif atype == "reset_workspace":
            res = workspace.reset_workspace(pctx, act.get("path", ""))
            log(db, "exec", f"Workspace zurückgesetzt ({'ok' if res.get('ok') else res.get('stderr','Fehler')})",
                agent_id=agent.id)

        elif atype == "read_file":
            content = workspace.read_file(pctx, act.get("path", ""))
            log(db, "file", f"Datei gelesen: {act.get('path','')} ({len(content)} Z.)", agent_id=agent.id)
            # Inhalt dem Agenten als Systemnachricht zurückgeben
            send_message(db, sender_kind="system", sender_agent_id=None,
                         recipient_kind="agent", recipient_agent_id=agent.id,
                         subject=f"Inhalt {act.get('path','')}", body=content[:4000])

        # ---------- Cookbook & Skills ----------
        elif atype == "add_rule":
            scope = act.get("scope", "global")
            rule = Rule(title=act.get("title", "Regel"), content=act.get("content", ""),
                        scope=scope if scope in ("global", "role", "project") else "global",
                        role=agent.role if scope == "role" else None,
                        project_id=pctx if scope == "project" else None,
                        source="agent", created_by_agent_id=agent.id, active=True)
            db.add(rule)
            log(db, "rule", f"Neue Regel angelegt: {rule.title}", agent_id=agent.id)

        elif atype == "use_skill":
            _do_use_skill(db, agent, act, current_task, pctx)

        elif atype == "mcp_call":
            await _do_mcp_call(db, agent, act, pctx)

        # ---------- Roadmap / Meilensteine ----------
        elif atype == "add_milestone":
            n = db.query(Milestone).filter(Milestone.project_id == pctx).count()
            ms = Milestone(project_id=pctx, title=act.get("title", "Meilenstein"),
                           description=act.get("description", ""), status="planned",
                           order_index=n, created_by_agent_id=agent.id,
                           due_date=parse_due(act.get("due_days"), act.get("due")))
            db.add(ms)
            frist = f" (Frist {ms.due_date.date()})" if ms.due_date else ""
            log(db, "milestone", f"Meilenstein geplant: {ms.title}{frist}", agent_id=agent.id)

        elif atype == "complete_milestone":
            ms = _find_milestone(db, pctx, act)
            if ms:
                ms.status = "done"
                ms.completed_at = now()
                log(db, "milestone", f"Meilenstein erreicht: {ms.title}", agent_id=agent.id)

        elif atype == "start_milestone":
            ms = _find_milestone(db, pctx, act)
            if ms:
                ms.status = "in_progress"
                log(db, "milestone", f"Meilenstein gestartet: {ms.title}", agent_id=agent.id)

    # Eingehende Aufgabe als in Bearbeitung markieren, falls nichts abgeschlossen
    db.commit()


def now():
    from datetime import datetime
    return datetime.utcnow()


def parse_due(due_days=None, due=None):
    """Wandelt due_days (Zahl) oder due (ISO-Datum 'YYYY-MM-DD') in ein Datum."""
    import datetime
    if due_days is not None:
        try:
            return datetime.datetime.utcnow() + datetime.timedelta(days=float(due_days))
        except (ValueError, TypeError):
            pass
    if due:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y"):
            try:
                return datetime.datetime.strptime(str(due)[:19], fmt)
            except ValueError:
                continue
    return None


def check_overdue(db):
    """Findet überfällige, nicht erledigte Meilensteine und meldet sie EINMAL
    an den/die Verantwortliche(n), damit die KI reagieren kann."""
    import datetime
    now_ = datetime.datetime.utcnow()
    overdue = (db.query(Milestone)
               .filter(Milestone.due_date.isnot(None),
                       Milestone.status != "done",
                       Milestone.tenant_id == context.tid(),
                       Milestone.overdue_notified == False)  # noqa: E712
               .all())
    notified = 0
    for ms in overdue:
        if ms.due_date and ms.due_date < now_:
            ms.overdue_notified = True
            log(db, "deadline", f"⚠️ Meilenstein überfällig: {ms.title} (Frist {ms.due_date.date()})")
            maybe_notify(db, "overdue", f"Meilenstein überfällig: {ms.title}",
                         f"Der Meilenstein '{ms.title}' ist seit {ms.due_date.date()} überfällig.")
            # An die Projektleitung des Projekts melden (sonst an den Chef)
            pm = (db.query(Agent)
                  .filter(Agent.project_id == ms.project_id, Agent.role == "project_manager",
                          Agent.status == "employed").first())
            target = pm or db.query(Agent).filter(Agent.role == "ceo").first()
            if target:
                send_message(db, sender_kind="system", sender_agent_id=None,
                             recipient_kind="agent", recipient_agent_id=target.id,
                             subject="⚠️ Frist überschritten: " + ms.title,
                             body=f"Der Meilenstein '{ms.title}' ist seit {ms.due_date.date()} "
                                  f"überfällig. Bitte priorisieren, Plan anpassen oder den Nutzer informieren.",
                             project_id=ms.project_id)
            notified += 1
    if notified:
        db.commit()
    return notified


def _refresh_milestone_status(db, milestone_id, agent_id=None):
    """Leitet den Meilenstein-Status aus seinen Aufgaben ab:
    alle erledigt -> done; mindestens eine vorhanden -> in_progress."""
    if not milestone_id:
        return
    ms = db.get(Milestone, milestone_id)
    if not ms:
        return
    tasks = db.query(Task).filter(Task.milestone_id == milestone_id).all()
    if not tasks:
        return
    done = sum(1 for t in tasks if t.status == "done")
    if done == len(tasks):
        if ms.status != "done":
            ms.status = "done"
            ms.completed_at = now()
            log(db, "milestone", f"Meilenstein automatisch erreicht: {ms.title}", agent_id=agent_id)
    elif ms.status == "planned":
        ms.status = "in_progress"


def milestone_progress(db, milestone_id):
    """(done, total) der Aufgaben eines Meilensteins."""
    tasks = db.query(Task).filter(Task.milestone_id == milestone_id).all()
    return sum(1 for t in tasks if t.status == "done"), len(tasks)


def _find_milestone(db, pctx, act):
    db.flush()  # in derselben Runde angelegte Meilensteine sichtbar machen
    mid = act.get("milestone_id")
    if mid is not None:
        ms = db.get(Milestone, _as_int(mid))
        if ms:
            return ms
    title = act.get("title", "")
    if title:
        return (db.query(Milestone)
                .filter(Milestone.project_id == pctx, Milestone.title == title).first())
    return None


async def _do_mcp_call(db, agent, act, pctx):
    name = act.get("server", "")
    server = db.query(McpServer).filter(McpServer.name == name,
                                        McpServer.enabled == True).first()  # noqa: E712
    if not server:
        log(db, "error", f"MCP-Server '{name}' nicht gefunden/aktiv", agent_id=agent.id)
        return
    tool = act.get("tool", "")
    args = act.get("arguments", {})
    if not isinstance(args, dict):
        args = {}
    try:
        result = await mcp_client.call_tool(server.transport, tool, args,
                                            command=server.command, url=server.url)
        text = mcp_client.result_to_text(result)[:2000]
        log(db, "mcp", f"{name}.{tool}() → {text[:120]}", agent_id=agent.id)
        send_message(db, sender_kind="system", sender_agent_id=None,
                     recipient_kind="agent", recipient_agent_id=agent.id,
                     subject=f"MCP-Ergebnis {name}.{tool}",
                     body=text, project_id=pctx)
    except Exception as e:  # noqa: BLE001
        log(db, "error", f"MCP-Fehler {name}.{tool}: {e}", agent_id=agent.id)


def _do_use_skill(db, agent, act, current_task, pctx):
    name = act.get("name", "")
    skill = db.query(Skill).filter(Skill.name == name, Skill.enabled == True).first()  # noqa: E712
    if not skill:
        log(db, "error", f"Skill '{name}' nicht gefunden", agent_id=agent.id)
        return
    log(db, "skill", f"Skill genutzt: {name}", agent_id=agent.id)
    # Hat der Skill einen Befehl, wird er (mit {args}) im Workspace ausgeführt
    if skill.command:
        cmd = skill.command.replace("{args}", act.get("args", ""))
        _do_run_command(db, agent, get_settings(db),
                        {"cmd": cmd}, current_task, pctx)
    else:
        # Reine Anweisungs-Skill: Vorgehen dem Agenten zurückspielen
        send_message(db, sender_kind="system", sender_agent_id=None,
                     recipient_kind="agent", recipient_agent_id=agent.id,
                     subject=f"Skill: {name}", body=skill.instructions[:3000])


def _do_run_command(db, agent, settings, act, current_task, pctx=None):
    if pctx is None:
        pctx = agent.project_id
    if not settings.enable_code_exec:
        log(db, "error", "Befehlsausführung gesperrt (Einstellungen)", agent_id=agent.id)
        return
    if current_task and current_task.exec_count >= config.MAX_EXEC_PER_TASK:
        log(db, "error", f"Befehlslimit ({config.MAX_EXEC_PER_TASK}) erreicht", agent_id=agent.id)
        return
    cmd = act.get("cmd") or act.get("command") or ""
    res = workspace.run_command(pctx, cmd)
    if current_task:
        current_task.exec_count = (current_task.exec_count or 0) + 1
        if res["ok"]:  # erfolgreicher Test/Smoke-Check -> Aufgabe gilt als verifiziert
            current_task.verified = True
    status = "ok" if res["ok"] else f"Fehler ({res['code']})"
    out = (res["stdout"] + ("\n" + res["stderr"] if res["stderr"] else ""))[:1500]
    log(db, "exec", f"$ {cmd}  → {status}\n{out}", agent_id=agent.id)
    # Ergebnis dem Agenten zurückspielen, damit er iterieren kann (Cap schützt vor Endlosschleife)
    if not current_task or current_task.exec_count < config.MAX_EXEC_PER_TASK:
        send_message(db, sender_kind="system", sender_agent_id=None,
                     recipient_kind="agent", recipient_agent_id=agent.id,
                     subject=f"Befehlsergebnis ({status})",
                     body=f"$ {cmd}\n{out}", project_id=pctx)


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


def _do_hire(db, agent, settings, act, pctx=None):
    if pctx is None:
        pctx = agent.project_id
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
                                    "manager_id": agent.id, "project_id": pctx}),
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
        maybe_notify(db, "question", "Freigabe nötig: Einstellung", approval.summary)
        return None

    return _create_agent(db, target_role, act.get("name"), provider, model,
                         agent.id, pctx)


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
def _next_agent_to_act(db, tenants):
    """Wählt einen beschäftigten Agenten (aus aktiven Firmen) mit offener Arbeit."""
    if not tenants:
        return None
    # Agenten mit ungelesener Nachricht
    ids = [r[0] for r in db.query(Message.recipient_agent_id)
           .filter(Message.recipient_kind == "agent", Message.is_read == False)  # noqa: E712
           .distinct() if r[0] is not None]
    agent = (
        db.query(Agent)
        .filter(Agent.status == "employed", Agent.stuck == False,  # noqa: E712
                Agent.tenant_id.in_(tenants), Agent.id.in_(ids))
        .order_by(Agent.id)
        .first()
    ) if ids else None
    if agent:
        return agent
    # Agenten mit offener Aufgabe
    task = (
        db.query(Task)
        .filter(Task.status == "todo", Task.assigned_agent_id.isnot(None),
                Task.tenant_id.in_(tenants))
        .order_by(Task.id)
        .first()
    )
    if task:
        a = db.get(Agent, task.assigned_agent_id)
        if a and a.status == "employed" and not a.stuck:
            return a
    return None


async def run_agent_turn(db, agent: Agent):
    context.set_tenant(agent.tenant_id)
    settings = get_settings(db, agent.tenant_id)

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
    project_ctx = agent.project_id
    context_lines = []
    for m in msgs:
        sender = "Nutzer" if m.sender_kind == "user" else (
            f"#{m.sender_agent_id} " + (db.get(Agent, m.sender_agent_id).name if m.sender_agent_id else "")
        )
        context_lines.append(f"NACHRICHT von {sender}: [{m.subject}] {m.body}")
        if m.project_id is not None:
            project_ctx = m.project_id
        m.is_read = True
    for t in tasks:
        context_lines.append(f"OFFENE AUFGABE #{t.id}: [{t.title}] {t.description}")
        if t.status == "todo":
            t.status = "in_progress"
        if t.project_id is not None:
            project_ctx = t.project_id
        current_task = current_task or t

    if not context_lines:
        db.commit()
        return None

    system = build_system_prompt(agent, settings, team_summary(db, agent),
                                 rules_text=rules_for(db, agent, project_ctx),
                                 skills_text=skills_text(db),
                                 mcp_text=mcp_text(db))
    user_msg = "Bearbeite das Folgende und antworte als JSON:\n\n" + "\n".join(context_lines)

    result = await providers.chat(agent.provider, agent.model, system,
                                  [{"role": "user", "content": user_msg}])
    if not result.ok:
        log(db, "error", f"{agent.name}: LLM-Fehler {result.error}", agent_id=agent.id)
        db.commit()
        return None

    parsed = parse_actions(result.text)
    await execute_actions(db, agent, settings, parsed, current_task, project_ctx)

    # Entscheidung protokollieren: warum (thoughts) + was/wie (Aktionen) + Auslöser
    summary = _summarize_actions(parsed.get("actions", []))
    db.add(Decision(agent_id=agent.id, project_id=project_ctx,
                    thoughts=(parsed.get("thoughts", "") or "")[:2000],
                    actions_summary=summary[:2000],
                    trigger=" | ".join(context_lines)[:1000]))
    db.commit()
    _check_loop(db, agent)
    return {"agent": agent.name, "provider": result.provider,
            "thoughts": parsed.get("thoughts", ""), "actions": parsed.get("actions", [])}


LOOP_THRESHOLD = 3  # so oft dieselbe Aktion hintereinander = Schleife


def _check_loop(db, agent: Agent):
    """Erkennt, wenn ein Agent immer wieder dasselbe tut, und stoppt ihn."""
    recent = (db.query(Decision)
              .filter(Decision.agent_id == agent.id)
              .order_by(Decision.id.desc())
              .limit(LOOP_THRESHOLD).all())
    if len(recent) < LOOP_THRESHOLD:
        return
    sigs = {(r.actions_summary or "").strip() for r in recent}
    if len(sigs) == 1:  # alle identisch -> Schleife
        agent.stuck = True
        log(db, "loop", f"{agent.name} hängt in einer Schleife "
            f"('{recent[0].actions_summary[:60]}') – automatisch gestoppt.", agent_id=agent.id)
        # Vorgesetzten bzw. Nutzer informieren
        if agent.manager_id:
            send_message(db, sender_kind="system", sender_agent_id=None,
                         recipient_kind="agent", recipient_agent_id=agent.manager_id,
                         subject=f"⚠️ {agent.name} steckt fest",
                         body=f"{agent.name} wiederholt dieselbe Aktion und wurde gestoppt. "
                              f"Bitte Aufgabe klären, neu zuweisen oder ersetzen.",
                         project_id=agent.project_id)
        else:
            send_message(db, sender_kind="system", sender_agent_id=None,
                         recipient_kind="user", recipient_agent_id=None,
                         subject=f"⚠️ {agent.name} steckt in einer Schleife",
                         body="Der Agent wurde automatisch gestoppt. Du kannst ihn nach einer "
                              "Klärung wieder fortsetzen.", requires_answer=True)
            maybe_notify(db, "question", f"{agent.name} steckt fest", "Automatisch gestoppt.")
        db.commit()


def _summarize_actions(actions) -> str:
    labels = []
    for a in actions:
        t = a.get("type", "?")
        if t == "message":
            labels.append(f"Nachricht an {a.get('to')}")
        elif t == "ask_user":
            labels.append("Rückfrage an Nutzer")
        elif t == "hire":
            labels.append(f"stellt {a.get('role','?')} ein ({a.get('name','')})")
        elif t == "fire":
            labels.append(f"kündigt #{a.get('agent_id')}")
        elif t == "create_task":
            labels.append(f"Aufgabe: {a.get('title','')}")
        elif t == "complete_task":
            labels.append("Aufgabe abgeschlossen")
        elif t == "rate":
            labels.append(f"bewertet #{a.get('agent_id')} ({a.get('score')})")
        elif t == "write_file":
            labels.append(f"Datei: {a.get('path','')}")
        elif t == "run_command":
            labels.append(f"Befehl: {a.get('cmd', a.get('command',''))}")
        elif t == "mcp_call":
            labels.append(f"MCP {a.get('server')}.{a.get('tool')}")
        elif t == "add_rule":
            labels.append(f"Regel: {a.get('title','')}")
        elif t == "add_milestone":
            labels.append(f"Meilenstein: {a.get('title','')}")
        elif t in ("complete_milestone", "start_milestone"):
            labels.append(f"{t}: {a.get('title', a.get('milestone_id',''))}")
        else:
            labels.append(t)
    return " · ".join(labels) if labels else "(keine Aktion)"


def within_schedule(settings) -> bool:
    """Prüft, ob die KI laut Zeitplan gerade arbeiten darf."""
    import datetime
    mode = settings.schedule_mode or "always"
    if mode == "manual":
        return False
    if mode == "window":
        h = datetime.datetime.now().hour
        f, t = settings.active_from or 0, settings.active_to if settings.active_to is not None else 24
        if f <= t:
            return f <= h < t
        return h >= f or h < t  # über Mitternacht
    return True  # always


def _active_tenants(db, force=False, only_tenant=None) -> list:
    """Firmen, deren KI gerade arbeiten darf (auto_run + Zeitplan)."""
    q = db.query(Settings)
    if only_tenant is not None:
        q = q.filter(Settings.tenant_id == only_tenant)
    out = []
    for s in q.all():
        if force or (s.auto_run and within_schedule(s)):
            out.append(s.tenant_id)
    return out


async def tick(db, force=False, only_tenant=None):
    """Eine Arbeitseinheit über alle aktiven Firmen (oder nur only_tenant).
    force=True ignoriert den Zeitplan (für 'Jetzt prüfen')."""
    tenants = _active_tenants(db, force=force, only_tenant=only_tenant)
    if not tenants:
        return None
    for t in tenants:  # überfällige Meilensteine je Firma melden
        context.set_tenant(t)
        check_overdue(db)
    agent = _next_agent_to_act(db, tenants)
    if not agent:
        return None
    return await run_agent_turn(db, agent)
