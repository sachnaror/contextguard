from __future__ import annotations

from pathlib import Path

from contextguardrail.budget import cost_usd
from contextguardrail.storage import load_stats, save_stats


def record_request(
    repo: str | Path,
    raw_tokens: int,
    optimized_tokens: int,
    cache_hit: bool = False,
) -> dict:
    stats = load_stats(repo)
    saved = max(0, raw_tokens - optimized_tokens)
    stats["requests"] += 1
    stats["raw_tokens"] += raw_tokens
    stats["optimized_tokens"] += optimized_tokens
    stats["input_tokens_saved"] += saved
    stats["estimated_cost_saved"] = round(
        stats.get("estimated_cost_saved", 0.0) + cost_usd(saved), 4
    )
    if cache_hit:
        stats["cache_hits"] += 1
    save_stats(repo, stats)
    return stats


def show_stats(repo: str | Path = ".") -> dict:
    return load_stats(repo)
