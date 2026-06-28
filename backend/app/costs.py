"""Grobe Kostenschätzung pro Modell (USD je 1 Mio. Tokens).

Werte sind Richtwerte und können sich ändern – sie dienen der Budget-Kontrolle,
nicht der centgenauen Abrechnung. Anpassbar."""

# (input_pro_1M, output_pro_1M) in USD
PRICES = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (0.8, 4.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4o": (2.5, 10.0),
    "gpt-4": (10.0, 30.0),
    "o1": (15.0, 60.0),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.0),
    "gemini": (0.5, 1.5),
    "mistral-large": (2.0, 6.0),
    "mistral": (0.25, 0.75),
}
DEFAULT = (3.0, 15.0)


def _rate(model: str):
    m = (model or "").lower()
    for key, price in PRICES.items():
        if key in m:
            return price
    if m.startswith("claude"):
        return PRICES["claude-sonnet"]
    if m in ("mock", "") or "llama" in m or "qwen" in m or "mistral" in m:
        return (0.0, 0.0)  # lokal/mock = kostenlos
    return DEFAULT


def estimate(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = _rate(model)
    return round((input_tokens / 1_000_000) * pin + (output_tokens / 1_000_000) * pout, 6)
