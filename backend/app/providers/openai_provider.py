"""OpenAI Provider (Chat Completions, REST)."""
import httpx

from .. import secrets
from ..config import config
from .base import BaseProvider, LLMResult, MockProvider


class OpenAIProvider(BaseProvider):
    name = "openai"

    def available(self) -> bool:
        return bool(secrets.provider_key("openai"))

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        if not self.available():
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error="Kein OPENAI_API_KEY")

        url = f"{config.OPENAI_BASE_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {secrets.provider_key('openai')}",
            "content-type": "application/json",
        }
        full = [{"role": "system", "content": system}] + messages
        payload = {"model": model, "messages": full, "temperature": 0.4}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                u = data.get("usage", {})
                return LLMResult(text, self.name, model,
                                 input_tokens=u.get("prompt_tokens", 0),
                                 output_tokens=u.get("completion_tokens", 0))
        except Exception as e:  # noqa: BLE001
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error=str(e))
