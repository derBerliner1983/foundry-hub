"""Authentifizierung: Benutzer, Passwörter (scrypt), Sitzungen (Cookie),
Tenant-Zugriff (eigene Firma + geteilte)."""
import base64
import hashlib
import hmac
import os
import secrets as pysecrets  # stdlib (nicht das App-Modul)
import struct
import time
from datetime import datetime, timedelta

from .database import SessionLocal
from .models import Access, Session as DBSession, User

COOKIE = "aihub_session"
SESSION_DAYS = 30
MAX_FAILS = 5          # Fehlversuche bis zur Sperre
LOCKOUT_MINUTES = 15   # Sperrdauer

# In-Memory Fehlversuchs-Tracker je Benutzer (reicht für Einzelprozess)
_fails: dict = {}


def _is_locked(username: str) -> bool:
    now = datetime.utcnow()
    times = [t for t in _fails.get(username, []) if (now - t).total_seconds() < LOCKOUT_MINUTES * 60]
    _fails[username] = times
    return len(times) >= MAX_FAILS


def _record_fail(username: str):
    _fails.setdefault(username, []).append(datetime.utcnow())


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = pysecrets.token_hex(16)
    dk = hashlib.scrypt(password.encode(), salt=salt.encode(),
                        n=16384, r=8, p=1, dklen=32)
    return dk.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    dk, _ = hash_password(password, salt)
    return pysecrets.compare_digest(dk, expected_hash)


def has_users() -> bool:
    db = SessionLocal()
    try:
        return db.query(User).count() > 0
    finally:
        db.close()


