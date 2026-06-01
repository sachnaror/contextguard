from __future__ import annotations

import json
from pathlib import Path

from contextguard.config import ensure_state
from contextguard.graph import load_graph
from contextguard.storage import connect, load_stats


def export_repo(repo: str | Path = ".") -> list[Path]:
    state = ensure_state(repo)
    with connect(repo, "hashes.db") as files_db, connect(repo, "graph.db") as graph_db:
        files = [dict(row) for row in files_db.execute("SELECT * FROM files ORDER BY path").fetchall()]
        symbols = [dict(row) for row in graph_db.execute("SELECT * FROM symbols ORDER BY path").fetchall()]
    graph = load_graph(repo)
    brain = {
        "files": files,
        "symbols": symbols,
        "edges": [{"source": a, "target": b, **data} for a, b, data in graph.edges(data=True)],
        "stats": load_stats(repo),
    }
    repo_brain = state / "repo-brain.json"
    code_dna = state / "code-dna.json"
    ai_gossip = state / "ai-gossip.md"
    repo_brain.write_text(json.dumps(brain, indent=2) + "\n", encoding="utf-8")
    code_dna.write_text(
        json.dumps({"files": len(files), "symbols": len(symbols), "edges": graph.number_of_edges()}, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = ["# AI Gossip", "", "Most connected files:"]
    for node, degree in sorted(graph.degree, key=lambda item: item[1], reverse=True)[:20]:
        lines.append(f"- {node}: {degree} links")
    ai_gossip.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [repo_brain, code_dna, ai_gossip]
