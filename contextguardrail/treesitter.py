from __future__ import annotations

from pathlib import Path

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}

FUNCTION_NODES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "arrow_function",
}
CLASS_NODES = {
    "class_definition",
    "class_declaration",
    "struct_type",
    "interface_type",
}
IMPORT_NODES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "call_expression",
}


def available() -> bool:
    try:
        import tree_sitter_language_pack  # noqa: F401

        return True
    except Exception:
        return False


def parse_with_treesitter(path: Path, text: str) -> dict[str, list[str]] | None:
    language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
    if not language:
        return None
    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(language)
        tree = parser.parse(text.encode("utf-8", errors="ignore"))
    except Exception:
        return None

    functions: set[str] = set()
    classes: set[str] = set()
    imports: set[str] = set()

    def walk(node):
        node_text = text[node.start_byte : node.end_byte]
        if node.type in FUNCTION_NODES:
            name = first_identifier(node, text)
            if name:
                functions.add(name)
        elif node.type in CLASS_NODES:
            name = first_identifier(node, text)
            if name:
                classes.add(name)
        elif node.type in IMPORT_NODES and ("import" in node_text or "require" in node_text):
            imports.update(extract_quoted(node_text))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return {
        "imports": sorted(imports),
        "classes": sorted(classes),
        "functions": sorted(functions),
    }


def first_identifier(node, text: str) -> str:
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier"}:
            return text[child.start_byte : child.end_byte]
        found = first_identifier(child, text)
        if found:
            return found
    return ""


def extract_quoted(text: str) -> set[str]:
    values = set()
    quote = None
    start = 0
    for index, char in enumerate(text):
        if char in {"'", '"'}:
            if quote is None:
                quote = char
                start = index + 1
            elif quote == char:
                values.add(text[start:index])
                quote = None
    return values
