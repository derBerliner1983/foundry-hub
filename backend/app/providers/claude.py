"""Anthropic Claude Provider (REST, ohne SDK-Abhängigkeit)."""
import httpx

from .. import secrets
from ..config import config
from .base import BaseProvider, LLMResult, MockProvider


class ClaudeProvider(BaseProvider):
    name = "claude"

    def available(self) -> bool:
        return bool(secrets.provider_key("anthropic"))

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        if not self.available():
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error="Kein ANTHROPIC_API_KEY")

        url = f"{config.ANTHROPIC_BASE_URL}/v1/messages"
        headers = {
            "x-api-key": secrets.provider_key("anthropic"),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 2000,
            "system": system,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
                u = data.get("usage", {})
                return LLMResult("".join(parts), self.name, model,
                                 input_tokens=u.get("input_tokens", 0),
                                 output_tokens=u.get("output_tokens", 0))
        except Exception as e:  # noqa: BLE001
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error=str(e))
