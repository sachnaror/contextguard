from __future__ import annotations

import json
import os
import subprocess
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import typer
from rich.console import Console
from rich.table import Table

from contextguardrail.budget import cost_usd
from contextguardrail.blast import blast_radius
from contextguardrail.cache import (
    already_sent,
    cache_key,
    clean_cache,
    get_cache,
    replay_entries,
    remember_sent,
    remember_topic,
    selected_files_hash,
    set_cache,
    topic_entries,
)
from contextguardrail.budget import MODEL_COSTS
from contextguardrail.config import DEFAULT_BUDGET, DEFAULT_MODEL, CODE_EXTENSIONS, CODE_FILENAMES, ensure_state, repo_root
from contextguardrail.exporter import export_repo
from contextguardrail.gitutils import file_authors, file_commit_count
from contextguardrail.graph import graph_counts, load_graph
from contextguardrail.optimizer import optimize_prompt
from contextguardrail.policy import has_secret, redact_text
from contextguardrail.scanner import index_repo
from contextguardrail.selector import prompt_terms, select_context
from contextguardrail.stats import record_request, show_stats
from contextguardrail.storage import connect, init_storage

app = typer.Typer(help="Local-first token firewall for AI coding agents.")
console = Console()


@app.command()
def init(path: str = typer.Argument(".")):
    """Create .contextguardrail storage for a repo."""
    root = repo_root(path)
    init_storage(root)
    console.print(f"[green]Initialized[/green] {ensure_state(root)}")


@app.command()
def index(
    path: str = typer.Argument("."),
    incremental: bool = typer.Option(False, "--incremental", "-i"),
):
    """Scan a repo and build the local code graph."""
    root = repo_root(path)
    result = index_repo(root, incremental=incremental)
    functions, classes = graph_counts(root)
    console.print(f"Files scanned: [bold]{result['files_scanned']}[/bold]")
    if incremental:
        console.print(f"Files skipped: [bold]{result['files_skipped']}[/bold]")
    console.print(f"Functions: [bold]{functions}[/bold]")
    console.print(f"Classes: [bold]{classes}[/bold]")
    console.print("[green]Graph built.[/green]")


