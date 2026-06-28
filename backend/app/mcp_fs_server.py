"""Dateisystem-MCP-Server (stdio) – auf einen Wurzelordner begrenzt.

Wurzel = $MCP_FS_ROOT (Standard: $WORKSPACE_DIR bzw. /data/workspace).
Tools: list_dir, read_file, write_file – alle innerhalb der Wurzel (kein Ausbruch).

Start:  python -m backend.app.mcp_fs_server
"""
import os

from .mcp_serverlib import serve

ROOT = os.path.realpath(
    os.getenv("MCP_FS_ROOT") or os.getenv("WORKSPACE_DIR") or "/data/workspace"
)
os.makedirs(ROOT, exist_ok=True)

TOOLS = [
    {"name": "list_dir", "description": "Listet Dateien/Ordner unter path (relativ zur Wurzel)",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "read_file", "description": "Liest eine Textdatei (relativ zur Wurzel)",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}},
                     "required": ["path"]}},
    {"name": "write_file", "description": "Schreibt eine Textdatei (relativ zur Wurzel)",
     "inputSchema": {"type": "object",
                     "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                     "required": ["path", "content"]}},
]


def _safe(rel):
    target = os.path.realpath(os.path.join(ROOT, (rel or "").lstrip("/")))
    if target != ROOT and not target.startswith(ROOT + os.sep):
        raise ValueError("Pfad außerhalb der erlaubten Wurzel")
    return target


def dispatch(name, args):
    if name == "list_dir":
        target = _safe(args.get("path", "."))
        if not os.path.isdir(target):
            return "(kein Verzeichnis)"
        entries = []
        for e in sorted(os.listdir(target)):
            full = os.path.join(target, e)
            entries.append(("[DIR] " if os.path.isdir(full) else "      ") + e)
        return "\n".join(entries) or "(leer)"
    if name == "read_file":
        target = _safe(args["path"])
        if not os.path.isfile(target):
            return "(Datei nicht gefunden)"
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:8000]
    if name == "write_file":
        target = _safe(args["path"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(args.get("content", ""))
        return f"Geschrieben: {os.path.relpath(target, ROOT)}"
    return f"Unbekanntes Tool: {name}"


if __name__ == "__main__":
    serve("ai-hub-filesystem", TOOLS, dispatch)
