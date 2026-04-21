#!/usr/bin/env python3

import json
from pathlib import Path
from os import getenv


def build_comment_body(root: Path) -> str:
    files = sorted(root.rglob("*.json"))
    items = []
    parse_warnings = []

    print("Parsing comment artifact files:")
    for path in files:
        print(f" - {path}")
        text = None
        try:
            text = path.read_text()
            items.append(json.loads(text))
        except Exception as exc:
            parse_warnings.append(f"{path.name}: failed to parse JSON ({exc})")
            print(f"   ERROR parsing {path}: {exc}")
            if text is not None:
                print("   File contents:")
                print(text)

    warnings = list(parse_warnings)
    sections = {}

    for item in items:
        for warning in item.get("warnings", []):
            warnings.append(f"{item.get('name', 'unknown')}: {warning}")
        sections.setdefault(item.get("section", "other"), []).append(item)

    short_sha = ""
    for item in items:
        git_sha = str(getenv("HEAD_SHA")).strip()
        if git_sha:
            short_sha = git_sha[:7]
            break

    title = "## CD summary"
    if short_sha:
        title = f"{title} `{short_sha}`"

    marker = "<!-- stitch-cd-summary -->"
    lines = [title, "", marker, ""]

    frontend_url = ""
    for item in items:
        if item.get("name") == "frontend":
            frontend_url = str(item.get("data", {}).get("url", "")).strip()
            if frontend_url:
                break

    if frontend_url:
        lines.append(f"Frontend: {frontend_url}")
        lines.append("")

    if warnings:
        lines.append("### Warnings")
        lines.extend([f"- {warning}" for warning in warnings])
        lines.append("")

    section_order = ["deployments", "database", "jobs", "images"]
    seen = set()
    ordered_sections = []

    for section in section_order:
        if section in sections:
            ordered_sections.append(section)
            seen.add(section)

    for section in sections:
        if section not in seen:
            ordered_sections.append(section)

    for section in ordered_sections:
        group = sections[section]
        lines.append("<details>")
        lines.append(f"<summary>{section.capitalize()} ({len(group)})</summary>")
        lines.append("")

        keys = []
        for item in group:
            for key in item.get("data", {}).keys():
                if key not in keys:
                    keys.append(key)

        if not keys:
            lines.append("_No data_")
            lines.append("")
            lines.append("</details>")
            lines.append("")
            continue

        lines.append("| " + " | ".join(keys) + " |")
        lines.append("| " + " | ".join(["---"] * len(keys)) + " |")

        for item in sorted(group, key=lambda value: value.get("name", "")):
            row = [str(item.get("data", {}).get(key, "")) for key in keys]
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    root = Path(".comment-artifacts")
    output_path = Path(".comment-body.md")
    body = build_comment_body(root)
    print(body)
    output_path.write_text(body)


if __name__ == "__main__":
    main()
