# ContextGuard

ContextGuard is a local-first MVP for reducing AI coding-agent context. It scans a repo, builds a lightweight code graph, selects relevant files for a prompt, prevents replaying already-sent files, caches repeated asks, and reports estimated token/cost savings.

## Install locally

```bash
cd /Users/homesachin/Desktop/zoneone/contextguard
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Use

```bash
contextguard init
contextguard index /path/to/repo
contextguard ask "Where is authentication handled?"
contextguard stats
contextguard export
contextguard clean
```

All state is stored in the indexed repo under `.contextguard/`.

## MVP Features

- Repo scanner with incremental hashing
- Python AST parser for imports, classes, functions, and summaries
- Lightweight dependency graph
- Context selector using prompt keywords and graph metadata
- Token counting with `tiktoken` when available, word-count fallback otherwise
- Semantic cache for repeated prompt and selected-file sets
- Replay prevention so already-sent files are skipped unless changed
- Context diffing via file hashes
- Cost observability through `contextguard stats`

This version intentionally skips dashboards, multi-user support, Neo4j, and agent orchestration.


## DIR Features

```
contextguard/
├── pyproject.toml              # Package metadata, dependencies, CLI entrypoints
├── README.md                   # Project documentation and usage guide

├── contextguard.egg-info/      # Auto-generated package build metadata
│   ├── PKG-INFO                # Package information used by pip
│   ├── SOURCES.txt             # List of files included in package
│   ├── entry_points.txt        # CLI commands exposed by package
│   ├── requires.txt            # Package dependencies
│   ├── top_level.txt           # Top-level package names
│   └── dependency_links.txt    # Legacy dependency references

├── tests/
│   └── test_budget.py          # Unit tests for token budgeting logic

├── .contextguard/              # Local memory store generated per repository
│   ├── hashes.db               # File hashes for incremental indexing
│   ├── repo-brain.json         # Human-readable repository knowledge map
│   ├── code-dna.json           # Machine-readable dependency graph
│   ├── ai-gossip.md            # Plain English repo summary for AI agents
│   ├── cache.db                # Semantic cache for prompt responses
│   ├── graph.db                # Graph relationships between files/functions
│   ├── costs.json              # Token and cost tracking history
│   ├── cache/
│   │   └── summaries/
│   │       ├── 711.md          # Cached summary of indexed file
│   │       ├── 46.md           # Cached summary of indexed file
│   │       └── 74.md           # Cached summary of indexed file

├── contextguard/
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

```
