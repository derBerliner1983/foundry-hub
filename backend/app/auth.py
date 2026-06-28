"""Authentifizierung: Benutzer, Passwörter (scrypt), Sitzungen (Cookie),
Tenant-Zugriff (eigene Firma + geteilte)."""
import hashlib
import secrets as pysecrets  # stdlib (nicht das App-Modul)
from datetime import datetime, timedelta

from .database import SessionLocal
from .models import Access, Session as DBSession, User

COOKIE = "aihub_session"
SESSION_DAYS = 30


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


def login(username: str, password: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if not u or not verify_password(password, u.salt, u.password_hash):
            return None
        token = pysecrets.token_urlsafe(32)
        db.add(DBSession(token=token, user_id=u.id, active_tenant_id=u.id,
                         expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
        db.commit()
        return token
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
