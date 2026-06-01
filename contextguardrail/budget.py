from __future__ import annotations

MODEL_COSTS = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "gemini-1.5-flash": (0.35, 1.05),
    "gemini-1.5-pro": (3.50, 10.50),
    "local": (0.0, 0.0),
}


def estimate_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        import tiktoken

        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        return int(len(text.split()) * 1.3)


def cost_usd(input_tokens: int, output_tokens: int = 0, model: str = "gpt-4o-mini") -> float:
    input_cost_per_million, output_cost_per_million = MODEL_COSTS.get(model, MODEL_COSTS["gpt-4o-mini"])
    return (input_tokens / 1_000_000 * input_cost_per_million) + (
        output_tokens / 1_000_000 * output_cost_per_million
    )
