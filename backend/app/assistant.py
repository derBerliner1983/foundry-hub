"""Daily-Assistant – persönlicher KI-Assistent für die tägliche Arbeit.

Getrennt von der Projekt-Firma. Kann (mit Erlaubnis) die E-Mails des Nutzers
lesen, zusammenfassen und beim Verfassen/Versenden helfen."""
from . import email_util
from . import providers
from .models import Settings

SYSTEM = (
    "Du bist der persönliche Daily-Assistant des Nutzers (nicht Teil der Projekt-Firma). "
    "Du hilfst bei der täglichen Arbeit: E-Mails zusammenfassen, einordnen, Antworten "
    "vorschlagen, To-dos ableiten. Antworte knapp, hilfreich und auf Deutsch."
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


async def chat(db, message: str) -> dict:
    provider, model = _model(db)
    ctx = _emails_context(db)
    user = message
    if ctx:
        user = (f"Aktuelle E-Mails (Kontext):\n{ctx}\n\n"
                f"Frage/Auftrag des Nutzers: {message}")
    result = await providers.chat(provider, model, SYSTEM, [{"role": "user", "content": user}])
    return {"ok": True, "reply": result.text, "email_access": _email_access(db)}
