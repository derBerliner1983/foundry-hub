"""Isolierter Build-/Sandbox-Dienst.

Läuft in einem EIGENEN Container (getrennt vom App-Container) und führt dort
Befehle, Installationen und Builds aus. Der Projekt-Workspace ist als Volume
geteilt, sodass von Agenten geschriebene Dateien hier gebaut werden können.

Sicherheit: alle Pfade sind auf WORKSPACE_DIR begrenzt; der Container hat keinen
Zugriff auf die App-Datenbank. Reset löscht nur innerhalb des Workspace.
"""
import os
import shutil
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Foundry-Hub Sandbox")
ROOT = os.path.realpath(os.getenv("WORKSPACE_DIR", "/data/workspace"))
os.makedirs(ROOT, exist_ok=True)


def _safe(rel: str) -> str:
    target = os.path.realpath(os.path.join(ROOT, (rel or "").lstrip("/")))
    if target != ROOT and not target.startswith(ROOT + os.sep):
        raise ValueError("Pfad außerhalb des Workspace")
    return target


class ExecIn(BaseModel):
    cmd: str
    cwd: str = ""
    timeout: int = 600


class InstallIn(BaseModel):
    manager: str = "pip"          # pip | npm | apt
    packages: list[str] = []
    cwd: str = ""


class ResetIn(BaseModel):
    path: str = ""                # leer = ganzer Workspace-Projektordner


@app.get("/health")
def health():
    tools = {}
    for name, cmd in {"python": "python --version", "pip": "pip --version",
                      "node": "node --version", "npm": "npm --version",
                      "gcc": "gcc --version", "git": "git --version",
                      "zip": "zip --version"}.items():
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            tools[name] = r.stdout.splitlines()[0] if r.returncode == 0 and r.stdout else (r.returncode == 0)
        except Exception:  # noqa: BLE001
            tools[name] = False
    return {"ok": True, "workspace": ROOT, "tools": tools}


@app.post("/exec")
def execute(e: ExecIn):
    try:
        cwd = _safe(e.cwd)
        os.makedirs(cwd, exist_ok=True)
        p = subprocess.run(e.cmd, shell=True, cwd=cwd, capture_output=True,
                           text=True, timeout=min(e.timeout, 1800))
        return {"ok": p.returncode == 0, "code": p.returncode,
                "stdout": (p.stdout or "")[-8000:], "stderr": (p.stderr or "")[-8000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "stdout": "", "stderr": "Timeout"}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(ex)}


@app.post("/install")
def install(i: InstallIn):
    if not i.packages:
        return {"ok": False, "stderr": "Keine Pakete angegeben"}
    pkgs = [p for p in i.packages if all(c.isalnum() or c in "._-+=<>[]@/" for c in p)]
    cmds = {
        "pip": ["pip", "install", *pkgs],
        "npm": ["npm", "install", *pkgs],
        "apt": ["apt-get", "install", "-y", *pkgs],
    }
    if i.manager not in cmds:
        return {"ok": False, "stderr": "Unbekannter Paketmanager"}
    cwd = _safe(i.cwd)
    os.makedirs(cwd, exist_ok=True)
    try:
        if i.manager == "apt":
            subprocess.run(["apt-get", "update"], capture_output=True, text=True, timeout=300)
        p = subprocess.run(cmds[i.manager], cwd=cwd, capture_output=True, text=True, timeout=1200)
        return {"ok": p.returncode == 0, "code": p.returncode,
                "stdout": (p.stdout or "")[-8000:], "stderr": (p.stderr or "")[-8000:]}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "stderr": str(ex)}


class ServeIn(BaseModel):
    rel: str = ""
    cmd: str = ""
    port: int = 8090


_preview = {"proc": None}


@app.post("/serve")
def serve(s: ServeIn):
    """Startet einen (Dev-)Server im Projektordner als Hintergrundprozess für die Live-Vorschau."""
    if _preview["proc"] and _preview["proc"].poll() is None:
        _preview["proc"].terminate()
    cwd = _safe(s.rel)
    os.makedirs(cwd, exist_ok=True)
    cmd = s.cmd or f"python -m http.server {s.port} --bind 0.0.0.0"
    try:
        _preview["proc"] = subprocess.Popen(cmd, shell=True, cwd=cwd)
        return {"ok": True, "port": s.port, "cmd": cmd}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stderr": str(e)}


@app.post("/serve/stop")
def serve_stop():
    if _preview["proc"] and _preview["proc"].poll() is None:
        _preview["proc"].terminate()
    _preview["proc"] = None
    return {"ok": True}


@app.post("/reset")
def reset(r: ResetIn):
    """Löscht Inhalte innerhalb des Workspace (Software/Builds wieder entfernen)."""
    target = _safe(r.path)
    try:
        if os.path.isdir(target):
            for entry in os.listdir(target):
                full = os.path.join(target, entry)
                if os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                else:
                    os.remove(full)
        return {"ok": True, "cleared": os.path.relpath(target, ROOT)}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "stderr": str(ex)}
