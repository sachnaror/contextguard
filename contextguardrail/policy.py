from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any

from contextguardrail.config import STATE_DIR

DEFAULT_IGNORE = [
    ".git/**",
    ".venv/**",
    "venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    f"{STATE_DIR}/**",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.pdf",
    "*.zip",
    "*.sqlite",
    "*.db",
    "*.pyc",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"),
    re.compile(r"(?i)(aws_access_key_id|aws_secret_access_key)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{12,})"),
    re.compile(r"(?i)(mongodb(?:\+srv)?://[^\s'\"]+)"),
    re.compile(r"(?i)(postgres(?:ql)?://[^\s'\"]+)"),
]


def ignore_file(repo: str | Path) -> Path:
    return Path(repo) / ".contextguardrailignore"


def policy_file(repo: str | Path) -> Path:
    return Path(repo) / ".contextguardrailpolicy.json"


def load_ignore_patterns(repo: str | Path) -> list[str]:
    path = ignore_file(repo)
    patterns = list(DEFAULT_IGNORE)
    if path.exists():
        patterns.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(Path(rel_path).name, pattern) for pattern in patterns)


def load_policy(repo: str | Path) -> dict[str, Any]:
    path = policy_file(repo)
    if not path.exists():
        return {"allow_secrets": False, "max_file_tokens": 50_000, "forbidden_paths": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "allow_secrets": bool(data.get("allow_secrets", False)),
        "max_file_tokens": int(data.get("max_file_tokens", 50_000)),
        "forbidden_paths": list(data.get("forbidden_paths", [])),
    }


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(redact_match, redacted)
    return redacted


def has_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def redact_match(match: re.Match) -> str:
    value = match.group(0)
    if "://" in value:
        return "<REDACTED_URL>"
    if len(match.groups()) >= 2:
        return f"{match.group(1)}=<REDACTED>"
    return "<REDACTED>"
