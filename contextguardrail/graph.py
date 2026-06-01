from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import networkx as nx

from contextguardrail.storage import connect


WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def parse_python(text: str) -> dict[str, list[str]]:
    tree = ast.parse(text)
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
    return {
        "imports": sorted(set(imports)),
        "classes": sorted(set(classes)),
        "functions": sorted(set(functions)),
    }


def parse_file(path: Path, rel_path: str, text: str) -> dict[str, Any]:
    data: dict[str, Any] = {"imports": [], "classes": [], "functions": []}
    if path.suffix == ".py":
        try:
            data = parse_python(text)
        except SyntaxError:
            pass
    words = WORD_RE.findall(rel_path + " " + text[:8_000])
    symbols = data["imports"] + data["classes"] + data["functions"]
    data["keywords"] = sorted(set(w.lower() for w in words + symbols if len(w) > 2))
    return data


def summarize_file(rel_path: str, text: str, parsed: dict[str, Any]) -> str:
    lines = [f"File: {rel_path}"]
    if parsed["functions"]:
        lines.append("Functions: " + ", ".join(parsed["functions"][:30]))
    if parsed["classes"]:
        lines.append("Classes: " + ", ".join(parsed["classes"][:30]))
    if parsed["imports"]:
        lines.append("Imports: " + ", ".join(parsed["imports"][:20]))
    doc = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
    if doc:
        lines.append("First line: " + doc[:240])
    return "\n".join(lines)


def upsert_symbols(repo: str | Path, rel_path: str, parsed: dict[str, Any]) -> None:
    with connect(repo, "graph.db") as db:
        db.execute(
            """
            INSERT INTO symbols(path, imports, classes, functions, keywords)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              imports=excluded.imports,
              classes=excluded.classes,
              functions=excluded.functions,
              keywords=excluded.keywords
            """,
            (
                rel_path,
                "\n".join(parsed["imports"]),
                "\n".join(parsed["classes"]),
                "\n".join(parsed["functions"]),
                "\n".join(parsed["keywords"]),
            ),
        )


def load_graph(repo: str | Path) -> nx.DiGraph:
    graph = nx.DiGraph()
    with connect(repo, "graph.db") as db:
        rows = db.execute("SELECT path, imports, classes, functions FROM symbols").fetchall()
    paths = {row["path"] for row in rows}
    module_to_path = {Path(path).with_suffix("").as_posix().replace("/", "."): path for path in paths}
    for row in rows:
        path = row["path"]
        graph.add_node(path, classes=row["classes"].splitlines(), functions=row["functions"].splitlines())
        for imported in row["imports"].splitlines():
            target = module_to_path.get(imported)
            if target:
                graph.add_edge(path, target, type="imports")
    return graph


def graph_counts(repo: str | Path) -> tuple[int, int]:
    with connect(repo, "graph.db") as db:
        rows = db.execute("SELECT classes, functions FROM symbols").fetchall()
    classes = sum(len(row["classes"].splitlines()) for row in rows if row["classes"])
    functions = sum(len(row["functions"].splitlines()) for row in rows if row["functions"])
    return functions, classes
