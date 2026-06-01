from __future__ import annotations

import hashlib
from pathlib import Path

from contextguardrail.budget import estimate_tokens
from contextguardrail.config import CODE_EXTENSIONS, SKIP_DIRS, ensure_state, repo_root
from contextguardrail.graph import parse_file, summarize_file, upsert_symbols
from contextguardrail.storage import connect, init_storage


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def should_scan(path: Path, rel_path: Path) -> bool:
    if any(part in SKIP_DIRS for part in rel_path.parts):
        return False
    return path.is_file() and path.suffix.lower() in CODE_EXTENSIONS


def iter_files(root: Path):
    for path in root.rglob("*"):
        if should_scan(path, path.relative_to(root)):
            yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def index_repo(path: str | Path = ".", incremental: bool = False) -> dict[str, int]:
    root = repo_root(path)
    state = ensure_state(root)
    init_storage(root)

    scanned = changed = skipped = raw_tokens = 0
    for file_path in iter_files(root):
        rel_path = file_path.relative_to(root).as_posix()
        digest = file_hash(file_path)
        stat = file_path.stat()
        with connect(root, "hashes.db") as db:
            existing = db.execute("SELECT hash FROM files WHERE path = ?", (rel_path,)).fetchone()
        if incremental and existing and existing["hash"] == digest:
            skipped += 1
            continue

        text = read_text(file_path)
        tokens = estimate_tokens(text)
        parsed = parse_file(file_path, rel_path, text)
        summary = summarize_file(rel_path, text, parsed)
        summary_path = state / "summaries" / f"{hashlib.sha256(rel_path.encode()).hexdigest()}.md"
        summary_path.write_text(summary + "\n", encoding="utf-8")

        with connect(root, "hashes.db") as db:
            db.execute(
                """
                INSERT INTO files(path, hash, size, mtime, tokens, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  hash=excluded.hash,
                  size=excluded.size,
                  mtime=excluded.mtime,
                  tokens=excluded.tokens,
                  summary=excluded.summary,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (rel_path, digest, stat.st_size, stat.st_mtime, tokens, summary),
            )
        upsert_symbols(root, rel_path, parsed)
        scanned += 1
        changed += 1
        raw_tokens += tokens

    return {
        "files_scanned": scanned,
        "files_changed": changed,
        "files_skipped": skipped,
        "raw_tokens": raw_tokens,
    }
