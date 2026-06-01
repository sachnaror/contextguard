from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import networkx as nx

from contextguardrail.storage import connect


WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+")
JS_IMPORT_RE = re.compile(r"(?:import\s+.*?\s+from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]")
JS_FUNCTION_RE = re.compile(
    r"(?:function\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(|([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?\()"
)
JS_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")
CSS_SELECTOR_RE = re.compile(r"(^|[,{]\s*)([.#]?[A-Za-z][A-Za-z0-9_-]*)\s*[{,]", re.MULTILINE)
HTML_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)\b")
HTML_ID_RE = re.compile(r"\bid=['\"]([^'\"]+)['\"]")
HTML_CLASS_RE = re.compile(r"\bclass=['\"]([^'\"]+)['\"]")
HTML_LINK_SCRIPT_RE = re.compile(r"(?:href|src)=['\"]([^'\"]+)['\"]")
GO_IMPORT_RE = re.compile(r"import\s+(?:\((.*?)\)|\"([^\"]+)\")", re.DOTALL)
GO_FUNC_RE = re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
GO_TYPE_RE = re.compile(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:struct|interface)\b")
ROUTE_RE = re.compile(r"\b(?:app|router|api)\.(get|post|put|patch|delete|route)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
SQL_TABLE_RE = re.compile(r"\b(?:create\s+table|alter\s+table|from|join|into|update)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.IGNORECASE)
YAML_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", re.MULTILINE)
TF_BLOCK_RE = re.compile(r"\b(resource|module|variable|output|data)\s+\"([^\"]+)\"(?:\s+\"([^\"]+)\")?")


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


def parse_javascript(text: str) -> dict[str, list[str]]:
    functions = []
    for match in JS_FUNCTION_RE.findall(text):
        functions.extend(name for name in match if name)
    routes = [f"{method.upper()} {route}" for method, route in ROUTE_RE.findall(text)]
    return {
        "imports": sorted(set(JS_IMPORT_RE.findall(text))),
        "classes": sorted(set(JS_CLASS_RE.findall(text))),
        "functions": sorted(set(functions + routes)),
    }


def parse_css(text: str) -> dict[str, list[str]]:
    selectors = [selector for _, selector in CSS_SELECTOR_RE.findall(text)]
    return {"imports": [], "classes": sorted(set(selectors)), "functions": []}


def parse_html(text: str) -> dict[str, list[str]]:
    classes = []
    for class_attr in HTML_CLASS_RE.findall(text):
        classes.extend(class_attr.split())
    return {
        "imports": sorted(set(HTML_LINK_SCRIPT_RE.findall(text))),
        "classes": sorted(set(classes + HTML_ID_RE.findall(text))),
        "functions": sorted(set(HTML_TAG_RE.findall(text))),
    }


def parse_go(text: str) -> dict[str, list[str]]:
    imports = []
    for block, single in GO_IMPORT_RE.findall(text):
        imports.extend(re.findall(r"\"([^\"]+)\"", block) if block else [single])
    return {
        "imports": sorted(set(imports)),
        "classes": sorted(set(GO_TYPE_RE.findall(text))),
        "functions": sorted(set(GO_FUNC_RE.findall(text))),
    }


def parse_sql(text: str) -> dict[str, list[str]]:
    return {"imports": [], "classes": sorted(set(SQL_TABLE_RE.findall(text))), "functions": []}


def parse_yaml(text: str) -> dict[str, list[str]]:
    keys = YAML_KEY_RE.findall(text)
    return {"imports": [], "classes": sorted(set(keys)), "functions": []}


def parse_terraform(text: str) -> dict[str, list[str]]:
    blocks = [".".join(part for part in match if part) for match in TF_BLOCK_RE.findall(text)]
    return {"imports": [], "classes": sorted(set(blocks)), "functions": []}


def parse_file(path: Path, rel_path: str, text: str) -> dict[str, Any]:
    data: dict[str, Any] = {"imports": [], "classes": [], "functions": []}
    if path.suffix == ".py":
        try:
            data = parse_python(text)
        except SyntaxError:
            pass
    elif path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
        data = parse_javascript(text)
    elif path.suffix == ".css":
        data = parse_css(text)
    elif path.suffix == ".html":
        data = parse_html(text)
    elif path.suffix == ".go":
        data = parse_go(text)
    elif path.suffix == ".sql":
        data = parse_sql(text)
    elif path.suffix in {".yaml", ".yml"}:
        data = parse_yaml(text)
    elif path.suffix in {".tf", ".tfvars"}:
        data = parse_terraform(text)
    words = WORD_RE.findall(rel_path + " " + text[:8_000])
    symbols = data["imports"] + data["classes"] + data["functions"]
    expanded = []
    for word in words + symbols:
        expanded.append(word)
        expanded.extend(CAMEL_RE.findall(word.replace("_", " ")))
    data["keywords"] = sorted(set(w.lower() for w in expanded if len(w) > 2))
    return data


def summarize_file(rel_path: str, text: str, parsed: dict[str, Any]) -> str:
    lines = [f"File: {rel_path}"]
    suffix = Path(rel_path).suffix.lower()
    if parsed["functions"]:
        label = "HTML tags" if suffix == ".html" else "Functions"
        lines.append(label + ": " + ", ".join(parsed["functions"][:30]))
    if parsed["classes"]:
        label = "Selectors" if suffix == ".css" else "Classes/IDs"
        if suffix == ".py":
            label = "Classes"
        lines.append(label + ": " + ", ".join(parsed["classes"][:30]))
    if parsed["imports"]:
        label = "Linked assets" if suffix == ".html" else "Imports"
        lines.append(label + ": " + ", ".join(parsed["imports"][:20]))
    doc = next(
        (
            line.strip("#/<!-*> ").strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith(("</", "{", "}"))
        ),
        "",
    )
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
            normalized = imported.split("#", 1)[0].split("?", 1)[0].lstrip("./")
            if not normalized or normalized.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            target = module_to_path.get(imported) or module_to_path.get(
                Path(normalized).with_suffix("").as_posix().replace("/", ".")
            )
            if not target and normalized in paths:
                target = normalized
            if target:
                graph.add_edge(path, target, type="imports")
    return graph


def graph_counts(repo: str | Path) -> tuple[int, int]:
    with connect(repo, "graph.db") as db:
        rows = db.execute("SELECT classes, functions FROM symbols").fetchall()
    classes = sum(len(row["classes"].splitlines()) for row in rows if row["classes"])
    functions = sum(len(row["functions"].splitlines()) for row in rows if row["functions"])
    return functions, classes
