from __future__ import annotations

from pathlib import Path

from contextguardrail.graph import load_graph
from contextguardrail.storage import connect


def blast_radius(repo: str | Path, file: str, depth: int = 2) -> dict:
    graph = load_graph(repo)
    if file not in graph:
        return {"file": file, "affected_files": [], "apis": [], "tests": []}
    seen = {file}
    frontier = {file}
    for _ in range(depth):
        next_frontier = set()
        for node in frontier:
            next_frontier.update(graph.successors(node))
            next_frontier.update(graph.predecessors(node))
        next_frontier -= seen
        seen.update(next_frontier)
        frontier = next_frontier
    affected = sorted(seen - {file})
    with connect(repo, "graph.db") as db:
        rows = {row["path"]: row for row in db.execute("SELECT path, functions FROM symbols").fetchall()}
    apis = []
    tests = []
    for path in affected:
        row = rows.get(path)
        functions = row["functions"] if row else ""
        apis.extend(f"{path}: {line}" for line in functions.splitlines() if " " in line and line.split(" ", 1)[0] in {"GET", "POST", "PUT", "PATCH", "DELETE"})
        if "test" in path.lower() or path.lower().endswith(("_test.go", ".spec.ts", ".test.ts", ".test.js")):
            tests.append(path)
    return {"file": file, "affected_files": affected, "apis": sorted(apis), "tests": sorted(tests)}
