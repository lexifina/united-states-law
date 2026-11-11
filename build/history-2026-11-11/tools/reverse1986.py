"""Takes title 26 from the 1994 edition back to the Internal Revenue Code of 1986 as it stood after the Tax Reform Act of
1986 (Pub. L. 99-514, October 22, 1986), section by section, by reversing the 1994 edition's amendment notes.

For each section: the entries of laws enacted after Pub. L. 99-514 are reversed, newest law first, each by the one place
its words name (see apply_one). The state before a law's entries are reversed is the text just after that law; the state
after all are reversed is the text the section started from: the 1986 Code, or, for a section a later law added
("Added Pub. L. 100-647, ..." in its source credit), the text that law added. A section is taken back only when every
entry reverses cleanly ("full"); otherwise it keeps the 1994 edition as its start ("partial", "none").

    reconstruct(edition_1994: dict, lawdb) -> {section: {...}}
"""
from __future__ import annotations

import re

from build_block import amend_entries, pl_key, straight

ROOT_DAY = "1986-10-22"
SUB = re.compile(r'\bsubstituted "([^"]+)" for "([^"]+)"', re.I)
INS = re.compile(r'\binserted "([^"]+)"', re.I)
STRUCK = re.compile(r'\bstruck out "([^"]+)" (after|before) "([^"]+)"', re.I)
ADDED = re.compile(r'\badded (?:subsec|par|subpar|cl|subcl|item)s?\.\s*\(([^)]+)\)', re.I)
_ADDED_BY = re.compile(r"^\(?\s*Added\s+Pub\.\s*L\.\s*(\d+)\s*[–—\-]\s*(\d+)")


def after_1986(pl: str, lawdb) -> bool:
    c, n = (int(x) for x in pl.split("-"))
    if c != 99:
        return c > 99
    d = lawdb.enacted(pl)
    return bool(d and d > ROOT_DAY)


def within(lines, path):
    return [i for i, l in enumerate(lines) if not path or l[0] == path or l[0].startswith(path + "(") or l[0].startswith(path + " ")]


def apply_one(lines, e) -> tuple[bool, str, dict]:
    """Reverses one entry in place. Returns (applied, kind, detail) where detail has the words for the cross-check."""
    t = straight(e.text)
    paths = e.paths or [""]
    idx = sorted({i for p in paths for i in within(lines, p)})
    if not idx:
        return False, "provision not found", {}

    def once(x):
        hits = [i for i in idx if straight(lines[i][1]).count(x) == 1]
        total = sum(straight(lines[i][1]).count(x) for i in idx)
        return hits[0] if len(hits) == 1 and total == 1 else None

    m = SUB.search(t)
    if m:
        x, y = m.group(1), m.group(2)
        i = once(x)
        if i is None:
            return False, "substituted: not exactly one place", {}
        lines[i][1] = straight(lines[i][1]).replace(x, y)
        return True, "substituted", {"new": x, "old": y}
    m = STRUCK.search(t)
    if m:
        x, where, y = m.groups()
        i = once(y)
        if i is None:
            return False, "struck: not exactly one place", {}
        s = straight(lines[i][1])
        k = s.index(y)
        lines[i][1] = s[: k + len(y)] + x + s[k + len(y):] if where.lower() == "after" else s[:k] + x + s[k:]
        return True, "struck", {"old": x, "anchor": y}
    m = INS.search(t)
    if m:
        x = m.group(1)
        i = once(x)
        if i is not None:
            lines[i][1] = straight(lines[i][1]).replace(x, "", 1)
            return True, "inserted", {"new": x}
        whole = [i for i in idx if straight(lines[i][1]).strip() == x.strip()]
        if len(x) > 40 and len(whole) == 1:
            del lines[whole[0]]
            return True, "inserted line", {"new": x}
        return False, "inserted: not exactly one place", {}
    m = ADDED.search(t)
    if m and e.paths:
        gone = within(lines, e.paths[0])
        if gone:
            for i in reversed(gone):
                del lines[i]
            return True, "added", {}
        return False, "added: provision not found", {}
    return False, "no reversible wording", {}


def reconstruct(ed: dict, lawdb) -> dict:
    out = {}
    for n, s in ed["sections"].items():
        if not s["lines"]:
            continue
        added = _ADDED_BY.match(s.get("source_credit", ""))
        adder = f"{int(added.group(1))}-{int(added.group(2))}" if added else None
        if adder and not after_1986(adder, lawdb):
            adder = None              # added by the Tax Reform Act of 1986 or earlier: in the 1986 Code
        es = [e for e in amend_entries(s) if e.laws and after_1986(e.laws[0].pl, lawdb) and e.laws[0].pl != adder]
        es.sort(key=lambda e: (lawdb.enacted(e.laws[0].pl) or "9999", pl_key(e.laws[0].pl)), reverse=True)
        lines = [list(l) for l in s["lines"]]
        after: dict[str, list] = {}
        done, failed, applied = 0, [], []
        for e in es:
            law = e.laws[0].pl
            if law not in after:
                after[law] = [list(l) for l in lines]     # the text just after this law
            ok, kind, detail = apply_one(lines, e)
            if ok:
                done += 1
                applied.append({"law": law, "kind": kind, "text": e.text, **detail})
            else:
                failed.append({"law": law, "why": kind, "text": e.text[:300]})
        status = "unamended" if not es else ("full" if not failed else ("partial" if done else "none"))
        out[n] = {"status": status, "adder": adder, "start": lines if status in ("unamended", "full") else None,
                  "after": after if status == "full" else {}, "applied": applied, "failed": failed,
                  "heading": s["heading"]}
    return out
