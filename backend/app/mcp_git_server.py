"""Git-MCP-Server (stdio) – liest Git-Infos eines Repos im Workspace.

Wurzel = $MCP_FS_ROOT (Standard: $WORKSPACE_DIR). repo ist relativ dazu.
Tools (lesend): git_status, git_log, git_diff, git_branch, git_show.

Start:  python -m backend.app.mcp_git_server
"""
import os
import subprocess

from .mcp_serverlib import serve

ROOT = os.path.realpath(
    os.getenv("MCP_FS_ROOT") or os.getenv("WORKSPACE_DIR") or "/data/workspace"
)
os.makedirs(ROOT, exist_ok=True)

TOOLS = [
    {"name": "git_status", "description": "git status des Repos (repo relativ zur Wurzel)",
     "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}}},
    {"name": "git_log", "description": "Letzte n Commits (Standard 10)",
     "inputSchema": {"type": "object",
                     "properties": {"repo": {"type": "string"}, "n": {"type": "number"}}}},
    {"name": "git_diff", "description": "git diff (uncommitted) des Repos",
     "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}}},
    {"name": "git_branch", "description": "Aktueller Branch und Branch-Liste",
     "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}}},
    {"name": "git_show", "description": "git show eines Refs (Standard HEAD)",
     "inputSchema": {"type": "object",
                     "properties": {"repo": {"type": "string"}, "ref": {"type": "string"}}}},
]


def _repo(rel):
    target = os.path.realpath(os.path.join(ROOT, (rel or ".").lstrip("/")))
    if target != ROOT and not target.startswith(ROOT + os.sep):
        raise ValueError("Repo-Pfad außerhalb der Wurzel")
    if not os.path.isdir(target):
        raise ValueError("Verzeichnis nicht gefunden")
    return target


def _git(repo, args):
    try:
        proc = subprocess.run(["git", "-C", repo] + args,
                              capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return "Fehler: git ist nicht installiert"
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return out.strip()[:8000] or "(keine Ausgabe)"


def dispatch(name, args):
    repo = _repo(args.get("repo", "."))
    if name == "git_status":
        return _git(repo, ["status", "-sb"])
    if name == "git_log":
        n = int(args.get("n", 10) or 10)
        return _git(repo, ["log", f"-{n}", "--oneline", "--decorate"])
    if name == "git_diff":
        return _git(repo, ["diff"])
    if name == "git_branch":
        cur = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        branches = _git(repo, ["branch", "-a"])
        return f"Aktuell: {cur}\n\n{branches}"
    if name == "git_show":
        return _git(repo, ["show", "--stat", args.get("ref", "HEAD")])
    return f"Unbekanntes Tool: {name}"


if __name__ == "__main__":
    serve("ai-hub-git", TOOLS, dispatch)
