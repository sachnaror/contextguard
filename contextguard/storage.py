from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from contextguard.config import ensure_state


def db_path(repo: str | Path, name: str) -> Path:
    return ensure_state(repo) / name


def connect(repo: str | Path, name: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path(repo, name))
    connection.row_factory = sqlite3.Row
    return connection


def init_storage(repo: str | Path = ".") -> None:
    ensure_state(repo)
    with connect(repo, "hashes.db") as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS files(
                path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                tokens INTEGER NOT NULL,
                summary TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    with connect(repo, "graph.db") as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS symbols(
                path TEXT PRIMARY KEY,
                imports TEXT NOT NULL,
                classes TEXT NOT NULL,
                functions TEXT NOT NULL,
                keywords TEXT NOT NULL
            )
            """
        )
    with connect(repo, "cache.db") as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS cache(
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS replay(
                prompt_hash TEXT PRIMARY KEY,
                files TEXT NOT NULL,
                file_hashes TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    stats_file(repo).write_text(
        json.dumps(load_stats(repo), indent=2) + "\n", encoding="utf-8"
    )


def stats_file(repo: str | Path) -> Path:
    return ensure_state(repo) / "costs.json"


def load_stats(repo: str | Path) -> dict[str, Any]:
    path = stats_file(repo)
    if not path.exists():
        return {
            "requests": 0,
            "input_tokens_saved": 0,
            "output_tokens_saved": 0,
            "cache_hits": 0,
            "raw_tokens": 0,
            "optimized_tokens": 0,
            "estimated_cost_saved": 0.0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_stats(repo: str | Path, stats: dict[str, Any]) -> None:
    stats_file(repo).write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
