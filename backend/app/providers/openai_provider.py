"""OpenAI Provider (Chat Completions, REST)."""
import httpx

from ..config import config
from .base import BaseProvider, LLMResult, MockProvider


class OpenAIProvider(BaseProvider):
    name = "openai"

    def available(self) -> bool:
        return bool(config.OPENAI_API_KEY)

    async def chat(self, model: str, system: str, messages: list) -> LLMResult:
        if not self.available():
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error="Kein OPENAI_API_KEY")

        url = f"{config.OPENAI_BASE_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
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
                return LLMResult(text, self.name, model)
        except Exception as e:  # noqa: BLE001
            if config.ALLOW_MOCK_FALLBACK:
                return await MockProvider().chat(model, system, messages)
            return LLMResult("", self.name, model, ok=False, error=str(e))
