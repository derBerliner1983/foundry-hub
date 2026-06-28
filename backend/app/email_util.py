"""E-Mail senden (SMTP) und lesen (IMAP) – nur Standardbibliothek."""
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage

from . import secrets


def smtp_configured() -> bool:
    c = secrets.smtp_conf()
    return bool(c["host"] and c["from"])


def imap_configured() -> bool:
    c = secrets.imap_conf()
    return bool(c["host"] and c["user"] and c["password"])


def send_email(to: str, subject: str, body: str) -> dict:
    c = secrets.smtp_conf()
    if not (c["host"] and c["from"]):
        return {"ok": False, "error": "SMTP nicht konfiguriert"}
    if not to:
        return {"ok": False, "error": "Kein Empfänger"}
    msg = EmailMessage()
    msg["From"] = c["from"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body or "")
    try:
        with smtplib.SMTP(c["host"], c["port"], timeout=30) as s:
            if c["starttls"]:
                s.starttls()
            if c["user"]:
                s.login(c["user"], c["password"])
            s.send_message(msg)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return str(value)


def _body_text(msg) -> str:
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    return ""


def fetch_recent(limit: int = 10) -> dict:
    """Liest die neuesten E-Mails aus der INBOX."""
    c = secrets.imap_conf()
    if not (c["host"] and c["user"] and c["password"]):
        return {"ok": False, "error": "IMAP nicht konfiguriert", "emails": []}
    try:
        cls = imaplib.IMAP4_SSL if c["ssl"] else imaplib.IMAP4
        M = cls(c["host"], c["port"])
        M.login(c["user"], c["password"])
        M.select("INBOX")
        typ, data = M.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-limit:][::-1]  # neueste zuerst
        out = []
        for num in ids:
            typ, msg_data = M.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            body = _body_text(msg)
            out.append({
                "from": _decode(msg.get("From")),
                "subject": _decode(msg.get("Subject")),
                "date": _decode(msg.get("Date")),
                "snippet": " ".join(body.split())[:300],
                "body": body[:4000],
            })
        M.logout()
        return {"ok": True, "emails": out}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "emails": []}
