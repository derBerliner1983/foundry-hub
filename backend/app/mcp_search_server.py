"""Web-Suche-MCP-Server (stdio).

Standard: schlüssellose Suche über DuckDuckGo (HTML).
Optional: Brave Search, wenn $BRAVE_API_KEY gesetzt ist (bessere Ergebnisse).

Tool: web_search(query, count=5)

Start:  python -m backend.app.mcp_search_server
"""
import html
import os
import re
import urllib.parse

import httpx

from .mcp_serverlib import serve

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
TIMEOUT = 20

TOOLS = [
    {"name": "web_search",
     "description": "Websuche; gibt Titel, URL und Kurzbeschreibung der Treffer zurück",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"}, "count": {"type": "number"}},
                     "required": ["query"]}},
]


def _strip(t):
    return html.unescape(re.sub("<[^>]+>", "", t)).strip()


def _brave(query, count):
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"}
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(url, headers=headers, params={"q": query, "count": count})
        r.raise_for_status()
        results = r.json().get("web", {}).get("results", [])[:count]
    lines = [f"{i+1}. {_strip(x.get('title',''))}\n   {x.get('url','')}\n   {_strip(x.get('description',''))}"
             for i, x in enumerate(results)]
    return "\n".join(lines) or "Keine Treffer"


def _duckduckgo(query, count):
    url = "https://html.duckduckgo.com/html/"
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (ai-hub-mcp)"}) as c:
        r = c.post(url, data={"q": query})
        r.raise_for_status()
        page = r.text
    blocks = re.findall(
        r'class="result__a"[^>]*href="(.*?)".*?>(.*?)</a>.*?'
        r'(?:class="result__snippet"[^>]*>(.*?)</a>)?',
        page, re.DOTALL)
    out = []
    for href, title, snippet in blocks[:count]:
        # DDG-Redirect auflösen (uddg-Parameter enthält die echte URL)
        m = re.search(r"uddg=([^&]+)", href)
        link = urllib.parse.unquote(m.group(1)) if m else href
        out.append(f"{len(out)+1}. {_strip(title)}\n   {link}\n   {_strip(snippet or '')}")
    return "\n".join(out) or "Keine Treffer"


def dispatch(name, args):
    if name != "web_search":
        return f"Unbekanntes Tool: {name}"
    query = args.get("query", "")
    if not query:
        return "Keine Suchanfrage angegeben"
    count = int(args.get("count", 5) or 5)
    count = max(1, min(count, 10))
    if BRAVE_API_KEY:
        try:
            return "[Brave]\n" + _brave(query, count)
        except Exception as e:  # noqa: BLE001
            return f"Brave-Fehler ({e}); ohne API-Key DuckDuckGo nutzen.\n" + _duckduckgo(query, count)
    return "[DuckDuckGo]\n" + _duckduckgo(query, count)


if __name__ == "__main__":
    serve("ai-hub-search", TOOLS, dispatch)
