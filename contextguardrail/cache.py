from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contextguardrail.storage import connect


def cache_key(prompt: str, selected_hash: str, model: str) -> str:
    return hashlib.sha256(f"{prompt}\n{selected_hash}\n{model}".encode()).hexdigest()


def selected_files_hash(files: list[dict]) -> str:
    payload = "|".join(f"{item['path']}:{item['hash']}" for item in files)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_cache(repo: str | Path, key: str) -> str | None:
    with connect(repo, "cache.db") as db:
        row = db.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
    return row["response"] if row else None


def set_cache(repo: str | Path, key: str, response: str) -> None:
    with connect(repo, "cache.db") as db:
        db.execute(
            "INSERT OR REPLACE INTO cache(key, response) VALUES (?, ?)",
            (key, response),
        )


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().lower().encode()).hexdigest()


def already_sent(repo: str | Path, prompt: str) -> dict[str, str]:
    with connect(repo, "cache.db") as db:
        row = db.execute("SELECT file_hashes FROM replay WHERE prompt_hash = ?", (prompt_hash(prompt),)).fetchone()
    return json.loads(row["file_hashes"]) if row else {}


def replay_entries(repo: str | Path) -> list[dict]:
    with connect(repo, "cache.db") as db:
        rows = db.execute("SELECT prompt_hash, files, file_hashes, created_at FROM replay ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def remember_topic(repo: str | Path, prompt: str, terms: set[str], files: list[dict]) -> None:
    key = hashlib.sha256("|".join(sorted(terms)).encode()).hexdigest()
    with connect(repo, "cache.db") as db:
        ensure_topic_table(db)
        db.execute(
            """
            INSERT INTO topic_memory(topic_key, prompt, terms, files, hits)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(topic_key) DO UPDATE SET
              prompt=excluded.prompt,
              terms=excluded.terms,
              files=excluded.files,
              hits=topic_memory.hits + 1,
              updated_at=CURRENT_TIMESTAMP
            """,
            (key, prompt, json.dumps(sorted(terms)), json.dumps([item["path"] for item in files])),
        )


def topic_entries(repo: str | Path) -> list[dict]:
    with connect(repo, "cache.db") as db:
        ensure_topic_table(db)
        rows = db.execute("SELECT topic_key, prompt, terms, files, hits, updated_at FROM topic_memory ORDER BY hits DESC, updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def ensure_topic_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_memory(
            topic_key TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            terms TEXT NOT NULL,
            files TEXT NOT NULL,
            hits INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def remember_sent(repo: str | Path, prompt: str, files: list[dict]) -> None:
    file_hashes = {item["path"]: item["hash"] for item in files}
    with connect(repo, "cache.db") as db:
        db.execute(
            "INSERT OR REPLACE INTO replay(prompt_hash, files, file_hashes) VALUES (?, ?, ?)",
            (prompt_hash(prompt), json.dumps(list(file_hashes)), json.dumps(file_hashes)),
        )


def clean_cache(repo: str | Path) -> int:
    with connect(repo, "cache.db") as db:
        count = db.execute("SELECT COUNT(*) AS count FROM cache").fetchone()["count"]
        db.execute("DELETE FROM cache")
        db.execute("DELETE FROM replay")
    return int(count)
