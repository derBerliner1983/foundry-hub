"""Web-MCP-Server (stdio) – einfache Web-Abfrage per HTTP.

Tools: fetch_url (GET, gibt Text/HTML gekürzt zurück), http_head (Status & Header).

Start:  python -m backend.app.mcp_web_server
"""
import httpx

from .mcp_serverlib import serve

TIMEOUT = 20
MAX_CHARS = 8000

TOOLS = [
    {"name": "fetch_url", "description": "Lädt eine URL per GET und gibt den Textinhalt (gekürzt) zurück",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}},
                     "required": ["url"]}},
    {"name": "http_head", "description": "Gibt HTTP-Status und wichtige Header einer URL zurück",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}},
                     "required": ["url"]}},
]


def dispatch(name, args):
    url = args.get("url", "")
    if not url:
        return "Keine URL angegeben"
    if name == "fetch_url":
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "foundry-hub-mcp/1.0"})
            ctype = r.headers.get("content-type", "")
            body = r.text[:MAX_CHARS]
            return f"HTTP {r.status_code} · {ctype}\n\n{body}"
    if name == "http_head":
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.head(url, headers={"User-Agent": "foundry-hub-mcp/1.0"})
            keys = ["content-type", "content-length", "server", "location"]
            head = "\n".join(f"{k}: {r.headers[k]}" for k in keys if k in r.headers)
            return f"HTTP {r.status_code}\n{head}"
    return f"Unbekanntes Tool: {name}"


if __name__ == "__main__":
    serve("foundry-hub-web", TOOLS, dispatch)
