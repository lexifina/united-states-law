"""Renders one parsed US Code section to the Markdown file united-states-law keeps (title-N/<section>.md).

Mirrors render() in the generator (saas-webpage scripts/us-code-git.ts) for a version's printed text, with no
in-between replay: heading line, then each provision as a paragraph or a bullet indented by designation depth.
"""
from __future__ import annotations

import re

_ESC = re.compile(r"([\\*_`<])")
_DEPTH = re.compile(r"^((?:\([^()]+\))*)")


def escape(s: str) -> str:
    return _ESC.sub(r"\\\1", s)


# Titles 1, 3, 4, 9, 11, 13, 17, 35 and 39 (main's first block) were written by the generator's first version: list
# depth from the printed level (path "" stays a paragraph) and no Markdown escaping.
V1_TITLES = {1, 3, 4, 9, 11, 13, 17, 35, 39}


def render_lines(title: int, number: str, heading: str, lines: list, style: str | None = None) -> str | None:
    """lines: (path, text) or (path, text, printed level). Returns None when there is no text (no file then)."""
    if not lines:
        return None
    v1 = (style or ("v1" if title in V1_TITLES else "v2")) == "v1"
    esc = (lambda x: x) if v1 else escape
    out = [f"# {title} U.S.C. § {number}. {esc(heading or '')}", ""]
    listed = False
    for line in lines:
        path, raw = line[0], line[1]
        text = raw
        text = re.sub(r"\s+", " ", text).replace("“", '"').replace("”", '"')
        text = re.sub(r"\.—\s+", ".—", text).strip()
        text = esc(text)
        level = (0 if path == "" else line[2] + 1) if v1 else _DEPTH.match(path).group(1).count("(")
        if not text:
            continue
        if level <= 0:
            if listed:
                out.append("")
            out.extend([text, ""])
            listed = False
        else:
            out.append(f"{'  ' * (level - 1)}- {text}")
            listed = True
    return "\n".join(out).rstrip() + "\n"
