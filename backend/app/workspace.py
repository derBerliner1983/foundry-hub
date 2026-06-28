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
