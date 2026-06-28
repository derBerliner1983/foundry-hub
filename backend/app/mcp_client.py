"""Echter (leichtgewichtiger) MCP-Client: spricht das Model-Context-Protocol
per JSON-RPC – über stdio (Subprozess) oder HTTP.

Pro Aufruf wird eine vollständige Sitzung aufgebaut (initialize → initialized →
Operationen → schließen). Das ist robust und ohne langlebige Verbindungen."""
import asyncio
import json
import shlex

import httpx

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "ai-hub", "version": "1.0"}
TIMEOUT = 20


class MCPError(Exception):
    pass


def _init_req(mid=1):
    return {"jsonrpc": "2.0", "id": mid, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": CLIENT_INFO}}


# --------------------------------------------------------------------------- #
# stdio-Transport
# --------------------------------------------------------------------------- #
async def _stdio_run(command: str, ops: list) -> list:
    if not command:
        raise MCPError("Kein Befehl für stdio-Server konfiguriert")
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def send(obj):
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        await proc.stdin.drain()

    async def read_id(want_id):
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=TIMEOUT)
            if not line:
                raise MCPError("MCP-Server hat die Verbindung beendet")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == want_id:
                return msg

    try:
        await send(_init_req(1))
        await read_id(1)
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        results = []
        mid = 2
        for method, params in ops:
            await send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
            resp = await read_id(mid)
            if "error" in resp:
                raise MCPError(resp["error"].get("message", "MCP-Fehler"))
            results.append(resp.get("result"))
            mid += 1
        return results
    finally:
        try:
            proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# HTTP-Transport (Streamable HTTP; JSON oder SSE)
# --------------------------------------------------------------------------- #
def _parse_http(resp) -> dict:
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        raise MCPError("Konnte SSE-Antwort nicht lesen")
    return resp.json()


async def _http_run(url: str, ops: list) -> list:
    if not url:
        raise MCPError("Keine URL für http-Server konfiguriert")
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=_init_req(1))
        r.raise_for_status()
        session = r.headers.get("mcp-session-id")
        if session:
            headers["mcp-session-id"] = session
        _parse_http(r)
        await c.post(url, headers=headers,
                     json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        results = []
        mid = 2
        for method, params in ops:
            r = await c.post(url, headers=headers,
                             json={"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
            r.raise_for_status()
            data = _parse_http(r)
            if "error" in data:
                raise MCPError(data["error"].get("message", "MCP-Fehler"))
            results.append(data.get("result"))
            mid += 1
        return results


async def _run(transport: str, command: str, url: str, ops: list) -> list:
    if transport == "http":
        return await _http_run(url, ops)
    return await _stdio_run(command, ops)


# --------------------------------------------------------------------------- #
# Öffentliche API
# --------------------------------------------------------------------------- #
async def list_tools(transport: str, command: str = "", url: str = "") -> list:
    res = await _run(transport, command, url, [("tools/list", {})])
    return (res[0] or {}).get("tools", [])


async def call_tool(transport: str, name: str, arguments: dict,
                    command: str = "", url: str = "") -> dict:
    res = await _run(transport, command, url,
                     [("tools/call", {"name": name, "arguments": arguments or {}})])
    return res[0] or {}


def result_to_text(result: dict) -> str:
    """Wandelt ein MCP tools/call-Resultat in lesbaren Text."""
    if not isinstance(result, dict):
        return str(result)
    parts = []
    for block in result.get("content", []):
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
    text = "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)
    if result.get("isError"):
        text = "[Fehler] " + text
    return text
