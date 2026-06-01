from __future__ import annotations

import re
from pathlib import Path

from contextguardrail.config import DEFAULT_BUDGET
from contextguardrail.storage import connect


WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def prompt_terms(prompt: str) -> set[str]:
    return {word.lower() for word in WORD_RE.findall(prompt) if len(word) > 2}


def score_row(row, terms: set[str]) -> int:
    haystack = "\n".join(
        [row["path"], row["summary"], row["keywords"], row["classes"], row["functions"]]
    ).lower()
    score = sum(5 for term in terms if term in row["path"].lower())
    score += sum(3 for term in terms if term in row["classes"].lower() or term in row["functions"].lower())
    score += sum(1 for term in terms if term in haystack)
    if any(term in row["path"].lower() for term in ("auth", "user", "api", "cache", "config", "setting")):
        score += 1
    return score


def select_context(
    repo: str | Path,
    prompt: str,
    budget: int = DEFAULT_BUDGET,
    exclude_unchanged: dict[str, str] | None = None,
) -> tuple[list[dict], int]:
    terms = prompt_terms(prompt)
    exclude_unchanged = exclude_unchanged or {}
    with connect(repo, "hashes.db") as files_db, connect(repo, "graph.db") as graph_db:
        rows = files_db.execute(
            "SELECT path, hash, tokens, summary FROM files ORDER BY path"
        ).fetchall()
        symbols = {
            row["path"]: row
            for row in graph_db.execute(
                "SELECT path, classes, functions, keywords FROM symbols"
            ).fetchall()
        }

    candidates = []
    raw_tokens = 0
    for row in rows:
        raw_tokens += int(row["tokens"])
        if exclude_unchanged.get(row["path"]) == row["hash"]:
            continue
        symbol = symbols.get(row["path"])
        merged = {
            "path": row["path"],
            "hash": row["hash"],
            "tokens": int(row["tokens"]),
            "summary": row["summary"],
            "classes": symbol["classes"] if symbol else "",
            "functions": symbol["functions"] if symbol else "",
            "keywords": symbol["keywords"] if symbol else "",
        }
        score = score_row(merged, terms)
        if score > 0:
            candidates.append((score, merged))

    candidates.sort(key=lambda item: (-item[0], item[1]["tokens"], item[1]["path"]))
    selected = []
    used = 0
    for _, item in candidates:
        summary_tokens = max(30, min(item["tokens"], int(item["tokens"] * 0.25)))
        if selected and used + summary_tokens > budget:
            continue
        selected.append(item)
        used += summary_tokens
        if used >= budget:
            break

    if not selected:
        selected = [item for _, item in candidates[:5]]
    return selected, raw_tokens
