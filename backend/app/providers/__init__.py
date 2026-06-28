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


async def chat(provider: str, model: str, system: str, messages: list) -> LLMResult:
    """Ruft das gewählte Modell auf. Fällt bei fehlendem Key/Fehler auf Mock zurück."""
    impl = _PROVIDERS.get(provider, _PROVIDERS["mock"])
    return await impl.chat(model=model, system=system, messages=messages)


def available_providers() -> dict:
    return {name: p.available() for name, p in _PROVIDERS.items()}
