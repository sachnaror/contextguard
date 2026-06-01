from __future__ import annotations

from pathlib import Path


STATE_DIR = ".contextguardrail"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BUDGET = 8_000

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".contextguardrail",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

CODE_EXTENSIONS = {
    ".py",
    ".md",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".txt",
    ".env",
    ".example",
    ".json",
    ".yaml",
    ".yml",
    ".tf",
    ".tfvars",
    ".sql",
    ".go",
    ".java",
    ".rb",
    ".php",
}

CODE_FILENAMES = {
    "dockerfile",
}


def repo_root(path: str | Path = ".") -> Path:
    return Path(path).expanduser().resolve()


def state_dir(path: str | Path = ".") -> Path:
    return repo_root(path) / STATE_DIR


def ensure_state(path: str | Path = ".") -> Path:
    root = state_dir(path)
    (root / "cache").mkdir(parents=True, exist_ok=True)
    (root / "summaries").mkdir(parents=True, exist_ok=True)
    return root
