from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from contextguard.budget import cost_usd
from contextguard.cache import (
    already_sent,
    cache_key,
    clean_cache,
    get_cache,
    remember_sent,
    selected_files_hash,
    set_cache,
)
from contextguard.config import DEFAULT_BUDGET, DEFAULT_MODEL, ensure_state, repo_root
from contextguard.exporter import export_repo
from contextguard.graph import graph_counts
from contextguard.scanner import index_repo
from contextguard.selector import select_context
from contextguard.stats import record_request, show_stats
from contextguard.storage import init_storage

app = typer.Typer(help="Local-first token firewall for AI coding agents.")
console = Console()


@app.command()
def init(path: str = typer.Argument(".")):
    """Create .contextguard storage for a repo."""
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
    key = cache_key(prompt, selected_files_hash(base_selected), model)
    cached = get_cache(root, key)
    if cached is not None:
        console.print(cached.replace("Cache: miss", "Cache: hit"))
        record_request(root, raw_tokens, 0, cache_hit=True)
        return

    replay = {} if include_replay else already_sent(root, prompt)
    selected, raw_tokens = select_context(root, prompt, budget=budget, exclude_unchanged=replay)
    optimized_tokens = sum(max(30, min(item["tokens"], int(item["tokens"] * 0.25))) for item in selected)

    lines = ["Files selected:", ""]
    if selected:
        lines.extend(item["path"] for item in selected)
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
    record_request(root, raw_tokens, optimized_tokens, cache_hit=False)
    console.print("\n".join(lines))


@app.command()
def analyze(
    prompt: str,
    path: str = typer.Option(".", "--path", "-p"),
    budget: int = typer.Option(DEFAULT_BUDGET, "--budget", "-b"),
):
    """Killer-demo alias for ask with cost framing."""
    ask(prompt=prompt, path=path, budget=budget)


@app.command()
def stats(path: str = typer.Argument(".")):
    """Show token and cache savings."""
    data = show_stats(repo_root(path))
    table = Table(title="ContextGuard Stats")
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


def estimated_optimized_tokens(files: list[dict]) -> int:
    return sum(max(30, min(item["tokens"], int(item["tokens"] * 0.25))) for item in files)


if __name__ == "__main__":
    app()
