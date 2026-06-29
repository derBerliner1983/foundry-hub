"""Ollama Provider für lokale Modelle."""
import httpx

from .. import secrets
from .base import BaseProvider, LLMResult, MockProvider


class OllamaProvider(BaseProvider):
    name = "ollama"

    def available(self) -> bool:
        # Lokaler Dienst gilt als verfügbar; bei Fehler greift der Mock.
        return True

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        url = f"{secrets.ollama_url()}/api/chat"
        full = [{"role": "system", "content": system}] + messages
        payload = {"model": model, "messages": full, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
                text = data.get("message", {}).get("content", "")
                if not text:
                    raise ValueError("Leere Antwort von Ollama")
                return LLMResult(text, self.name, model)
        except Exception as e:  # noqa: BLE001
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error=str(e))
