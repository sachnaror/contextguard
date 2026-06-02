from __future__ import annotations


def optimize_prompt(prompt: str, files: list[dict], constraints: list[str] | None = None) -> str:
    constraints = constraints or []
    lines = [
        "Task:",
        prompt.strip(),
        "",
        "Relevant files, inspect in this order:",
    ]
    for item in files:
        lines.append(f"- {item['path']} ({item.get('reason', 'selected')})")
    if constraints:
        lines.extend(["", "Constraints:"])
        lines.extend(f"- {constraint}" for constraint in constraints)
    lines.extend(
        [
            "",
            "Working instructions:",
            "- Prefer the listed files before scanning broadly.",
            "- If required context is missing, state exactly which file or module is needed.",
            "- Keep changes minimal and verify with the nearest relevant tests.",
        ]
    )
    return "\n".join(lines)
