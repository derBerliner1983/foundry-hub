"""Verwaltung des lokalen Ollama-Servers: Modelle auflisten, ziehen,
in den RAM laden / entladen und löschen."""
import httpx

from . import secrets
from .config import config


def BASE() -> str:
    """Ollama-URL – in der GUI änderbar (z. B. auf eine vorhandene Instanz)."""
    return secrets.ollama_url()


async def _client():
    return httpx.AsyncClient(timeout=600, base_url=BASE())


async def list_installed() -> list:
    """Auf der Platte installierte Modelle (GET /api/tags)."""
    try:
        async with httpx.AsyncClient(timeout=10, base_url=BASE()) as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception:  # noqa: BLE001
        return []


async def list_loaded() -> list:
    """Aktuell im RAM geladene Modelle (GET /api/ps)."""
    try:
        async with httpx.AsyncClient(timeout=10, base_url=BASE()) as c:
            r = await c.get("/api/ps")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception:  # noqa: BLE001
        return []


async def status() -> dict:
    installed = await list_installed()
    loaded = await list_loaded()
    loaded_names = {m.get("name") for m in loaded}
    reachable = True
    try:
        async with httpx.AsyncClient(timeout=5, base_url=BASE()) as c:
            await c.get("/api/tags")
    except Exception:  # noqa: BLE001
        reachable = False
    models = []
    for m in installed:
        name = m.get("name")
        models.append({
            "name": name,
            "size": m.get("size", 0),
            "loaded": name in loaded_names,
        })
    return {"reachable": reachable, "models": models, "loaded_count": len(loaded),
            "base_url": BASE()}


async def pull(name: str) -> dict:
    """Lädt ein Modell herunter (blockierend, ohne Stream-Parsing)."""
    try:
        async with httpx.AsyncClient(timeout=1800, base_url=BASE()) as c:
            r = await c.post("/api/pull", json={"name": name, "stream": False})
            r.raise_for_status()
            return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def load(name: str) -> dict:
    """Lädt ein Modell in den RAM (keep_alive dauerhaft)."""
    try:
        async with httpx.AsyncClient(timeout=600, base_url=BASE()) as c:
            r = await c.post("/api/generate", json={"model": name, "keep_alive": -1, "prompt": ""})
            r.raise_for_status()
            return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def unload(name: str) -> dict:
    """Entlädt ein Modell aus dem RAM (keep_alive 0)."""
    try:
        async with httpx.AsyncClient(timeout=60, base_url=BASE()) as c:
            r = await c.post("/api/generate", json={"model": name, "keep_alive": 0, "prompt": ""})
            r.raise_for_status()
            return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def delete(name: str) -> dict:
    """Löscht ein Modell von der Platte (DELETE /api/delete)."""
    try:
        async with httpx.AsyncClient(timeout=60, base_url=BASE()) as c:
            r = await c.request("DELETE", "/api/delete", json={"name": name})
            r.raise_for_status()
            return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def ensure_default_model() -> dict:
    """Beim Start: nur ziehen, wenn noch GAR KEIN Modell installiert ist.
    Ist bereits eines vorhanden, wird nichts geladen (Wunsch des Nutzers)."""
    if not config.OLLAMA_AUTO_MODEL:
        return {"action": "disabled"}
    installed = await list_installed()
    if installed:
        return {"action": "skip", "reason": "Modell bereits vorhanden",
                "models": [m.get("name") for m in installed]}
    res = await pull(config.OLLAMA_AUTO_MODEL)
    return {"action": "pulled" if res.get("ok") else "failed",
            "model": config.OLLAMA_AUTO_MODEL, **res}