@app.command()
def ask(
    prompt: str,
    path: str = typer.Option(".", "--path", "-p"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", "-b"),
    include_replay: bool = typer.Option(False, "--include-replay"),
):
    """Select optimized context for a coding prompt."""
    root = repo_root(path)
    base_selected, raw_tokens = select_context(root, prompt, budget=budget)
    base_optimized = estimated_optimized_tokens(base_selected)
    direct_answer = direct_file_answer(prompt, base_selected)
    key = cache_key(prompt, selected_files_hash(base_selected), model)
    cached = get_cache(root, key)
    if cached is not None:
        console.print(cached.replace("Cache: miss", "Cache: hit"), markup=False)
        record_request(root, raw_tokens, 0, cache_hit=True)
        return

    replay = {} if include_replay else already_sent(root, prompt)
    selected, raw_tokens = select_context(root, prompt, budget=budget, exclude_unchanged=replay)
    optimized_tokens = sum(max(30, min(item["tokens"], int(item["tokens"] * 0.25))) for item in selected)

    if direct_answer:
        lines = [direct_answer]
    else:
        lines = ["Files selected:", ""]
        if selected:
            lines.extend(format_selected_files(selected))
        else:
            lines.append("No changed files since this prompt was last sent.")
        lines.extend(
            [
                "",
                f"Raw Tokens: {raw_tokens:,}",
                f"Optimized Tokens: {optimized_tokens:,}",
                f"Savings: {savings_percent(raw_tokens, optimized_tokens):.1f}%",
                f"Estimated Cost Saved: ${cost_usd(max(0, raw_tokens - optimized_tokens)):.4f}",
            ]
        )
        lines.append("Cache: miss")
    if base_optimized == optimized_tokens or not replay:
        set_cache(root, key, "\n".join(lines))
    remember_sent(root, prompt, selected)
    remember_topic(root, prompt, prompt_terms(prompt), selected)
    record_request(root, raw_tokens, optimized_tokens, cache_hit=False)
    console.print("\n".join(lines), markup=False)


@app.command()
def analyze(
    prompt: str,
    path: str = typer.Option(".", "--path", "-p"),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", "-b"),
):
    """Killer-demo alias for ask with cost framing."""
    ask(prompt=prompt, path=path, budget=budget)


@app.command()
def pack(
    prompt: str,
    path: str = typer.Option(".", "--path", "-p"),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", "-b"),
    max_tokens: int | None = typer.Option(None, "--max-tokens"),
    output_format: str = typer.Option("markdown", "--format", "-f"),
    compression: str = typer.Option("summary", "--compression", "-c"),
    full_files: bool = typer.Option(False, "--full-files"),
    allow_secrets: bool = typer.Option(False, "--allow-secrets"),
):
    """Print an AI-ready context bundle for Codex, Copilot, Claude, or ChatGPT."""
    root = repo_root(path)
    token_budget = max_tokens or budget
    selected, raw_tokens = select_context(root, prompt, budget=token_budget)
    selected, optimized_tokens = enforce_hard_budget(selected, token_budget)
    bundle = build_context_bundle(root, prompt, selected, raw_tokens, optimized_tokens, compression, full_files, allow_secrets)
    console.print(render_bundle(bundle, output_format), markup=False)


@app.command()
def diff(
    prompt_or_range: str,
    path: str = typer.Option(".", "--path", "-p"),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", "-b"),
):
    """Show changed context for a prompt, or files changed in a git range."""
    root = repo_root(path)
    if ".." in prompt_or_range:
        files = git_changed_files(root, prompt_or_range)
        console.print("Git changed files:")
        for file in files:
            console.print(f"- {file}")
        return
    replay = already_sent(root, prompt_or_range)
    selected, raw_tokens = select_context(root, prompt_or_range, budget=budget, exclude_unchanged=replay)
    console.print("Changed context files:")
    if selected:
        for line in format_selected_files(selected):
            console.print(f"- {line}", markup=False)
    else:
        console.print("- No selected files changed since this prompt was last sent.")
    console.print(f"Raw tokens: {raw_tokens:,}")
    console.print(f"Diff tokens: {estimated_optimized_tokens(selected):,}")


@app.command()
def explain(
    prompt: str,
    path: str = typer.Option(".", "--path", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Show ranked candidate files and why they match before making a pack."""
    selected, raw_tokens = select_context(repo_root(path), prompt, budget=DEFAULT_BUDGET)
    console.print(f"Terms: {', '.join(sorted(prompt_terms(prompt)))}")
    console.print(f"Raw tokens: {raw_tokens:,}")
    for item in selected[:limit]:
        console.print(f"- {item['path']} [score={item.get('score', 0)}; {item.get('reason', 'selected')}]", markup=False)


@app.command()
def doctor(path: str = typer.Argument(".")):
    """Validate index health, parser coverage, optional backends, and policy files."""
    root = repo_root(path)
    init_storage(root)
    with connect(root, "hashes.db") as db:
        indexed = db.execute("SELECT COUNT(*) AS count FROM files").fetchone()["count"]
        expensive = db.execute("SELECT path, tokens FROM files ORDER BY tokens DESC LIMIT 5").fetchall()
    stats_data = show_stats(root)
    console.print("ContextGuardrail Doctor")
    console.print(f"- Repo: {root}")
    console.print(f"- Indexed files: {indexed}")
    console.print(f"- Supported extensions: {', '.join(sorted(CODE_EXTENSIONS))}")
    console.print(f"- Supported filenames: {', '.join(sorted(CODE_FILENAMES))}")
    console.print(f"- Ignore file: {(root / '.contextguardrailignore').exists()}")
    console.print(f"- Policy file: {(root / '.contextguardrailpolicy.json').exists()}")
    console.print(f"- Tree-sitter available: {module_available('tree_sitter')}")
    console.print(f"- Tree-sitter language pack available: {module_available('tree_sitter_language_pack')}")
    embeddings_installed = module_available("sentence_transformers")
    embeddings_enabled = os.environ.get("CONTEXTGUARDRAIL_USE_EMBEDDINGS") == "1"
    console.print(f"- Local embeddings installed: {embeddings_installed}")
    console.print(f"- Local embeddings enabled: {embeddings_enabled}")
    console.print(f"- Requests tracked: {stats_data.get('requests', 0):,}")
    console.print(f"- Input tokens saved: {stats_data.get('input_tokens_saved', 0):,}")
    console.print("- Potential token hot spots:")
    for row in expensive:
        console.print(f"  - {row['path']}: {row['tokens']:,} tokens")


@app.command()
def inspect(file: str, path: str = typer.Option(".", "--path", "-p")):
    """Inspect one indexed file: summary, symbols, tokens, dependencies, dependents."""
    root = repo_root(path)
    rel = Path(file).as_posix()
    with connect(root, "hashes.db") as files_db, connect(root, "graph.db") as graph_db:
        row = files_db.execute("SELECT * FROM files WHERE path = ?", (rel,)).fetchone()
        symbols = graph_db.execute("SELECT * FROM symbols WHERE path = ?", (rel,)).fetchone()
    if not row:
        console.print(f"[red]Not indexed:[/red] {rel}")
        raise typer.Exit(1)
    graph = load_graph(root)
    console.print(f"File: {rel}")
    console.print(f"Tokens: {row['tokens']:,}")
    console.print(f"Hash: {row['hash']}")
    console.print(f"Recent commits: {file_commit_count(root, rel)}")
    authors = file_authors(root, rel)
    console.print(f"Authors: {', '.join(authors) if authors else '-'}")
    console.print(f"Summary:\n{row['summary']}")
    if symbols:
        console.print(f"Imports: {symbols['imports'] or '-'}")
        console.print(f"Classes/Selectors: {symbols['classes'] or '-'}")
        console.print(f"Functions/Routes/Tags: {symbols['functions'] or '-'}")
    console.print("Dependencies: " + ", ".join(sorted(graph.successors(rel))) if rel in graph else "Dependencies: -")
    console.print("Dependents: " + ", ".join(sorted(graph.predecessors(rel))) if rel in graph else "Dependents: -")


@app.command()
def related(file: str, path: str = typer.Option(".", "--path", "-p")):
    """Show graph neighbors for a file."""
    graph = load_graph(repo_root(path))
    rel = Path(file).as_posix()
    if rel not in graph:
        console.print(f"[red]Not in graph:[/red] {rel}")
        raise typer.Exit(1)
    console.print(f"Related to {rel}:")
    for node in sorted(set(graph.successors(rel)) | set(graph.predecessors(rel))):
        console.print(f"- {node}")


@app.command("blast-radius")
def blast_radius_command(file: str, path: str = typer.Option(".", "--path", "-p"), depth: int = typer.Option(2, "--depth")):
    """Show dependency blast radius for a file."""
    result = blast_radius(repo_root(path), Path(file).as_posix(), depth=depth)
    console.print(json.dumps(result, indent=2))


@app.command("optimize-prompt")
def optimize_prompt_command(prompt: str, path: str = typer.Option(".", "--path", "-p")):
    """Convert a vague prompt into an AI-ready task brief."""
    selected, _ = select_context(repo_root(path), prompt)
    console.print(optimize_prompt(prompt, selected), markup=False)


@app.command()
def router(prompt: str, path: str = typer.Option(".", "--path", "-p")):
    """Suggest a model based on context size and task complexity."""
    selected, raw_tokens = select_context(repo_root(path), prompt)
    optimized = estimated_optimized_tokens(selected)
    terms = prompt_terms(prompt)
    if optimized < 2_000 and not {"architecture", "refactor", "security"} & terms:
        model = "gpt-4o-mini"
    elif {"architecture", "design", "refactor"} & terms or optimized > 8_000:
        model = "claude-3-5-sonnet"
    else:
        model = "gpt-4o"
    console.print(
        json.dumps(
            {
                "recommended_model": model,
                "raw_tokens": raw_tokens,
                "optimized_tokens": optimized,
                "estimated_cost": round(cost_usd(optimized, 1_000, model), 4),
                "reason": "selected by context size, prompt complexity, and model cost profile",
            },
            indent=2,
        )
    )


@app.command()
def heatmap(path: str = typer.Argument(".")):
    """Show expensive/high-churn context hot spots."""
    root = repo_root(path)
    with connect(root, "hashes.db") as db:
        rows = db.execute("SELECT path, tokens FROM files ORDER BY tokens DESC LIMIT 20").fetchall()
    table = Table(title="ContextGuardrail Heatmap")
    table.add_column("File")
    table.add_column("Tokens", justify="right")
    table.add_column("Recent commits", justify="right")
    table.add_column("Recommendation")
    for row in rows:
        commits = file_commit_count(root, row["path"])
        recommendation = "create permanent summary" if row["tokens"] > 4_000 or commits > 10 else "normal"
        table.add_row(row["path"], f"{row['tokens']:,}", str(commits), recommendation)
    console.print(table)


@app.command()
def orchestrate(prompt: str, path: str = typer.Option(".", "--path", "-p")):
    """Print a local planner/code/review/test orchestration plan."""
    selected, _ = select_context(repo_root(path), prompt)
    console.print("Planner -> Code Agent -> Review Agent -> Test Agent")
    console.print(optimize_prompt(prompt, selected), markup=False)


@app.command("langgraph-template")
def langgraph_template():
    """Print a LangGraph integration template."""
    console.print(
        """from contextguardrail.selector import select_context

def context_node(state):
    files, raw_tokens = select_context('.', state['prompt'])
    return {**state, 'context_files': files, 'raw_tokens': raw_tokens}
""",
        markup=False,
    )


@app.command("neo4j-export")
def neo4j_export(path: str = typer.Argument(".")):
    """Export graph edges in a Neo4j-friendly Cypher file."""
    root = repo_root(path)
    graph = load_graph(root)
    output = ensure_state(root) / "neo4j-import.cypher"
    lines = []
    for source, target in graph.edges():
        lines.append(
            "MERGE (a:File {path:%s}) MERGE (b:File {path:%s}) MERGE (a)-[:DEPENDS_ON]->(b);"
            % (json.dumps(source), json.dumps(target))
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(output)


@app.command()
def memory(path: str = typer.Argument(".")):
    """View replay prevention memory."""
    root = repo_root(path)
    entries = replay_entries(root)
    topics = topic_entries(root)
    if not entries:
        console.print("No replay memory yet.")
    else:
        console.print("Replay memory:")
        for entry in entries:
            files = json.loads(entry["files"])
            console.print(f"- {entry['created_at']} {entry['prompt_hash'][:12]}: {', '.join(files)}")
    if topics:
        console.print("Topic memory:")
        for topic in topics:
            console.print(f"- hits={topic['hits']} terms={topic['terms']} files={topic['files']}")


@app.command()
def redact(file: str):
    """Print a redacted version of a file."""
    text = Path(file).read_text(encoding="utf-8", errors="ignore")
    console.print(redact_text(text))


@app.command("suggest-tests")
def suggest_tests(prompt: str, path: str = typer.Option(".", "--path", "-p")):
    """Find tests likely affected by a prompt."""
    root = repo_root(path)
    selected, _ = select_context(root, prompt)
    names = {Path(item["path"]).stem.lower() for item in selected}
    with connect(root, "hashes.db") as db:
        rows = db.execute("SELECT path FROM files ORDER BY path").fetchall()
    matches = [row["path"] for row in rows if "test" in row["path"].lower() and any(name in row["path"].lower() for name in names)]
    if not matches:
        matches = [row["path"] for row in rows if "test" in row["path"].lower()][:10]
    for match in matches:
        console.print(match)


@app.command()
def instructions(path: str = typer.Argument(".")):
    """Generate Cursor, Copilot, Claude, and Codex instruction files."""
    root = repo_root(path)
    (root / ".cursor").mkdir(exist_ok=True)
    text = "Use `contextguardrail ask` or `contextguardrail pack` before reading broad repository context. Prefer selected files first.\n"
    for target in [root / ".cursor" / "rules", root / "copilot-instructions.md", root / "CLAUDE.md", root / "CODEX.md"]:
        target.write_text(text, encoding="utf-8")
        console.print(target)


@app.command()
def batch(tasks: Path, path: str = typer.Option(".", "--path", "-p"), output_format: str = typer.Option("json", "--format", "-f")):
    """Process many prompts from a JSON or text file and deduplicate selected context."""
    root = repo_root(path)
    raw = tasks.read_text(encoding="utf-8")
    prompts = json.loads(raw) if tasks.suffix == ".json" else [line.strip() for line in raw.splitlines() if line.strip()]
    results = []
    seen = set()
    for prompt in prompts:
        selected, raw_tokens = select_context(root, prompt)
        for item in selected:
            seen.add(item["path"])
        results.append({"prompt": prompt, "files": [item["path"] for item in selected], "raw_tokens": raw_tokens})
    payload = {"tasks": results, "deduped_files": sorted(seen)}
    console.print(json.dumps(payload, indent=2) if output_format == "json" else payload)


@app.command()
def pr(
    revision_range: str = typer.Argument("origin/main...HEAD"),
    path: str = typer.Option(".", "--path", "-p"),
):
    """Generate a changed-file context report for a PR-style git range."""
    root = repo_root(path)
    changed = git_changed_files(root, revision_range)
    graph = load_graph(root)
    impacted = set(changed)
    for file in changed:
        if file in graph:
            impacted.update(graph.successors(file))
            impacted.update(graph.predecessors(file))
    console.print(f"PR range: {revision_range}")
    console.print("Changed files:")
    for file in changed:
        console.print(f"- {file}")
    console.print("Impacted graph neighbors:")
    for file in sorted(impacted - set(changed)):
        console.print(f"- {file}")


@app.command()
def benchmark(tasks: Path, path: str = typer.Option(".", "--path", "-p")):
    """Compare raw repo tokens vs selected context over sample prompts."""
    root = repo_root(path)
    prompts = [line.strip() for line in tasks.read_text(encoding="utf-8").splitlines() if line.strip()]
    table = Table(title="ContextGuardrail Benchmark")
    table.add_column("Prompt")
    table.add_column("Raw", justify="right")
    table.add_column("Optimized", justify="right")
    table.add_column("Savings", justify="right")
    for prompt in prompts:
        selected, raw_tokens = select_context(root, prompt)
        optimized = estimated_optimized_tokens(selected)
        table.add_row(prompt[:50], f"{raw_tokens:,}", f"{optimized:,}", f"{savings_percent(raw_tokens, optimized):.1f}%")
    console.print(table)


@app.command()
def serve(
    path: str = typer.Option(".", "--path", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
):
    """Serve a tiny local HTTP API: /pack?prompt=..."""
    root = repo_root(path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/pack":
                self.send_response(404)
                self.end_headers()
                return
            prompt = parse_qs(parsed.query).get("prompt", [""])[0]
            selected, raw_tokens = select_context(root, prompt)
            bundle = build_context_bundle(root, prompt, selected, raw_tokens, estimated_optimized_tokens(selected), "summary", False, False)
            body = json.dumps(bundle, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    console.print(f"Serving ContextGuardrail on http://{host}:{port}/pack?prompt=...")
    HTTPServer((host, port), Handler).serve_forever()


@app.command()
def stats(path: str = typer.Argument(".")):
    """Show token and cache savings."""
    data = show_stats(repo_root(path))
    table = Table(title="ContextGuardrail Stats")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Requests", f"{data['requests']:,}")
    table.add_row("Input tokens saved", f"{data['input_tokens_saved']:,}")
    table.add_row("Output tokens saved", f"{data['output_tokens_saved']:,}")
    table.add_row("Cache hits", f"{data['cache_hits']:,}")
    table.add_row("Raw tokens observed", f"{data['raw_tokens']:,}")
    table.add_row("Optimized tokens sent", f"{data['optimized_tokens']:,}")
    table.add_row("Estimated cost saved", f"${data['estimated_cost_saved']:.4f}")
    console.print(table)


@app.command("clean")
def clean(path: str = typer.Argument(".")):
    """Clean semantic cache and replay memory."""
    count = clean_cache(repo_root(path))
    console.print(f"[green]Cleaned[/green] {count} cached responses")


@app.command("export")
def export_command(path: str = typer.Argument(".")):
    """Export repo-brain.json, code-dna.json, and ai-gossip.md."""
    files = export_repo(repo_root(path))
    for file in files:
        console.print(file)


def savings_percent(raw_tokens: int, optimized_tokens: int) -> float:
    if raw_tokens <= 0:
        return 0.0
    return max(0.0, (raw_tokens - optimized_tokens) / raw_tokens * 100)


def direct_file_answer(prompt: str, files: list[dict]) -> str | None:
    """Return a terse answer for simple file lookup questions."""
    if not files:
        return None
    text = prompt.lower()
    asks_for_file = "file" in text or "page" in text
    looks_like_lookup = asks_for_file and any(word in text for word in ("which", "where", "what"))
    action_words = (
        "add",
        "build",
        "change",
        "create",
        "debug",
        "fix",
        "implement",
        "refactor",
        "update",
    )
    if not looks_like_lookup or any(word in text for word in action_words):
        return None
    return f"Answer: {files[0]['path']}"


def estimated_optimized_tokens(files: list[dict]) -> int:
    return sum(max(30, min(item["tokens"], int(item["tokens"] * 0.25))) for item in files)


def enforce_hard_budget(files: list[dict], max_tokens: int) -> tuple[list[dict], int]:
    selected = []
    used = 0
    for item in files:
        estimate = max(30, min(item["tokens"], int(item["tokens"] * 0.25)))
        if used + estimate <= max_tokens:
            selected.append(item)
            used += estimate
        elif not selected:
            clipped = dict(item)
            clipped["summary"] = truncate_text(item["summary"], max(400, max_tokens * 4))
            clipped["budget_truncated"] = True
            selected.append(clipped)
            used = max_tokens
            break
    return selected, used


def format_selected_files(files: list[dict]) -> list[str]:
    lines = []
    for item in files:
        reason = item.get("reason", "selected")
        score = item.get("score", 0)
        lines.append(f"{item['path']}  [score={score}; {reason}]")
    return lines


def build_context_bundle(root: Path, prompt: str, selected: list[dict], raw_tokens: int, optimized_tokens: int, compression: str, full_files: bool, allow_secrets: bool) -> dict:
    files = []
    for item in selected:
        file_payload = dict(item)
        if full_files or compression in {"full", "hybrid", "snippets"}:
            text = (root / item["path"]).read_text(encoding="utf-8", errors="ignore")
            if has_secret(text) and not allow_secrets:
                text = redact_text(text)
                file_payload["secret_redacted"] = True
            file_payload["content"] = truncate_text(text, 4_000 if compression in {"snippets", "hybrid"} else 20_000)
        files.append(file_payload)
    return {
        "prompt": prompt,
        "raw_tokens": raw_tokens,
        "optimized_tokens": optimized_tokens,
        "savings_percent": round(savings_percent(raw_tokens, optimized_tokens), 1),
        "files": files,
        "missing_context_warning": missing_context_warning(prompt, files),
    }


def render_bundle(bundle: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(bundle, indent=2)
    if output_format == "xml":
        file_xml = "\n".join(
            f'<file path="{escape(item["path"])}" score="{item.get("score", 0)}"><reason>{escape(item.get("reason", ""))}</reason><summary>{escape(item.get("summary", ""))}</summary></file>'
            for item in bundle["files"]
        )
        return f'<contextguardrail prompt="{escape(bundle["prompt"])}">{file_xml}</contextguardrail>'
    lines = [
        "# ContextGuardrail Pack",
        "",
        f"Prompt: {bundle['prompt']}",
        f"Raw tokens: {bundle['raw_tokens']:,}",
        f"Optimized tokens: {bundle['optimized_tokens']:,}",
        f"Savings: {bundle['savings_percent']}%",
    ]
    if bundle["missing_context_warning"]:
        lines.extend(["", f"Warning: {bundle['missing_context_warning']}"])
    lines.extend(["", "## Read These Files First"])
    lines.extend(f"- {item['path']} [score={item.get('score', 0)}; {item.get('reason', 'selected')}]" for item in bundle["files"])
    if any(item.get("budget_truncated") for item in bundle["files"]):
        lines.extend(["", "Budget note: one or more summaries were truncated to honor --max-tokens."])
    lines.append("\n## File Summaries")
    for item in bundle["files"]:
        lines.extend(["", f"### {item['path']}", item.get("summary", "")])
        if "content" in item:
            lines.extend(["", "```", item["content"], "```"])
    return "\n".join(lines)


def missing_context_warning(prompt: str, files: list[dict]) -> str:
    terms = prompt_terms(prompt)
    if {"test", "tests", "pytest"} & terms and not any("test" in item["path"].lower() for item in files):
        return "Prompt mentions tests but no test files were selected."
    if {"api", "route", "endpoint"} & terms and not any(item["path"].endswith((".py", ".js", ".ts", ".tsx")) for item in files):
        return "Prompt may need route/controller files outside the selected set."
    return ""


def truncate_text(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "\n...<truncated>..."


def module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def git_changed_files(root: Path, revision_range: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", revision_range],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    app()
