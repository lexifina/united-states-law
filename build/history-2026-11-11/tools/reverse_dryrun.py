"""Dry run: take title 26 back from the 1994 edition towards the 1986 Code by reversing each amendment-note entry of a
law enacted after Pub. L. 99-514 (Oct 22, 1986), newest first, and count what applies cleanly. Nothing is written but
data/reverse-dryrun.json.

An entry applies cleanly when its inverse finds exactly one place to act in the provision the note names (or the
whole section when it names none):
  substituted "X" for "Y"            -> X back to Y
  inserted "X" [after|before "Y"]    -> remove X
  struck out "X" after|before "Y"    -> put X back beside Y
  added par./subpar./... (n)         -> remove that provision
Anything else (struck out without a place, amended generally, redesignated, entries without quoted words) does not.
"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_block import Laws, amend_entries, straight  # noqa: E402
from feasibility_1986 import after_1986  # noqa: E402

ROOT = HERE.parent
ed = json.load(gzip.open(ROOT / "data" / "title26" / "1994.json.gz", "rt", encoding="utf-8"))

SUB = re.compile(r'\bsubstituted "([^"]+)" for "([^"]+)"', re.I)
INS = re.compile(r'\binserted "([^"]+)"', re.I)
STRUCK = re.compile(r'\bstruck out "([^"]+)" (after|before) "([^"]+)"', re.I)
ADDED = re.compile(r'\badded (?:subsec|par|subpar|cl|subcl|item)s?\.\s*\(([^)]+)\)', re.I)


def within(lines, path):
    return [i for i, l in enumerate(lines) if not path or l[0] == path or l[0].startswith(path + "(") or l[0].startswith(path + " ")]


def apply_one(lines, e) -> tuple[bool, str]:
    t = straight(e.text)
    paths = e.paths or [""]
    idx = sorted({i for p in paths for i in within(lines, p)})
    if not idx:
        return False, "provision not found"
    m = SUB.search(t)
    if m:
        x, y = m.group(1), m.group(2)
        hits = [i for i in idx if straight(lines[i][1]).count(x) == 1]
        if len(hits) == 1 and sum(straight(lines[i][1]).count(x) for i in idx) == 1:
            i = hits[0]
            lines[i][1] = straight(lines[i][1]).replace(x, y)
            return True, "substituted"
        return False, "substituted: not exactly one place"
    m = STRUCK.search(t)
    if m:
        x, where, y = m.groups()
        hits = [i for i in idx if straight(lines[i][1]).count(y) == 1]
        if len(hits) == 1:
            i = hits[0]
            s = straight(lines[i][1])
            k = s.index(y)
            lines[i][1] = s[: k + len(y)] + x + s[k + len(y):] if where.lower() == "after" else s[:k] + x + s[k:]
            return True, "struck"
        return False, "struck: not exactly one place"
    m = INS.search(t)
    if m:
        x = m.group(1)
        hits = [i for i in idx if straight(lines[i][1]).count(x) == 1]
        if len(hits) == 1 and sum(straight(lines[i][1]).count(x) for i in idx) == 1:
            i = hits[0]
            lines[i][1] = straight(lines[i][1]).replace(x, "", 1)
            return True, "inserted"
        if len(x) > 40 and any(straight(lines[i][1]).strip() == x.strip() for i in idx):
            i = next(i for i in idx if straight(lines[i][1]).strip() == x.strip())
            del lines[i]
            return True, "inserted line"
        return False, "inserted: not exactly one place"
    m = ADDED.search(t)
    if m and e.paths:
        target = e.paths[0]
        gone = within(lines, target) if target else []
        if gone:
            for i in reversed(gone):
                del lines[i]
            return True, "added"
        return False, "added: provision not found"
    return False, "no reversible wording"


sections = Counter()
reasons = Counter()
entries = Counter()
out = {}
for n, s in ed["sections"].items():
    if not s["lines"]:
        continue
    es = [e for e in amend_entries(s) if e.laws and after_1986(e.laws[0].pl)]
    if not es:
        sections["unamended since 99-514"] += 1
        continue
    lines = [list(l) for l in s["lines"]]
    ok = bad = 0
    for e in es:   # the notes list the newest year first
        done, why = apply_one(lines, e)
        reasons[why] += 1
        ok += done
        bad += not done
    entries["applied"] += ok
    entries["not applied"] += bad
    k = "fully" if not bad else ("partly" if ok else "not at all")
    sections[k] += 1
    out[n] = {"entries": len(es), "applied": ok}
print("title 26 sections with text in the 1994 edition:", sum(sections.values()))
for k, v in sections.most_common():
    print(f"  {k:26} {v}")
print("entries:", dict(entries))
for k, v in reasons.most_common():
    print(f"  {k:40} {v}")
(ROOT / "data" / "reverse-dryrun.json").write_text(json.dumps(out), encoding="utf-8")
