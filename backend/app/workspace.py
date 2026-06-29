"""Datei-Werkstatt: pro Projekt ein Arbeitsverzeichnis, in das Agenten
echte Dateien schreiben und in dem sie Befehle (Sandbox) ausführen können.

Ist SANDBOX_URL gesetzt, laufen Befehle im isolierten Build-Container, sonst
lokal im App-Container."""
import os
import shutil
import subprocess

import httpx

from .config import config


def _project_root(project_id) -> str:
    pid = project_id if project_id is not None else "shared"
    root = os.path.join(config.WORKSPACE_DIR, f"project_{pid}")
    os.makedirs(root, exist_ok=True)
    return root


def _safe_path(project_id, rel_path: str) -> str:
    """Verhindert Ausbruch aus dem Projektverzeichnis (kein ../)."""
    root = os.path.realpath(_project_root(project_id))
    target = os.path.realpath(os.path.join(root, rel_path.lstrip("/")))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("Pfad außerhalb des Workspace")
    return target


def write_file(project_id, rel_path: str, content: str) -> str:
    target = _safe_path(project_id, rel_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content or "")
    return os.path.relpath(target, _project_root(project_id))


def safe_abspath(project_id, rel_path: str) -> str:
    """Sicherer absoluter Pfad innerhalb des Projekt-Workspace (für Download)."""
    return _safe_path(project_id, rel_path)


def save_bytes(project_id, rel_path: str, data: bytes) -> str:
    target = _safe_path(project_id, rel_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(data or b"")
    return os.path.relpath(target, _project_root(project_id))


def make_zip(project_id) -> str:
    """Packt den Projekt-Workspace in eine ZIP und gibt den Pfad zurück."""
    import tempfile
    import zipfile
    root = _project_root(project_id)
    fd, path = tempfile.mkstemp(suffix=".zip", prefix=f"project_{project_id or 'shared'}_")
    os.close(fd)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(root):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, root))
    return path


def read_file(project_id, rel_path: str) -> str:
    target = _safe_path(project_id, rel_path)
    if not os.path.isfile(target):
        return ""
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def list_files(project_id) -> list:
    root = _project_root(project_id)
    out = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            out.append({"path": rel, "size": size})
    return sorted(out, key=lambda x: x["path"])


def _project_rel(project_id) -> str:
    pid = project_id if project_id is not None else "shared"
    return f"project_{pid}"