def create_user(username: str, password: str, is_owner: bool = False):
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            return None, "Benutzername bereits vergeben"
        ph, salt = hash_password(password)
        u = User(username=username, password_hash=ph, salt=salt, is_owner=is_owner)
        db.add(u)
        db.commit()
        return u.id, None
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 2FA (TOTP, RFC 6238)
# --------------------------------------------------------------------------- #
def gen_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _totp(secret: str, t: float) -> str:
    pad = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret + pad, casefold=True)
    msg = struct.pack(">Q", int(t // 30))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def totp_verify(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    now = time.time()
    return any(_totp(secret, now + d) == str(code).strip().zfill(6) for d in (-30, 0, 30))


def otpauth_uri(username: str, secret: str) -> str:
    return f"otpauth://totp/AI-Hub:{username}?secret={secret}&issuer=AI-Hub"


def login(username: str, password: str, code: str = None,
          user_agent: str = "", ip: str = ""):
    """Gibt (token, error) zurück. error: None | 'locked' | 'invalid' | '2fa'."""
    if _is_locked(username):
        return None, "locked"
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if not u or not verify_password(password, u.salt, u.password_hash):
            _record_fail(username)
            return None, "invalid"
        if u.totp_enabled and not totp_verify(u.totp_secret, code):
            return None, "2fa"
        _fails.pop(username, None)
        token = pysecrets.token_urlsafe(32)
        db.add(DBSession(token=token, user_id=u.id, active_tenant_id=u.id,
                         expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
                         user_agent=(user_agent or "")[:300], ip=(ip or "")[:64]))
        db.commit()
        return token, None
    finally:
        db.close()


def list_sessions(user_id: int, current_token: str = "") -> list:
    """Aktive Sitzungen eines Nutzers (für die Sitzungsverwaltung)."""
    db = SessionLocal()
    try:
        out = []
        for s in (db.query(DBSession).filter(DBSession.user_id == user_id)
                  .order_by(DBSession.created_at.desc()).all()):
            out.append({
                "id": s.token[:12],
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "user_agent": s.user_agent or "",
                "ip": s.ip or "",
                "current": s.token == current_token,
            })
        return out
    finally:
        db.close()


def revoke_session(user_id: int, session_id: str) -> bool:
    """Beendet eine bestimmte Sitzung (per Kurz-ID = erste 12 Zeichen)."""
    db = SessionLocal()
    try:
        for s in db.query(DBSession).filter(DBSession.user_id == user_id).all():
            if s.token[:12] == session_id:
                db.delete(s)
                db.commit()
                return True
        return False
    finally:
        db.close()


def revoke_other_sessions(user_id: int, keep_token: str) -> int:
    """Beendet alle Sitzungen außer der aktuellen."""
    db = SessionLocal()
    try:
        n = 0
        for s in db.query(DBSession).filter(DBSession.user_id == user_id).all():
            if s.token != keep_token:
                db.delete(s)
                n += 1
        db.commit()
        return n
    finally:
        db.close()


def change_password(user_id: int, old_password: str, new_password: str):
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if not u or not verify_password(old_password, u.salt, u.password_hash):
            return False, "Aktuelles Passwort falsch"
        if len(new_password) < 6:
            return False, "Neues Passwort zu kurz (min. 6 Zeichen)"
        u.password_hash, u.salt = hash_password(new_password)
        db.commit()
        return True, None
    finally:
        db.close()


def reset_password(user_id: int, new_password: str):
    """Owner setzt das Passwort eines Nutzers neu."""
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if not u:
            return False, "Nutzer nicht gefunden"
        if len(new_password) < 6:
            return False, "Passwort zu kurz (min. 6 Zeichen)"
        u.password_hash, u.salt = hash_password(new_password)
        # alle Sitzungen dieses Nutzers beenden
        for s in db.query(DBSession).filter(DBSession.user_id == user_id).all():
            db.delete(s)
        db.commit()
        return True, None
    finally:
        db.close()


def logout(token: str):
    if not token:
        return
    db = SessionLocal()
    try:
        s = db.get(DBSession, token)
        if s:
            db.delete(s)
            db.commit()
    finally:
        db.close()


def current(request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    db = SessionLocal()
    try:
        s = db.get(DBSession, token)
        if not s or (s.expires_at and s.expires_at < datetime.utcnow()):
            return None
        u = db.get(User, s.user_id)
        if not u:
            return None
        # last_seen höchstens minütlich aktualisieren (spart Schreiblast)
        try:
            now = datetime.utcnow()
            if not s.last_seen or (now - s.last_seen).total_seconds() > 60:
                s.last_seen = now
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return {"user_id": u.id, "username": u.username, "is_owner": u.is_owner,
                "tenant_id": s.active_tenant_id, "token": token}
    finally:
        db.close()


def accessible_tenants(user_id: int) -> set:
    """Eigene Firma + geteilte Firmen."""
    db = SessionLocal()
    try:
        ids = {user_id}
        for a in db.query(Access).filter(Access.user_id == user_id).all():
            ids.add(a.tenant_id)
        return ids
    finally:
        db.close()


def set_active_tenant(token: str, tenant_id: int) -> bool:
    db = SessionLocal()
    try:
        s = db.get(DBSession, token)
        if not s:
            return False
        if tenant_id not in accessible_tenants(s.user_id):
            return False
        s.active_tenant_id = tenant_id
        db.commit()
        return True
    finally:
        db.close()


def grant_access(owner_user_id: int, target_username: str) -> tuple:
    """Owner teilt SEINE Firma (tenant = owner_user_id) mit einem anderen Nutzer."""
    db = SessionLocal()
    try:
        target = db.query(User).filter(User.username == target_username).first()
        if not target:
            return False, "Nutzer nicht gefunden"
        if db.query(Access).filter(Access.user_id == target.id,
                                   Access.tenant_id == owner_user_id).first():
            return True, "Hatte bereits Zugriff"
        db.add(Access(user_id=target.id, tenant_id=owner_user_id))
        db.commit()
        return True, None
    finally:
        db.close()


def revoke_access(owner_user_id: int, target_user_id: int):
    db = SessionLocal()
    try:
        for a in db.query(Access).filter(Access.user_id == target_user_id,
                                         Access.tenant_id == owner_user_id).all():
            db.delete(a)
        db.commit()
    finally:
        db.close()
