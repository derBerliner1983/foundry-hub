"""Echte Embeddings für die Wissenssuche (Vektor-RAG).

Nutzt OpenAI (text-embedding-3-small) wenn ein Key gesetzt ist, sonst Ollama
(nomic-embed-text) lokal. Ist nichts verfügbar, gibt es None zurück und die
Suche fällt auf die Stichwortsuche zurück."""
import math

import httpx

from . import secrets
from .config import config


def available() -> bool:
    if secrets.provider_key("openai"):
        return True
    try:
        httpx.get(f"{secrets.ollama_url()}/api/tags", timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def embed(text: str):
    """Gibt einen Embedding-Vektor (list[float]) zurück oder None."""
    text = (text or "").strip()[:8000]
    if not text:
        return None
    key = secrets.provider_key("openai")
    if key:
        try:
            r = httpx.post(f"{config.OPENAI_BASE_URL}/v1/embeddings",
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": "text-embedding-3-small", "input": text}, timeout=30)
            r.raise_for_status()
            return r.json()["data"][0]["embedding"]
        except Exception:  # noqa: BLE001
            pass
    try:
        r = httpx.post(f"{secrets.ollama_url()}/api/embeddings",
                       json={"model": "nomic-embed-text", "prompt": text}, timeout=30)
        r.raise_for_status()
        v = r.json().get("embedding")
        return v or None
    except Exception:  # noqa: BLE001
        return None


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
