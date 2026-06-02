from __future__ import annotations

import math
import os
from collections import Counter
from functools import lru_cache


def cosine_similarity(left: str, right: str) -> float:
    embedding_score = embedding_similarity(left, right)
    if embedding_score is not None:
        return embedding_score
    left_counts = Counter(tokenize(left))
    right_counts = Counter(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    terms = set(left_counts) | set(right_counts)
    dot = sum(left_counts[t] * right_counts[t] for t in terms)
    left_norm = math.sqrt(sum(v * v for v in left_counts.values()))
    right_norm = math.sqrt(sum(v * v for v in right_counts.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def tokenize(text: str) -> list[str]:
    token = []
    tokens = []
    for char in text.lower():
        if char.isalnum() or char in {"_", "-"}:
            token.append(char)
        elif token:
            tokens.extend(split_token("".join(token)))
            token = []
    if token:
        tokens.extend(split_token("".join(token)))
    return [t for t in tokens if len(t) > 2]


def split_token(token: str) -> list[str]:
    parts = token.replace("_", "-").split("-")
    return [part for part in parts if part]


def embedding_similarity(left: str, right: str) -> float | None:
    model = embedding_model()
    if model is None:
        return None
    try:
        vectors = model.encode([left, right], normalize_embeddings=True)
    except Exception:
        return None
    return float(sum(a * b for a, b in zip(vectors[0], vectors[1])))


@lru_cache(maxsize=1)
def embedding_model():
    if os.environ.get("CONTEXTGUARDRAIL_USE_EMBEDDINGS") != "1":
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None

    try:
        return SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        return None
