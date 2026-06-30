"""Owner-/Nutzer-Passwort zurücksetzen (Notfall, ohne Login).

Im laufenden Container ausführen (Arbeitsverzeichnis /app):

    # Vorhandene Nutzer anzeigen:
    docker exec -it foundryhub-app python -m backend.reset_password

    # Passwort eines Nutzers neu setzen (löscht zugleich 2FA & aktive Sitzungen):
    docker exec -it foundryhub-app python -m backend.reset_password <benutzer> <neues-passwort>

Ohne Benutzernamen wird der erste Owner genommen:
    docker exec -it foundryhub-app python -m backend.reset_password --owner <neues-passwort>
"""
import sys

from backend.app.database import SessionLocal
from backend.app.models import Session as DBSession, User
from backend.app import auth


def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("Keine Nutzer vorhanden – beim ersten Aufruf der Web-UI das Owner-Konto anlegen.")
            return
        print("Vorhandene Nutzer:")
        for u in users:
            flags = []
            if u.is_owner:
                flags.append("Owner")
            if u.totp_enabled:
                flags.append("2FA an")
            print(f"  - {u.username}" + (f"  [{', '.join(flags)}]" if flags else ""))
        print("\nPasswort setzen:  python -m backend.reset_password <benutzer> <neues-passwort>")
    finally:
        db.close()


def reset(username: str | None, new_password: str):
    if len(new_password) < 6:
        print("Fehler: Passwort muss mindestens 6 Zeichen haben.")
        sys.exit(1)
    db = SessionLocal()
    try:
        if username in (None, "--owner"):
            u = (db.query(User).filter(User.is_owner == True).first()  # noqa: E712
                 or db.query(User).first())
        else:
            u = db.query(User).filter(User.username == username).first()
        if not u:
            print(f"Fehler: Nutzer '{username}' nicht gefunden.")
            list_users()
            sys.exit(1)
        u.password_hash, u.salt = auth.hash_password(new_password)
        u.totp_enabled = False          # 2FA entfernen, falls es den Login blockiert
        u.totp_secret = ""
        # alle aktiven Sitzungen dieses Nutzers beenden
        for s in db.query(DBSession).filter(DBSession.user_id == u.id).all():
            db.delete(s)
        db.commit()
        print(f"✓ Passwort für '{u.username}' neu gesetzt. 2FA wurde deaktiviert. "
              "Jetzt mit diesem Benutzernamen und dem neuen Passwort anmelden.")
    finally:
        db.close()


def main():
    args = sys.argv[1:]
    if not args:
        list_users()
    elif len(args) == 1:
        # nur Passwort -> Owner
        reset("--owner", args[0])
    else:
        reset(args[0], args[1])


if __name__ == "__main__":
    main()
