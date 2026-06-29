"""Minimaler Demo-MCP-Server (stdio) zum Testen – Tools: echo, add.

Start:  python -m backend.app.mcp_demo_server
"""
from .mcp_serverlib import serve

TOOLS = [
    {"name": "echo", "description": "Gibt den übergebenen Text unverändert zurück",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "add", "description": "Addiert zwei Zahlen a und b",
     "inputSchema": {"type": "object",
                     "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                     "required": ["a", "b"]}},
]


def dispatch(name, args):
    if name == "echo":
        return str(args.get("text", ""))
    if name == "add":
        return str((args.get("a", 0) or 0) + (args.get("b", 0) or 0))
    return f"Unbekanntes Tool: {name}"


if __name__ == "__main__":
    serve("foundry-hub-demo", TOOLS, dispatch)
