# ContextGuardrail

ContextGuardrail is a local-first MVP for reducing AI coding-agent context. It scans a repo, builds a lightweight code graph, selects relevant files for a prompt, prevents replaying already-sent files, caches repeated asks, and reports estimated token/cost savings.

## Install locally

```bash
cd /Users/homesachin/Desktop/zoneone/contextguardrail
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional advanced parsers and semantic ranking:

```bash
pip install -e ".[treesitter]"
pip install -e ".[embeddings]"
pip install -e ".[all]"
```

## Use

```bash
contextguardrail init
contextguardrail index /path/to/repo
contextguardrail ask "Where is authentication handled?"
contextguardrail pack "Where is authentication handled?"
contextguardrail diff "Where is authentication handled?"
contextguardrail explain "Where is authentication handled?"
contextguardrail inspect app.py
contextguardrail related app.py
contextguardrail doctor
contextguardrail stats
contextguardrail export
contextguardrail clean
```

All state is stored in the indexed repo under `.contextguardrail/`.

## MVP Features

- Repo scanner with incremental hashing
- Supported file scanning for `.py`, `.md`, `.css`, `.js`, `.html`, `.txt`, `.env`, `Dockerfile`, `.example`, and `.json`
- Python AST parser for imports, classes, functions, and summaries
- Lightweight JS, HTML, and CSS parser for functions, linked assets, tags, IDs, classes, and selectors
- Lightweight dependency graph
- Context selector using prompt keywords, graph metadata, file type boosts, exact keyword matching, and weak-match pruning
- Token counting with `tiktoken` when available, word-count fallback otherwise
- Semantic cache for repeated prompt and selected-file sets
- Replay prevention so already-sent files are skipped unless changed
- Context diffing via file hashes
- Cost observability through `contextguardrail stats`
- AI-ready context packs for Codex, Copilot, Claude, and ChatGPT through `contextguardrail pack`
- `markdown`, `json`, and `xml` pack output formats
- Hard context budgets with `--max-tokens`
- Optional redaction for secrets and local policy files
- Git diff, PR range, memory, inspect, related, benchmark, batch, and local API workflows
- Tree-sitter parser backend when `contextguardrail[treesitter]` is installed
- Semantic ranking with local embeddings when `contextguardrail[embeddings]` is installed
- Ranking v2 blends keyword/symbol matches, semantic similarity, graph signals, git changes, recency, and churn
- Blast radius analysis for affected files, APIs, and tests
- Prompt optimizer and LLM router
- Heatmap and upgraded repo doctor for token hot spots

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

## AI Tool Workflow

Use ContextGuardrail before opening a large task in Codex, Copilot, Claude, or ChatGPT:

```bash
contextguardrail index .
contextguardrail ask "Which files control page styling?"
contextguardrail pack "Which files control page styling?" --format markdown
contextguardrail pack "Which files control page styling?" --format json
contextguardrail pack "Which files control page styling?" --format xml
```

`ask` prints the files to inspect first, plus raw vs optimized token estimates. `pack` prints an AI-ready bundle with selected files, scores, reasons, and summaries. Add `--full-files` when you want a copy/paste bundle containing the selected source content too:

```bash
contextguardrail pack "Where is the contact form handled?" --full-files
```

For follow-up prompts, use:

```bash
contextguardrail diff "Where is the contact form handled?"
```

That shows only selected files that changed since the prompt was last sent.

Useful advanced commands:

```bash
contextguardrail explain "Add Redis cache to user API"
contextguardrail optimize-prompt "Add Redis cache to user API"
contextguardrail router "Refactor auth architecture"
contextguardrail blast-radius app/models.py
contextguardrail heatmap
contextguardrail inspect app/main.py
contextguardrail related templates/index.html
contextguardrail pr origin/main...HEAD
contextguardrail benchmark prompts.txt
contextguardrail batch tasks.json
contextguardrail memory
contextguardrail doctor
contextguardrail instructions
contextguardrail orchestrate "Add OAuth support"
contextguardrail langgraph-template
contextguardrail neo4j-export
contextguardrail serve
```

Create `.contextguardrailignore` to exclude files from indexing, and `.contextguardrailpolicy.json` for simple local policy controls:

```json
{
  "allow_secrets": false,
  "max_file_tokens": 50000,
  "forbidden_paths": ["secrets/**"]
}
```


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
