"""Minimaler MCP-Server (stdio, JSON-RPC) zum Testen des MCP-Clients.

Start (als MCP-Server in der Registry eintragen, transport=stdio):
    python -m backend.app.mcp_demo_server

Bietet zwei Tools: echo(text) und add(a, b).
"""
import json
import sys

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "echo",
        "description": "Gibt den übergebenen Text unverändert zurück",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Addiert zwei Zahlen a und b",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _call(name, args):
    if name == "echo":
        return str(args.get("text", ""))
    if name == "add":
        try:
            return str((args.get("a", 0) or 0) + (args.get("b", 0) or 0))
        except TypeError:
            return "Fehler: a und b müssen Zahlen sein"
    return f"Unbekanntes Tool: {name}"


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method")

        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ai-hub-demo", "version": "1.0"},
            }})
        elif method == "notifications/initialized":
            continue  # Notification, keine Antwort
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params", {})
            text = _call(params.get("name"), params.get("arguments", {}) or {})
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"Unbekannte Methode: {method}"}})


if __name__ == "__main__":
    main()
