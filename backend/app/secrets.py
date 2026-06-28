"""Zentrale Auflösung von Zugangsdaten: GUI (Datenbank) ODER .env.

Priorität: in der GUI gesetzter Wert > Umgebungsvariable. So muss nichts in die
.env eingetragen werden – die App erkennt selbst, was konfiguriert ist."""
import os

from . import context
from .config import config
from .database import SessionLocal
from .models import Secret

# Schlüssel, die in der GUI gesetzt werden können
KEYS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAVE_API_KEY",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "SMTP_STARTTLS",
    "IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASS", "IMAP_SSL",
]
# Schlüssel mit geheimem Wert (werden nie zurückgegeben)
SECRET_KEYS = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAVE_API_KEY", "SMTP_PASS", "IMAP_PASS"}


def _db_value(key: str) -> str:
    db = SessionLocal()
    try:
        s = (db.query(Secret)
             .filter(Secret.tenant_id == context.tid(), Secret.key == key).first())
        return (s.value or "").strip() if s else ""
    finally:
        db.close()


def get(key: str, default: str = "") -> str:
    """GUI-Wert, sonst Env/Config-Default."""
    v = _db_value(key)
    if v:
        return v
    env = os.getenv(key)
    if env:
        return env
    return str(getattr(config, key, default) or default)


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, str(default)))
    except (ValueError, TypeError):
        return default


def get_bool(key: str, default: bool) -> bool:
    return get(key, str(default)).lower() in ("1", "true", "yes", "on")


def set_value(key: str, value: str):
    if key not in KEYS:
        return
    db = SessionLocal()
    try:
        s = (db.query(Secret)
             .filter(Secret.tenant_id == context.tid(), Secret.key == key).first())
        if s is None:
            s = Secret(tenant_id=context.tid(), key=key, value=value or "")
            db.add(s)
        else:
            s.value = value or ""
        db.commit()
    finally:
        db.close()


def apply_to_environ():
    """Spiegelt in der GUI gesetzte Werte in os.environ, damit auch Subprozesse
    (z. B. MCP-Server) sie sehen."""
    for k in KEYS:
        v = _db_value(k)
        if v:
            os.environ[k] = v


def source(key: str) -> str:
    """Woher kommt der Wert: 'gui' | 'env' | 'none'."""
    if _db_value(key):
        return "gui"
    if os.getenv(key) or getattr(config, key, ""):
        return "env"
    return "none"


# --------------------------------------------------------------------------- #
# Bequeme Sammel-Accessoren
# --------------------------------------------------------------------------- #
def provider_key(name: str) -> str:
    return {"anthropic": get("ANTHROPIC_API_KEY"),
            "openai": get("OPENAI_API_KEY"),
            "brave": get("BRAVE_API_KEY")}.get(name, "")


def smtp_conf() -> dict:
    return {"host": get("SMTP_HOST"), "port": get_int("SMTP_PORT", 587),
            "user": get("SMTP_USER"), "password": get("SMTP_PASS"),
            "from": get("SMTP_FROM") or get("SMTP_USER"),
            "starttls": get_bool("SMTP_STARTTLS", True)}


def imap_conf() -> dict:
    return {"host": get("IMAP_HOST"), "port": get_int("IMAP_PORT", 993),
            "user": get("IMAP_USER") or get("SMTP_USER"),
            "password": get("IMAP_PASS") or get("SMTP_PASS"),
            "ssl": get_bool("IMAP_SSL", True)}


def status() -> dict:
    """Welche Zugangsdaten sind konfiguriert und woher."""
    out = {}
    for k in KEYS:
        out[k] = {"configured": bool(get(k)), "source": source(k),
                  "secret": k in SECRET_KEYS}
    return out
