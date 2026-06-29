"""MCP-Client mit DAUERHAFTEN Sitzungen (Session-Pool).

Statt pro Aufruf neu zu verbinden, wird je Server eine langlebige Sitzung
gehalten und wiederverwendet (initialize nur einmal). Stirbt ein stdio-Prozess
oder bricht die HTTP-Sitzung ab, wird einmalig neu verbunden."""
import asyncio
import json
import shlex

import httpx

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "foundry-hub", "version": "1.0"}
TIMEOUT = 20


class MCPError(Exception):
    pass


def _init_params():
    return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": CLIENT_INFO}


# --------------------------------------------------------------------------- #
# stdio-Sitzung (langlebiger Subprozess)
# --------------------------------------------------------------------------- #
class _StdioSession:
    def __init__(self, command: str):
        self.command = command
        self.proc = None
        self.next_id = 1
        self.lock = asyncio.Lock()

    def _alive(self):
        return self.proc is not None and self.proc.returncode is None

    async def _spawn(self):
        if not self.command:
            raise MCPError("Kein Befehl für stdio-Server")
        self.proc = await asyncio.create_subprocess_exec(
            *shlex.split(self.command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.next_id = 1
        await self._send({"jsonrpc": "2.0", "id": self._id(), "method": "initialize",
                          "params": _init_params()}, expect=True)
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _id(self):
        i = self.next_id
        self.next_id += 1
        return i

    async def _send(self, obj, expect=False):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self.proc.stdin.drain()
        if not expect:
            return None
        want = obj["id"]
        while True:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=TIMEOUT)
            if not line:
                raise MCPError("stdio-Server beendet")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == want:
                if "error" in msg:
                    raise MCPError(msg["error"].get("message", "MCP-Fehler"))
                return msg.get("result")

    async def request(self, method, params):
        async with self.lock:
            for attempt in (1, 2):
                try:
                    if not self._alive():
                        await self._spawn()
                    return await self._send(
                        {"jsonrpc": "2.0", "id": self._id(), "method": method,
                         "params": params}, expect=True)
                except (MCPError, BrokenPipeError, ConnectionError,
                        asyncio.TimeoutError) as e:
                    self.proc = None  # tot -> beim nächsten Versuch neu spawnen
                    if attempt == 2:
                        raise MCPError(str(e))

    async def close(self):
        async with self.lock:
            if self._alive():
                try:
                    self.proc.terminate()
                    await asyncio.wait_for(self.proc.wait(), timeout=3)
                except Exception:  # noqa: BLE001
                    try:
                        self.proc.kill()
                    except Exception:  # noqa: BLE001
                        pass
            self.proc = None


# --------------------------------------------------------------------------- #
# HTTP-Sitzung (Session-ID wird wiederverwendet)
# --------------------------------------------------------------------------- #
class _HttpSession:
    def __init__(self, url: str):
        self.url = url
        self.session_id = None
        self.next_id = 1
        self.lock = asyncio.Lock()

    def _headers(self):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        return h

    @staticmethod
    def _parse(resp):
        if "text/event-stream" in resp.headers.get("content-type", ""):
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            raise MCPError("SSE-Antwort unlesbar")
        return resp.json()

    async def _init(self, client):
        r = await client.post(self.url, headers=self._headers(),
                              json={"jsonrpc": "2.0", "id": 0, "method": "initialize",
                                    "params": _init_params()})
        r.raise_for_status()
        self.session_id = r.headers.get("mcp-session-id")
        self._parse(r)
        await client.post(self.url, headers=self._headers(),
                          json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def request(self, method, params):
        if not self.url:
            raise MCPError("Keine URL für http-Server")
        async with self.lock:
            for attempt in (1, 2):
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                        if not self.session_id:
                            await self._init(client)
                        self.next_id += 1
                        r = await client.post(self.url, headers=self._headers(),
                                              json={"jsonrpc": "2.0", "id": self.next_id,
                                                    "method": method, "params": params})
                        r.raise_for_status()
                        data = self._parse(r)
                        if "error" in data:
                            raise MCPError(data["error"].get("message", "MCP-Fehler"))
                        return data.get("result")
                except Exception as e:  # noqa: BLE001
                    self.session_id = None  # Sitzung neu aufbauen
                    if attempt == 2:
                        raise MCPError(str(e))

    async def close(self):
        self.session_id = None


# --------------------------------------------------------------------------- #
# Pool
# --------------------------------------------------------------------------- #
_pool = {}
_pool_lock = asyncio.Lock()


async def _session(transport, command, url):
    key = f"{transport}|{command}|{url}"
    async with _pool_lock:
        s = _pool.get(key)
        if s is None:
            s = _HttpSession(url) if transport == "http" else _StdioSession(command)
            _pool[key] = s
        return s


async def close_session(transport, command, url):
    key = f"{transport}|{command}|{url}"
    async with _pool_lock:
        s = _pool.pop(key, None)
    if s:
        await s.close()


async def close_all():
    async with _pool_lock:
        sessions = list(_pool.values())
        _pool.clear()
    for s in sessions:
        await s.close()


# --------------------------------------------------------------------------- #
# Öffentliche API (unverändert)
# --------------------------------------------------------------------------- #
async def list_tools(transport: str, command: str = "", url: str = "") -> list:
    s = await _session(transport, command, url)
    res = await s.request("tools/list", {})
    return (res or {}).get("tools", [])


async def call_tool(transport: str, name: str, arguments: dict,
                    command: str = "", url: str = "") -> dict:
    s = await _session(transport, command, url)
    res = await s.request("tools/call", {"name": name, "arguments": arguments or {}})
    return res or {}


def result_to_text(result: dict) -> str:
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
