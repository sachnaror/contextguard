from __future__ import annotations


def estimate_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        import tiktoken

        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        return int(len(text.split()) * 1.3)


def cost_usd(input_tokens: int, output_tokens: int = 0) -> float:
    input_cost_per_million = 0.15
    output_cost_per_million = 0.60
    return (input_tokens / 1_000_000 * input_cost_per_million) + (
        output_tokens / 1_000_000 * output_cost_per_million
    )
