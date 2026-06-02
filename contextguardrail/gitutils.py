from __future__ import annotations

import subprocess
import time
from pathlib import Path


def run_git(repo: str | Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    return result.stdout.strip()


def changed_files(repo: str | Path, revision_range: str = "HEAD") -> set[str]:
    if ".." in revision_range:
        output = run_git(repo, ["diff", "--name-only", revision_range])
    else:
        output = run_git(repo, ["diff", "--name-only", revision_range])
        output += "\n" + run_git(repo, ["diff", "--name-only", "--cached"])
    return {line.strip() for line in output.splitlines() if line.strip()}


def file_recency(repo: str | Path, path: str) -> float:
    output = run_git(repo, ["log", "-1", "--format=%ct", "--", path])
    if not output.isdigit():
        return 0.0
    age_days = max(0.0, (time.time() - int(output)) / 86_400)
    return 1.0 / (1.0 + age_days)


def file_commit_count(repo: str | Path, path: str, days: int = 90) -> int:
    output = run_git(repo, ["log", f"--since={days} days ago", "--format=%H", "--", path])
    return len([line for line in output.splitlines() if line.strip()])


def file_authors(repo: str | Path, path: str) -> list[str]:
    output = run_git(repo, ["log", "--format=%an", "--", path])
    seen = []
    for line in output.splitlines():
        if line and line not in seen:
            seen.append(line)
    return seen[:5]