def run_command(project_id, command: str) -> dict:
    """Führt einen Shell-Befehl im Projektverzeichnis aus (mit Timeout).
    Mit SANDBOX_URL im isolierten Build-Container, sonst lokal."""
    if not config.ENABLE_CODE_EXECUTION:
        return {"ok": False, "stdout": "", "stderr": "Code-Ausführung ist deaktiviert.", "code": -1}

    if config.SANDBOX_URL:
        try:
            r = httpx.post(f"{config.SANDBOX_URL}/exec",
                           json={"cmd": command, "cwd": _project_rel(project_id),
                                 "timeout": config.SANDBOX_TIMEOUT},
                           timeout=config.SANDBOX_TIMEOUT + 15)
            d = r.json()
            return {"ok": d.get("ok", False), "stdout": (d.get("stdout") or "")[-4000:],
                    "stderr": (d.get("stderr") or "")[-4000:], "code": d.get("code", -1)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "stdout": "", "stderr": f"Sandbox nicht erreichbar: {e}", "code": -1}

    root = _project_root(project_id)
    try:
        proc = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True,
            timeout=config.EXEC_TIMEOUT,
        )
        out = (proc.stdout or "")[-4000:]
        err = (proc.stderr or "")[-4000:]
        return {"ok": proc.returncode == 0, "stdout": out, "stderr": err, "code": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timeout nach {config.EXEC_TIMEOUT}s", "code": -1}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}


def _ws_exec(project_id, command: str, timeout: int = 60) -> dict:
    """Führt einen Befehl im Workspace aus (für Infrastruktur wie Git) –
    unabhängig vom Code-Ausführungs-Schalter."""
    if config.SANDBOX_URL:
        try:
            r = httpx.post(f"{config.SANDBOX_URL}/exec",
                           json={"cmd": command, "cwd": _project_rel(project_id), "timeout": timeout},
                           timeout=timeout + 15)
            d = r.json()
            return {"ok": d.get("ok", False), "stdout": d.get("stdout", ""), "stderr": d.get("stderr", "")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "stdout": "", "stderr": str(e)}
    root = _project_root(project_id)
    try:
        p = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "stdout": p.stdout or "", "stderr": p.stderr or ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": str(e)}


_GIT = "git -c user.email=aihub@local -c user.name=AI-Hub"


def git_autocommit(project_id, message: str) -> dict:
    """Versioniert den aktuellen Arbeitsstand (init bei Bedarf)."""
    _ws_exec(project_id, "git init -q 2>/dev/null; git symbolic-ref HEAD refs/heads/main 2>/dev/null")
    _ws_exec(project_id, f"{_GIT} add -A")
    msg = (message or "Arbeitsstand").replace('"', "'")[:200]
    res = _ws_exec(project_id, f'{_GIT} commit -q -m "{msg}"')
    return res


def git_history(project_id, n: int = 25) -> list:
    res = _ws_exec(project_id, f"{_GIT} log --pretty=format:'%h|%ad|%s' --date=format:'%d.%m. %H:%M' -{n}")
    if not res["ok"] or not res["stdout"].strip():
        return []
    out = []
    for line in res["stdout"].strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            out.append({"sha": parts[0], "date": parts[1], "message": parts[2],
                        "verified": "[verified]" in parts[2]})
    return out


def git_rollback(project_id, commit: str) -> dict:
    """Setzt den Workspace hart auf einen früheren Commit zurück."""
    safe = "".join(c for c in (commit or "") if c.isalnum())
    if not safe:
        return {"ok": False, "stderr": "Ungültiger Commit"}
    return _ws_exec(project_id, f"{_GIT} reset --hard {safe}")


def git_diff(project_id, commit: str, base: str = "") -> dict:
    """Liefert den Diff eines Commits (gegen seinen Vorgänger oder gegen `base`)."""
    safe = "".join(c for c in (commit or "") if c.isalnum())
    if not safe:
        return {"ok": False, "diff": "", "stderr": "Ungültiger Commit"}
    base_safe = "".join(c for c in (base or "") if c.isalnum())
    if base_safe:
        rng = f"{base_safe} {safe}"
    else:
        rng = f"{safe}~1 {safe}"
    res = _ws_exec(project_id, f"{_GIT} diff --stat --no-color {rng}; echo '---DIFF---'; "
                              f"{_GIT} diff --no-color {rng}")
    out = res.get("stdout", "")
    stat, _, body = out.partition("---DIFF---")
    if not body.strip():
        # z. B. erster Commit ohne Vorgänger -> kompletten Commit-Inhalt zeigen
        res2 = _ws_exec(project_id, f"{_GIT} show --no-color {safe}")
        d2 = res2.get("stdout", "")
        if d2.strip():
            return {"ok": True, "stat": "", "diff": d2[:200000]}
    return {"ok": True, "stat": stat.strip(), "diff": body.strip()[:200000]}


def reset_workspace(project_id, path: str = "") -> dict:
    """Löscht installierte Software/Builds wieder (innerhalb des Projekt-Workspace)."""
    if config.SANDBOX_URL:
        try:
            rel = _project_rel(project_id) + (("/" + path.lstrip("/")) if path else "")
            r = httpx.post(f"{config.SANDBOX_URL}/reset", json={"path": rel}, timeout=60)
            return r.json()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "stderr": str(e)}
    target = _safe_path(project_id, path) if path else _project_root(project_id)
    try:
        for entry in os.listdir(target):
            full = os.path.join(target, entry)
            shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) else os.remove(full)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stderr": str(e)}
