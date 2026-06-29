"""GitHub-Integration: Repo anlegen und Projekt-Workspace pushen.

Nutzt einen persönlichen Access-Token (in den Zugangsdaten als GITHUB_TOKEN)."""
import httpx

from . import secrets
from . import workspace

API = "https://api.github.com"


def _token() -> str:
    return secrets.get("GITHUB_TOKEN")


def status() -> dict:
    tok = _token()
    if not tok:
        return {"configured": False}
    try:
        r = httpx.get(f"{API}/user", headers={"Authorization": f"Bearer {tok}",
                                              "Accept": "application/vnd.github+json"}, timeout=15)
        r.raise_for_status()
        return {"configured": True, "login": r.json().get("login")}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e)}


def push_project(project_id, repo_name: str, private: bool = True) -> dict:
    tok = _token()
    if not tok:
        return {"ok": False, "error": "Kein GitHub-Token in den Zugangsdaten"}
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    try:
        with httpx.Client(timeout=20) as c:
            me = c.get(f"{API}/user", headers=headers)
            me.raise_for_status()
            login = me.json()["login"]
            # Repo anlegen (falls noch nicht vorhanden)
            ex = c.get(f"{API}/repos/{login}/{repo_name}", headers=headers)
            if ex.status_code == 404:
                cr = c.post(f"{API}/user/repos", headers=headers,
                            json={"name": repo_name, "private": private, "auto_init": False})
                cr.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Repo-Anlage fehlgeschlagen: {e}"}

    remote = f"https://x-access-token:{tok}@github.com/{login}/{repo_name}.git"
    # Workspace versionieren und pushen
    workspace.git_autocommit(project_id, "Foundry-Hub: Stand für GitHub")
    workspace._ws_exec(project_id, "git remote remove origin 2>/dev/null; "
                       f"git remote add origin {remote}")
    res = workspace._ws_exec(project_id, "git push -u origin main --force", timeout=120)
    safe = res.get("stderr", "").replace(tok, "***")
    if res.get("ok"):
        return {"ok": True, "url": f"https://github.com/{login}/{repo_name}"}
    return {"ok": False, "error": safe or "push fehlgeschlagen"}
