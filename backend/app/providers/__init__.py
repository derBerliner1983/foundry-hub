"""Provider-Auswahl: liefert für (provider, model) eine Chat-Funktion."""
from .base import LLMResult, MockProvider
from .claude import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama import OllamaProvider

_PROVIDERS = {
    "claude": ClaudeProvider(),
    "openai": OpenAIProvider(),
    "ollama": OllamaProvider(),
    "mock": MockProvider(),
}


# Fallback-Modelle je Anbieter (falls der primäre Anbieter ausfällt)
_FALLBACK_MODEL = {"claude": "claude-sonnet-4-6", "openai": "gpt-4o-mini", "ollama": "llama3.2"}
_FALLBACK_ORDER = ["claude", "openai", "ollama"]


async def chat(provider: str, model: str, system: str, messages: list) -> LLMResult:
    """Ruft das gewählte Modell auf. Schlägt es fehl, wird automatisch ein anderer
    verfügbarer Anbieter versucht; zuletzt der Mock."""
    impl = _PROVIDERS.get(provider, _PROVIDERS["mock"])
    if provider != "mock" and impl.available():
        res = await impl.chat(model=model, system=system, messages=messages)
        if res.ok and res.provider != "mock":
            return res
    # Fallback-Kette über verfügbare Anbieter
    for name in _FALLBACK_ORDER:
        if name == provider:
            continue
        p = _PROVIDERS[name]
        if p.available():
            res = await p.chat(model=_FALLBACK_MODEL[name], system=system, messages=messages)
            if res.ok and res.provider != "mock":
                return res
    return await _PROVIDERS["mock"].chat(model=model, system=system, messages=messages)


def available_providers() -> dict:
    return {name: p.available() for name, p in _PROVIDERS.items()}
