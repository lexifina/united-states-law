"""Puts back the lines main's parser dropped (paragraphs GovInfo prints with a style attribute) into a file's text as main
has it on a date, from restore/title<T>.json (restore_data.py).

The printed version used is the latest one current on or before the date (the 2017 edition for anything earlier). Each
missing run of lines goes where the lines around it in the printed version are: after the run before it, else before the
run after it, matched exactly and only where the match is unique; shorter context is tried when the longer one is not
found. A run already there is left alone. Runs with no unique place are skipped and counted.
"""
from __future__ import annotations

import bisect
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = Counter()


class Restorer:
    def __init__(self) -> None:
        self.titles: dict[int, dict] = {}

    def _title(self, t: int) -> dict:
        if t not in self.titles:
            p = ROOT / "restore" / f"title{t}.json"
            vs = json.loads(p.read_text(encoding="utf-8"))["versions"] if p.exists() else []
            vs.sort(key=lambda v: v["date"])
            self.titles[t] = {"dates": [v["date"] for v in vs], "versions": vs,
                              "paths": {f for v in vs for f in v["files"]}}
        return self.titles[t]

    def affects(self, path: str) -> bool:
        m = re.match(r"title-(\d+)/", path)
        return bool(m) and path in self._title(int(m.group(1)))["paths"]

    def apply(self, path: str, text: str | None, day: str) -> str | None:
        if text is None or not self.affects(path):
            return text
        d = self._title(int(re.match(r"title-(\d+)/", path).group(1)))
        k = max(0, bisect.bisect_right(d["dates"], day) - 1)
        inserts = d["versions"][k]["files"].get(path)
        if not inserts:
            return text
        trail = text.endswith("\n")
        lines = text[:-1].split("\n") if trail else text.split("\n")
        for before, after, run in inserts:
            pos = self._place(lines, before, after, run)
            if pos is None:
                STATS["skipped"] += 1
                continue
            if lines[pos:pos + len(run)] == run:
                STATS["present"] += 1
                continue
            lines[pos:pos] = run
            STATS["inserted"] += 1
        return "\n".join(lines) + ("\n" if trail else "")

    @staticmethod
    def _find(lines: list[str], ctx: list[str]) -> list[int]:
        n = len(ctx)
        return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == ctx]

    def _place(self, lines, before, after, run) -> int | None:
        for size in (3, 2, 1):
            b = before[-size:] if len(before) >= size else None
            if b and any(x.strip() for x in b):
                hits = self._find(lines, b)
                if len(hits) == 1:
                    return hits[0] + len(b)
            a = after[:size] if len(after) >= size else None
            if a and any(x.strip() for x in a):
                hits = self._find(lines, a)
                if len(hits) == 1:
                    return hits[0]
        if not before and after:
            return 0
        return None
