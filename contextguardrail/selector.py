from __future__ import annotations

import itertools
import re
from pathlib import Path

from contextguardrail.config import DEFAULT_BUDGET
from contextguardrail.gitutils import changed_files, file_commit_count, file_recency
from contextguardrail.graph import load_graph
from contextguardrail.semantic import cosine_similarity
from contextguardrail.storage import connect


WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
STOPWORDS = {
    "add",
    "and",
    "are",
    "can",
    "control",
    "controls",
    "does",
    "file",
    "files",
    "for",
    "how",
    "into",
    "page",
    "pages",
    "the",
    "this",
    "to",
    "what",
    "where",
    "which",
    "with",
}
ALIASES = {
    "handled": "submit",
    "handles": "submit",
    "handling": "submit",
    "styling": "style",
    "styled": "style",
    "styles": "style",
}


def prompt_terms(prompt: str) -> set[str]:
    terms = set()
    for word in WORD_RE.findall(prompt):
        term = ALIASES.get(word.lower(), word.lower())
        if len(term) > 2 and term not in STOPWORDS:
            terms.add(term)
    return terms


def score_row(row, terms: set[str]) -> int:
    path = row["path"].lower()
    keywords = set(row["keywords"].lower().splitlines())
    symbols = set(row["classes"].lower().splitlines()) | set(row["functions"].lower().splitlines())
    summary_terms = {word.lower() for word in WORD_RE.findall(row["summary"])}

    score = sum(5 for term in terms if term in path)
    score += sum(3 for term in terms if term in symbols)
    score += sum(2 for term in terms if term in keywords)
    score += sum(1 for term in terms if term in summary_terms)

    compact_text = re.sub(
        r"[^a-z0-9]+",
        "",
        "\n".join([row["path"], row["summary"], row["keywords"], row["classes"], row["functions"]]).lower(),
    )
    for ordered_terms in itertools.permutations(terms, 2):
        if "".join(ordered_terms) in compact_text:
            score += 6
            break

    if {"style", "css"} & terms and row["path"].endswith(".css"):
        score += 8
    if {"docker", "container", "image"} & terms and row["path"].lower().endswith("dockerfile"):
        score += 8
    if any(term in row["path"].lower() for term in ("auth", "user", "api", "cache", "config", "setting")):
        score += 1
    return score


def rank_score(row, terms: set[str], prompt: str, graph, git_changed: set[str], repo: str | Path) -> tuple[float, list[str]]:
    keyword_score = float(score_row(row, terms))
    semantic_score = cosine_similarity(prompt, "\n".join([row["path"], row["summary"], row["keywords"]])) * 25
    if terms == {"style"} and not row["path"].endswith(".css") and "style" not in row["path"].lower():
        keyword_score *= 0.2
        semantic_score *= 0.2
    graph_score = 0.0
    if row["path"] in graph and (keyword_score >= 3 or semantic_score >= 3 or row["path"] in git_changed):
        graph_score = min(10.0, graph.degree(row["path"]) * 0.75)
        if any(neighbor in git_changed for neighbor in set(graph.successors(row["path"])) | set(graph.predecessors(row["path"]))):
            graph_score += 6
    git_score = 12.0 if row["path"] in git_changed else 0.0
    recency_score = file_recency(repo, row["path"]) * 8
    churn_score = min(6.0, file_commit_count(repo, row["path"]) * 0.6)
    if keyword_score < 1 and semantic_score < 1 and not git_score:
        recency_score = 0.0
        churn_score = 0.0
    total = keyword_score + semantic_score + graph_score + git_score + recency_score + churn_score
    reasons = [
        f"keyword={keyword_score:.1f}",
        f"semantic={semantic_score:.1f}",
        f"graph={graph_score:.1f}",
        f"git={git_score:.1f}",
        f"recency={recency_score:.1f}",
        f"churn={churn_score:.1f}",
    ]
    return total, reasons


def explain_row(row, terms: set[str]) -> str:
    path = row["path"].lower()
    keywords = set(row["keywords"].lower().splitlines())
    symbols = set(row["classes"].lower().splitlines()) | set(row["functions"].lower().splitlines())
    reasons = []
    path_hits = sorted(term for term in terms if term in path)
    symbol_hits = sorted(term for term in terms if term in symbols)
    keyword_hits = sorted(term for term in terms if term in keywords)
    if path_hits:
        reasons.append("path: " + ", ".join(path_hits))
    if symbol_hits:
        reasons.append("symbol: " + ", ".join(symbol_hits))
    if keyword_hits:
        reasons.append("keyword: " + ", ".join(keyword_hits[:5]))
    if {"style", "css"} & terms and row["path"].endswith(".css"):
        reasons.append("stylesheet")
    if {"docker", "container", "image"} & terms and row["path"].lower().endswith("dockerfile"):
        reasons.append("dockerfile")
    return "; ".join(reasons) or "related keywords"


def prune_weak_matches(candidates: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    if not candidates:
        return []
    top_score = candidates[0][0]
    cutoff = max(2, int(top_score * 0.35))
    return [(score, item) for score, item in candidates if score >= cutoff]


def select_context(
    repo: str | Path,
    prompt: str,
    budget: int = DEFAULT_BUDGET,
    exclude_unchanged: dict[str, str] | None = None,
) -> tuple[list[dict], int]:
    terms = prompt_terms(prompt)
    exclude_unchanged = exclude_unchanged or {}
    graph = load_graph(repo)
    git_changed = changed_files(repo)
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
        score, rank_reasons = rank_score(merged, terms, prompt, graph, git_changed, repo)
        if score > 0:
            merged["score"] = score
            merged["reason"] = explain_row(merged, terms) + "; " + ", ".join(rank_reasons)
            candidates.append((score, merged))

    candidates.sort(key=lambda item: (-item[0], item[1]["tokens"], item[1]["path"]))
    ranked_candidates = candidates
    candidates = prune_weak_matches(ranked_candidates)
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
        selected = [item for _, item in ranked_candidates[:5]]
    return selected, raw_tokens
