"""Datei-Werkstatt: pro Projekt ein Arbeitsverzeichnis, in das Agenten
echte Dateien schreiben und in dem sie Befehle (Sandbox) ausführen können."""
import os
import subprocess

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


def run_command(project_id, command: str) -> dict:
    """Führt einen Shell-Befehl im Projektverzeichnis aus (mit Timeout)."""
    if not config.ENABLE_CODE_EXECUTION:
        return {"ok": False, "stdout": "", "stderr": "Code-Ausführung ist deaktiviert.", "code": -1}
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
