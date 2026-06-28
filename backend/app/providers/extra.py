"""Weitere LLM-Anbieter: OpenRouter, Mistral (OpenAI-kompatibel) und Google Gemini."""
import httpx

from .. import secrets
from .base import BaseProvider, LLMResult, MockProvider


class OpenAICompat(BaseProvider):
    """Für alle Anbieter mit OpenAI-kompatibler /chat/completions-API."""

    def __init__(self, name, base_url, key_name):
        self.name = name
        self.base_url = base_url
        self.key_name = key_name

    def available(self) -> bool:
        return bool(secrets.get(self.key_name))

    async def chat(self, model, system, messages):
        key = secrets.get(self.key_name)
        if not key:
            return await MockProvider().chat(model, system, messages)
        full = [{"role": "system", "content": system}] + messages
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{self.base_url}/chat/completions",
                                 headers={"Authorization": f"Bearer {key}"},
                                 json={"model": model, "messages": full, "temperature": 0.4})
                r.raise_for_status()
                d = r.json()
                u = d.get("usage", {})
                return LLMResult(d["choices"][0]["message"]["content"], self.name, model,
                                 input_tokens=u.get("prompt_tokens", 0),
                                 output_tokens=u.get("completion_tokens", 0))
        except Exception:  # noqa: BLE001
            return await MockProvider().chat(model, system, messages)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def available(self) -> bool:
        return bool(secrets.get("GEMINI_API_KEY"))

    async def chat(self, model, system, messages):
        key = secrets.get("GEMINI_API_KEY")
        if not key:
            return await MockProvider().chat(model, system, messages)
        text_in = system + "\n\n" + "\n".join(m["content"] for m in messages)
        body = {"contents": [{"role": "user", "parts": [{"text": text_in}]}]}
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                    json=body)
                r.raise_for_status()
                d = r.json()
                text = d["candidates"][0]["content"]["parts"][0]["text"]
                um = d.get("usageMetadata", {})
                return LLMResult(text, "gemini", model,
                                 input_tokens=um.get("promptTokenCount", 0),
                                 output_tokens=um.get("candidatesTokenCount", 0))
        except Exception:  # noqa: BLE001
            return await MockProvider().chat(model, system, messages)
