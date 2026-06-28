"""Mini-Bibliothek für eigene MCP-Server (stdio, JSON-RPC).

Damit lassen sich kleine MCP-Server mit wenigen Zeilen schreiben – sie laufen
mit reinem Python im Container, ohne Node/npx."""
import json
import sys

PROTOCOL_VERSION = "2024-11-05"


def serve(name: str, tools: list, dispatch):
    """Startet die JSON-RPC-Schleife. `dispatch(tool_name, args)->str` führt ein Tool aus."""
    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

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
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": name, "version": "1.0"},
            }})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tools}})
        elif method == "tools/call":
            params = msg.get("params", {})
            try:
                text = dispatch(params.get("name"), params.get("arguments", {}) or {})
                is_error = False
            except Exception as e:  # noqa: BLE001
                text, is_error = f"Fehler: {e}", True
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": str(text)}], "isError": is_error}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"Unbekannte Methode: {method}"}})
