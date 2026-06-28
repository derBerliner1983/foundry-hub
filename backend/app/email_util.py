"""E-Mail senden (SMTP) und lesen (IMAP) – nur Standardbibliothek."""
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage

from .config import config


def smtp_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def imap_configured() -> bool:
    return bool(config.IMAP_HOST and config.IMAP_USER and config.IMAP_PASS)


def send_email(to: str, subject: str, body: str) -> dict:
    if not smtp_configured():
        return {"ok": False, "error": "SMTP nicht konfiguriert"}
    if not to:
        return {"ok": False, "error": "Kein Empfänger"}
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body or "")
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
            if config.SMTP_STARTTLS:
                s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASS)
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
    if not imap_configured():
        return {"ok": False, "error": "IMAP nicht konfiguriert", "emails": []}
    try:
        cls = imaplib.IMAP4_SSL if config.IMAP_SSL else imaplib.IMAP4
        M = cls(config.IMAP_HOST, config.IMAP_PORT)
        M.login(config.IMAP_USER, config.IMAP_PASS)
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
