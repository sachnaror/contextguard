# ContextGuardrail

ContextGuardrail is a local-first MVP for reducing AI coding-agent context. It scans a repo, builds a lightweight code graph, selects relevant files for a prompt, prevents replaying already-sent files, caches repeated asks, and reports estimated token/cost savings.

## Install locally

```bash
cd /Users/homesachin/Desktop/zoneone/contextguardrail
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Use

```bash
contextguardrail init
contextguardrail index /path/to/repo
contextguardrail ask "Where is authentication handled?"
contextguardrail stats
contextguardrail export
contextguardrail clean
```

All state is stored in the indexed repo under `.contextguardrail/`.

## MVP Features

- Repo scanner with incremental hashing
- Supported file scanning for `.py`, `.md`, `.css`, `.js`, `.html`, `.txt`, `.env`, `Dockerfile`, `.example`, and `.json`
- Python AST parser for imports, classes, functions, and summaries
- Lightweight dependency graph
- Context selector using prompt keywords and graph metadata
- Token counting with `tiktoken` when available, word-count fallback otherwise
- Semantic cache for repeated prompt and selected-file sets
- Replay prevention so already-sent files are skipped unless changed
- Context diffing via file hashes
- Cost observability through `contextguardrail stats`

This version intentionally skips dashboards, multi-user support, Neo4j, and agent orchestration.

## Supported Files

ContextGuardrail indexes common application, documentation, config, and deployment files:

```text
.py
.md
.css
.js
.html
.txt
.env
Dockerfile
.example
.json
```

`Dockerfile` is matched by filename, so it works even though it has no extension. `.env` and `.example` files are matched by suffix, which covers files like `.env`, `.env.example`, and `settings.example`.


## Project Layout

```
contextguardrail/
├── pyproject.toml              # Package metadata, dependencies, CLI entrypoints
├── README.md                   # Project documentation and usage guide
├── contextguardrail/
│   ├── scanner.py              # Scan repo and detect files, hashes, changes
│   ├── config.py               # Global settings and configuration loading
│   ├── budget.py               # Token estimation and budget enforcement
│   ├── exporter.py             # Export graph, summaries, and reports
│   ├── graph.py                # Build dependency graph from source code
│   ├── selector.py             # Select most relevant context for a prompt
│   ├── cache.py                # Semantic cache and replay prevention
│   ├── cli.py                  # Main CLI commands exposed to users
│   ├── stats.py                # Usage metrics and cost-saving reports
│   └── storage.py              # SQLite helpers and persistence layer
└── tests/
    └── test_budget.py          # Unit tests for token budgeting logic
```
