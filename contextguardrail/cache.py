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
