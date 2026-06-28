"""Daily-Assistant – persönlicher KI-Assistent für die tägliche Arbeit.

Getrennt von der Projekt-Firma. Kann (mit Erlaubnis) die E-Mails des Nutzers
lesen, zusammenfassen und beim Verfassen/Versenden helfen – und größere Vorhaben
als Projekt oder Einzelaufgabe an die Firma delegieren."""
import json
import re

from . import email_util
from . import providers
from .models import Agent, Project, Settings

SYSTEM = (
    "Du bist der persönliche Daily-Assistant des Nutzers (nicht Teil der Projekt-Firma). "
    "Du nimmst dem Nutzer Arbeit ab: E-Mails zusammenfassen/beantworten, To-dos, "
    "Recherche-Notizen, kurze Texte. Größere oder mehrstufige Vorhaben ('mein Projekt') "
    "delegierst du an die Firma (an den Chef), kleine Einzelaufträge ebenfalls.\n\n"
    "Antworte als JSON:\n"
    '{"reply":"kurze Antwort an den Nutzer","actions":[ ... ]}\n'
    "Mögliche actions (nur wenn sinnvoll, sonst leer):\n"
    '- {"type":"create_project","title":"...","description":"..."}  (größeres Vorhaben an die Firma)\n'
    '- {"type":"create_task","title":"...","description":"..."}     (kleine Einzelaufgabe an die Firma)\n'
    '- {"type":"send_email","to":"...","subject":"...","body":"..."}\n'
    "Wenn keine Aktion nötig ist, gib actions als leere Liste zurück und antworte direkt."
)


def _model(db):
    s = db.get(Settings, 1)
    if s:
        return s.default_worker_provider, s.default_worker_model
    return "claude", "claude-sonnet-4-6"


def _email_access(db) -> bool:
    s = db.get(Settings, 1)
    return bool(s and s.assistant_email_access)


def _emails_context(db, limit=10) -> str:
    if not _email_access(db):
        return ""
    res = email_util.fetch_recent(limit)
    if not res.get("ok"):
        return ""
    lines = []
    for i, m in enumerate(res["emails"], 1):
        lines.append(f"{i}. Von: {m['from']} | Betreff: {m['subject']} | {m['date']}\n   {m['snippet']}")
    return "\n".join(lines)


async def summarize(db, limit=10) -> dict:
    if not _email_access(db):
        return {"ok": False, "error": "Kein E-Mail-Zugang aktiviert (Einstellungen)."}
    res = email_util.fetch_recent(limit)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "IMAP-Fehler")}
    emails = res["emails"]
    if not emails:
        return {"ok": True, "summary": "Keine E-Mails gefunden.", "count": 0}
    ctx = "\n\n".join(
        f"E-Mail {i}:\nVon: {m['from']}\nBetreff: {m['subject']}\nDatum: {m['date']}\n{m['body']}"
        for i, m in enumerate(emails, 1))
    provider, model = _model(db)
    prompt = ("Fasse die folgenden E-Mails kurz zusammen. Pro E-Mail eine Zeile mit "
              "Absender, Kernaussage und – falls nötig – empfohlener Aktion. Hebe Dringendes hervor.\n\n" + ctx)
    result = await providers.chat(provider, model, SYSTEM, [{"role": "user", "content": prompt}])
    return {"ok": True, "summary": result.text, "count": len(emails)}


def _execute_actions(db, actions: list) -> list:
    """Führt Assistenten-Aktionen aus (Delegation an die Firma, E-Mail)."""
    from . import orchestrator as orch
    chef = db.query(Agent).filter_by(role="ceo").first()
    done = []
    for a in actions[:5]:
        t = a.get("type")
        if t == "create_project" and chef:
            p = Project(title=a.get("title", "Projekt"), description=a.get("description", ""))
            db.add(p); db.flush()
            orch.send_message(db, sender_kind="user", sender_agent_id=None,
                              recipient_kind="agent", recipient_agent_id=chef.id,
                              subject="Neues Projekt: " + p.title,
                              body=a.get("description", "") or p.title, project_id=p.id)
            done.append(f"Projekt '{p.title}' an die Firma übergeben")
        elif t == "create_task" and chef:
            orch.send_message(db, sender_kind="user", sender_agent_id=None,
                              recipient_kind="agent", recipient_agent_id=chef.id,
                              subject="Einzelaufgabe: " + a.get("title", "Aufgabe"),
                              body=(a.get("description", "") or a.get("title", "")) +
                                   "\n\n(Einzelaufgabe – kein volles Projekt nötig.)")
            done.append(f"Einzelaufgabe '{a.get('title','')}' an die Firma übergeben")
        elif t == "send_email":
            res = email_util.send_email(a.get("to", ""), a.get("subject", ""), a.get("body", ""))
            done.append(("E-Mail gesendet an " + a.get("to", "")) if res.get("ok")
                        else "E-Mail-Fehler: " + res.get("error", ""))
    if done:
        db.commit()
    return done


async def chat(db, message: str) -> dict:
    provider, model = _model(db)
    ctx = _emails_context(db)
    user = message
    if ctx:
        user = (f"Aktuelle E-Mails (Kontext):\n{ctx}\n\n"
                f"Frage/Auftrag des Nutzers: {message}")
    result = await providers.chat(provider, model, SYSTEM, [{"role": "user", "content": user}])

    reply, actions = result.text, []
    m = re.search(r"\{.*\}", result.text or "", re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "reply" in data:
                reply = data.get("reply", "")
                actions = data.get("actions", []) or []
        except Exception:  # noqa: BLE001
            pass
    done = _execute_actions(db, actions) if actions else []
    return {"ok": True, "reply": reply, "done": done, "email_access": _email_access(db)}
