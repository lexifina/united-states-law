"""Builds the pre-1994 block of one US Code title: commits from the first LoC edition (the 1926 Code, laws in force
December 7, 1925, or the first edition printing the title) to the title's GovInfo starting text (1994; 1995 for
titles 7, 28 and 39), one commit per law per date, credited from the editions' own records.

    python build_pre.py <title>

Reads data/title<T>/<Y>.json.gz (clean.py output for the LoC editions; fetch_parse.py output for the anchor) and
writes blocks/title<T>.json.gz: [{author, email, date, message, files: {path: text | null}}] and
blocks/title<T>.report.json.

How a change is credited (as the 1994-2016 block): between two consecutive editions, a section whose text changed is
credited to the laws the newer edition names for it that the older did not, in its source credit or amendment notes.
One law: the whole change is its. Several: each changed run of lines goes to the law whose amendment-note entry quotes
its new words, else the latest. None: "Printed text differs" under the newer edition. A law's commit is dated the day
it was enacted, or the day after the older edition's cutoff if it was enacted before it. Acts before public-law
numbers (1957) are named by date and chapter ("Act of July 30, 1947, ch. 388") with their Statutes at Large page.
"""
from __future__ import annotations

import difflib
import gzip
import json
import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ref", "build", "history-2026-11-11", "tools"))
from render import render_lines  # noqa: E402

DATA = os.path.join(ROOT, "data")
BLOCKS = os.path.join(ROOT, "blocks")
EDITIONS = [1925, 1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982, 1988]
CUTOFF = {1925: "1925-12-07", 1934: "1935-01-03", 1940: "1941-01-03", 1946: "1947-01-02", 1952: "1953-01-06",
          1958: "1959-01-06", 1964: "1965-01-03", 1970: "1971-01-20", 1976: "1977-01-03", 1982: "1983-01-14",
          1988: "1989-01-03", 1994: "1995-01-04", 1995: "1996-01-16"}
EDITION_NAME = {1925: "the Code of Laws of the United States (1926), laws in force December 7, 1925"}
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "aug": 8,
       "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MONTHS = "Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec"
DATE = re.compile(r"\b(" + MONTHS + r")[.,]?\s+(\d{1,2})[,.]?\s+(\d{4})")
PL = re.compile(r"Pub\.\s*L\.\s*(\d{2,3})\s*[–—\-~]\s*(\d{1,4})")
CH = re.compile(r"\b(?:ch|c)\.\s*(\d{1,4})")
STAT = re.compile(r"(\d{1,3})\s+Stat[.,]?\s+(\d{1,5})")
REORG = re.compile(r"Reorg\.\s*Plan\s*No\.\s*(\d+)\s*of\s*(\d{4})")
LOC = "https://tile.loc.gov/storage-services/service/ll/uscode"


def iso(m) -> str | None:
    try:
        return date(int(m.group(3)), MON[m.group(1).lower()], int(m.group(2))).isoformat()
    except (ValueError, KeyError):
        return None


def fmt(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{['January','February','March','April','May','June','July','August','September','October','November','December'][m-1]} {dd}, {y}"


def wrap(s: str, width: int = 72, indent: str = "") -> str:
    lines, line = [], ""
    for w in s.split():
        if line and len(line) + 1 + len(w) > width:
            lines.append(indent + line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    if line:
        lines.append(indent + line)
    return "\n".join(lines)


def sec_key(n: str):
    m = re.match(r"(\d+)(.*)", n)
    return (int(m.group(1)), m.group(2)) if m else (10**9, n)


# ---- laws named in a source credit ----

def laws_in_credit(credit: str) -> dict[str, dict]:
    """key -> {name, email, enacted, stat}. Keys: pl-C-N, act-YYYY-MM-DD-chN (or act-YYYY-MM-DD), reorg-YYYY-N."""
    out: dict[str, dict] = {}
    credit = (credit or "").replace("–", "-").replace("—", "-")
    for part in re.split(r";", credit):
        part = part.strip(" ().")
        if not part:
            continue
        stat = STAT.search(part)
        st = f"{stat.group(1)} Stat. {stat.group(2)}" if stat else None
        m = PL.search(part)
        dm = DATE.search(part)
        d = iso(dm) if dm else None
        if m:
            c, n = int(m.group(1)), int(m.group(2))
            if 85 <= c <= 103:
                out[f"pl-{c}-{n}"] = {"name": f"Pub. L. {c}-{n}", "email": f"pl-{c}-{n}@public-law.invalid",
                                      "enacted": d, "stat": st}
            continue
        r = REORG.search(part)
        if r:
            k = f"reorg-{r.group(2)}-{r.group(1)}"
            out[k] = {"name": f"Reorg. Plan No. {r.group(1)} of {r.group(2)}", "email": f"{k}@public-law.invalid",
                      "enacted": d, "stat": st}
            continue
        if re.match(r"^\s*[RB]\.\s*S\.", part) or not d:
            continue
        ch = CH.search(part)
        if ch:
            k = f"act-{d}-ch{int(ch.group(1))}"
            name = f"Act of {fmt(d)}, ch. {int(ch.group(1))}"
        else:
            k = f"act-{d}"
            name = f"Act of {fmt(d)}" + (f" ({st})" if st else "")
        out[k] = {"name": name, "email": f"{k}@public-law.invalid", "enacted": d, "stat": st}
    return out


def note_entries(sec: dict) -> list[str]:
    """Amendment-note entries (GovInfo notes for the anchor; OCR'd AMENDMENTS notes for LoC editions)."""
    out = []
    notes = sec.get("notes") or {}
    for k, v in notes.items():
        if k == "ocr-notes":
            for head, paras in v:
                if re.search(r"AMENDMENT", head, re.I):
                    out.extend(paras)
        elif "amendment" in k:
            out.extend(re.sub(r"<[^>]+>", "", x).replace("&mdash;", "—").replace("&ldquo;", "“").replace("&rdquo;", "”")
                       for x in v if isinstance(x, str))
    return out


def laws_of(sec: dict | None) -> dict[str, dict]:
    if not sec:
        return {}
    got = laws_in_credit(sec.get("source_credit") or "")
    for e in note_entries(sec):
        # notes name laws as "Pub. L. 98-51" or "Act July 30, 1947"; other dates in notes are not laws
        for m in re.finditer(r"(Pub\.\s*L\.\s*\d{2,3}\s*[–—\-~]\s*\d{1,4}[^;.]*?(?:" + MONTHS + r")[.,]?\s+\d{1,2}[,.]?\s+\d{4})|"
                             r"(Act\s+(?:" + MONTHS + r")[.,]?\s+\d{1,2}[,.]?\s+\d{4}(?:,\s*(?:ch|c)\.\s*\d+)?)", e):
            for k, v in laws_in_credit(m.group(0)).items():
                if not v.get("enacted"):
                    continue
                if k.startswith("act-") and "-ch" not in k:
                    # notes cite "Act Aug. 2, 1946" without the chapter: the credit's act of that day, if only one
                    same = [kk for kk in got if kk.startswith(k + "-ch")]
                    if len(same) == 1:
                        continue
                got.setdefault(k, v)
    # and the reverse: a date-only key from the credit (no chapter read) next to a chaptered one of the same day
    for k in [k for k in got if k.startswith("act-") and "-ch" not in k]:
        if any(kk.startswith(k + "-ch") for kk in got):
            got.pop(k)
    return got


def load(T: int, Y: int) -> dict | None:
    p = os.path.join(DATA, f"title{T}", f"{Y}.json.gz")
    if not os.path.exists(p):
        return None
    return json.load(gzip.open(p, "rt", encoding="utf-8"))


def fname(T: int, n: str) -> str:
    return f"title-{T}/{n}.md"


def main() -> None:
    T = int(sys.argv[1])
    anchor_year = 1995 if T in (7, 28, 39) else 1994
    eds = [e for e in (load(T, y) for y in EDITIONS) if e]
    anchor = load(T, anchor_year)
    if anchor is None:
        # a title gone before 1994 (title 6, repealed 1982; the old title 34, Navy, repealed 1956): its block ends empty
        anchor = {"year": anchor_year, "sections": {}, "through": CUTOFF[anchor_year], "url": []}
    if not eds:
        print(T, "no LoC editions"); return
    for e in eds:
        e["through"] = CUTOFF[e["year"]]
    anchor["through"] = anchor.get("through") or CUTOFF[anchor_year]
    seq = eds + [anchor]
    # Publication gaps: a section printed in the editions before and after one edition, but not read in it, with no
    # law removing it, is kept through that edition (as the history from 1994 does); the OCR missed its start.
    gaps = 0
    for i in range(1, len(seq) - 1):
        prev_s, cur_s, next_s = seq[i - 1]["sections"], seq[i]["sections"], seq[i + 1]["sections"]
        for n, s in prev_s.items():
            if n in cur_s or n not in next_s or "#" in n or s.get("repealed"):
                continue
            # the newer edition's (cleaner) text stands in for the edition that missed it
            cur_s[n] = dict(next_s[n], ocr="gap-carried", source_credit=s.get("source_credit", ""))
            gaps += 1

    def rend(n, s):
        if not s or s.get("repealed") and not s.get("lines"):
            return None
        return render_lines(T, n, s.get("heading") or "", s.get("lines") or [])

    commits = []
    first = eds[0]
    y0 = first["year"]
    files0 = {}
    for n, s in sorted(first["sections"].items(), key=lambda kv: sec_key(kv[0])):
        if "#" in n:
            continue
        r = rend(n, s)
        if r:
            files0[fname(T, n)] = r
    src0 = ", ".join(first["url"][:1]) + (f" and {len(first['url']) - 1} more" if len(first["url"]) > 1 else "")
    commits.append({
        "author": f"{y0} edition of the US Code", "email": f"{y0}@uscode-version.invalid", "date": first["through"],
        "message": (f"The {y0} edition of the US Code, title {T}: the start of this record\n\n"
                    + wrap(f"The text of title {T} as printed in the {EDITION_NAME.get(y0, f'{y0} edition of the United States Code')}"
                           f" (laws enacted through {fmt(first['through'])}), read from the Library of Congress scans of "
                           f"the printed edition. It is the earliest edition of the Code that prints this title, so this record of title {T} "
                           f"starts here: lines first seen in this commit are credited to this edition, not to the Acts that wrote "
                           f"them, which each section's source credit lists.") + "\n\n"
                    + wrap("The words are read from the scans by two OCR engines (Tesseract 5 and the Library's own text layer) and "
                           "checked against the next edition: where both readings agree with the next edition's words, allowing for "
                           "misread letters, the next edition's clean text is used; a difference is kept only where both readings "
                           "show it. Sections printed only in this edition keep the OCR reading.") + "\n\n"
                    + f"Consolidated: {first['through']}\nPrinted-in: {y0}\nSource: {src0}\n"),
        "files": files0})
    state = dict(files0)
    report = {"title": T, "pairs": []}

    for A, B in zip(seq, seq[1:]):
        ya, yb = A["year"], B["year"]
        ca, cb = A["through"], B["through"]
        by_law: dict[str, dict] = {}
        differs: list[tuple[str, str, str | None]] = []
        names = set(A["sections"]) | set(B["sections"])
        stats = {"changed": 0, "law": 0, "edition": 0}
        for n in sorted((x for x in names if "#" not in x), key=sec_key):
            a, b = A["sections"].get(n), B["sections"].get(n)
            path = fname(T, n)
            new = rend(n, b)
            old = state.get(path)
            if new == old:
                continue
            stats["changed"] += 1
            la, lb = laws_of(a), laws_of(b)
            def known(k):  # the older edition already names this law (an act with or without its chapter read)
                if k in la:
                    return True
                if k.startswith("act-"):
                    base = re.match(r"act-\d{4}-\d{2}-\d{2}", k).group(0)
                    return any(x == base or x.startswith(base + "-ch") and ("-ch" not in k) for x in la) or base in la
                return False

            fresh = {k: v for k, v in lb.items() if not known(k) and (v.get("enacted") or "0") <= cb
                     and (v.get("enacted") or "9") > (CUTOFF.get(ya - 6, "0000") if ya > 1925 else "0000")}
            # laws enacted after the older edition's cutoff (the newer edition is the first to print them)
            recent = {k: v for k, v in fresh.items() if (v.get("enacted") or "0") > ca}
            cand = recent or fresh
            if b and b.get("repealed") and not b.get("lines"):
                cand = laws_in_credit(b.get("heading", "") + " " + " ".join(" ".join(l[1] for l in b.get("lines") or []) for _ in [0])) or cand
            if not cand:
                why = ("not in the edition; removed" if new is None else
                       "neither its source credit nor its amendment notes name a law the earlier edition did not")
                differs.append((path, why, new))
                stats["edition"] += 1
                continue
            def day_of(key):
                d = cand[key].get("enacted") or cb
                return (date.fromisoformat(ca) + timedelta(days=1)).isoformat() if d <= ca else d

            latest = max(cand, key=lambda x: (day_of(x), x))
            steps: list[tuple[str, str | None, str]] = []  # (law key, file text after it, how credited)
            if len(cand) > 1 and old is not None and new is not None:
                # several laws: each changed run of lines goes to the law whose amendment note quotes its new words
                # (else the latest); the section then gets one version per law, in date order
                ol, nl = old.split("\n"), new.split("\n")
                ops = difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes()
                quotes = {}
                for e in note_entries(b):
                    ks = [kk for kk in laws_in_credit(" ".join(re.findall(
                        r"(?:Pub\.\s*L\.\s*\d{2,3}\s*[–—\-~]\s*\d{1,4}[^;.]*?\d{4})|(?:Act\s+(?:" + MONTHS + r")[.,]?\s+\d{1,2}[,.]?\s+\d{4}(?:,\s*(?:ch|c)\.\s*\d+)?)", e)))
                          if kk in cand]
                    qs = [q for q in re.findall(r"[“\"]([^”\"]{12,})[”\"]", e)]
                    for kk in ks:
                        quotes.setdefault(kk, []).extend(qs)
                owner = {}
                for i, (tag, i1, i2, j1, j2) in enumerate(ops):
                    if tag == "equal":
                        continue
                    seg_new = re.sub(r"\s+", " ", " ".join(nl[j1:j2]))
                    seg_old = re.sub(r"\s+", " ", " ".join(ol[i1:i2]))
                    hits = [kk for kk, qs in quotes.items() if any(re.sub(r"\s+", " ", q) in seg_new and
                                                                   re.sub(r"\s+", " ", q) not in seg_old for q in qs)]
                    owner[i] = max(hits, key=lambda x: (day_of(x), x)) if hits else latest
                order = sorted(set(owner.values()), key=lambda x: (day_of(x), x))
                done: set[int] = set()
                for kk in order:
                    done |= {i for i, o in owner.items() if o == kk}
                    text = []
                    for i, (tag, i1, i2, j1, j2) in enumerate(ops):
                        text.extend(nl[j1:j2] if (tag != "equal" and i in done) else ol[i1:i2] if tag != "equal" else ol[i1:i2])
                    how = ("its amendment note quotes the new words" if any(o == kk for o in owner.values()) and kk != latest
                           else f"the latest of {len(cand)} laws the edition newly names for this section")
                    steps.append((kk, "\n".join(text), how))
                steps[-1] = (steps[-1][0], new, steps[-1][2])
            else:
                steps.append((latest, new, "the only law the edition newly names for this section." if len(cand) == 1
                              else f"the latest of {len(cand)} laws the edition newly names for this section."))
            kind = "Added" if old is None else ("Repealed" if new is None else "Amended")
            for kk, text, how in steps:
                day = day_of(kk)
                rec = by_law.setdefault((kk, day), {"law": cand[kk], "key": kk, "day": day, "files": {}, "sections": []})
                rec["files"][path] = text
                rec["sections"].append((n, kind, how))
            stats["law"] += 1
        # an act cited without its chapter, where the pair names exactly one chaptered act of that day: the same law
        for (k, day) in [x for x in by_law if x[0].startswith("act-") and "-ch" not in x[0]]:
            same = [x for x in by_law if x[0].startswith(k + "-ch") and x[1] == day]
            if len(same) == 1:
                tgt = by_law[same[0]]
                src = by_law.pop((k, day))
                for p_, v in src["files"].items():
                    tgt["files"].setdefault(p_, v)
                tgt["sections"].extend(src["sections"])
        # sections the newer edition no longer prints, in a pair where one law added many sections (a re-enactment
        # of the title, e.g. title 1 by the Act of July 30, 1947): the old numbering went with that law
        added = {}
        for key, rec in by_law.items():
            added[key] = sum(1 for _, kind, _ in rec["sections"] if kind == "Added")
        if added and differs:
            big = max(added, key=lambda x: added[x])
            if added[big] >= 5:
                rec = by_law[big]
                keep = []
                for p_, why, v in differs:
                    if v is None and why.startswith("not in the edition"):
                        rec["files"][p_] = None
                        rec["sections"].append((p_.split("/")[1][:-3], "Removed",
                                                "the edition no longer prints it, and this law re-enacted the title "
                                                f"in the same edition (it adds {added[big]} sections)"))
                        stats["edition"] -= 1
                        stats["law"] += 1
                    else:
                        keep.append((p_, why, v))
                differs = keep
        for (k, day), rec in sorted(by_law.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            law = rec["law"]
            secs = rec["sections"]
            head = ", ".join(f"{T} U.S.C. §{n}" for n, _, _ in secs[:2]) + (f" and {len(secs) - 2} more" if len(secs) > 2 else "")
            body = [f"{law['name']}.",
                    wrap(f"In force {fmt(day)}. Dated the day it was enacted: this part of the record does not read "
                         f"effective dates." if law.get("enacted") and law["enacted"] == day else
                         f"In force {fmt(day)}: the law was enacted before the {ya} edition's cutoff but first printed "
                         f"in the {yb} edition, so it is dated the day after the cutoff."),
                    wrap(f"Enacted {fmt(law['enacted'])}." if law.get("enacted") else "Enactment date not read.") ,
                    wrap(f"The {yb} edition names this law in the source credit or amendment notes of each section below; "
                         f"the change is the difference between the {ya} and {yb} editions that the law accounts for. "
                         + ("Both editions are read from the Library of Congress scans." if yb < 1994 else
                            f"The {ya} edition is read from the Library of Congress scans; the {yb} edition is GovInfo's.")),
                    ""]
            for n, kind, how in secs:
                body.append(f"{T} U.S.C. §{n}. {kind}.")
                body.append(wrap("Credited to this law because " + how.rstrip(".") + ".", indent="  "))
            trailers = [f"Law: {law['name']}"]
            if law.get("enacted"):
                trailers.append(f"Enacted: {law['enacted']}")
            trailers.append(f"In-force: {day}")
            trailers.append(f"Printed-in: {yb}")
            if law.get("stat"):
                trailers.append(f"Statutes-at-Large: {law['stat']}")
            commits.append({"author": law["name"], "email": law["email"], "date": day,
                            "message": f"{law['name']}: {head}\n\n" + "\n".join(body) + "\n\n" + "\n".join(trailers) + "\n",
                            "files": dict(rec["files"])})
            state.update(rec["files"])
            for p_, v in rec["files"].items():
                if v is None:
                    state.pop(p_, None)
        if differs:
            files = {p_: v for p_, _, v in differs}
            lines = [f"- {T} U.S.C. §{p_.split('/')[1][:-3]}: {why}" for p_, why, _ in differs]
            head = ", ".join(f"{T} U.S.C. §{p_.split('/')[1][:-3]}" for p_, _, _ in differs[:2]) + (
                f" and {len(differs) - 2} more" if len(differs) > 2 else "")
            commits.append({"author": f"{yb} edition of the US Code", "email": f"{yb}@uscode-version.invalid", "date": cb,
                            "message": (f"Printed text differs: {head}\n\n"
                                        + wrap(f"The text below changed between the {ya} edition (laws enacted through {fmt(ca)}) "
                                               f"and the {yb} edition (through {fmt(cb)}), and the record does not credit it to a "
                                               f"law: the reason is given for each section. It is committed under the {yb} "
                                               f"edition's name on the day that edition is current through. Most are editorial "
                                               f"changes by the publisher; some are changes by laws the edition's notes name but "
                                               f"this record could not match to the words.") + "\n\n" + "\n".join(lines) + "\n\n"
                                        + f"Printed-in: {yb}\n"),
                            "files": files})
            for p_, _, v in differs:
                if v is None:
                    state.pop(p_, None)
                else:
                    state[p_] = v
        report["pairs"].append({"from": ya, "to": yb, **stats, "laws": len(by_law)})
        print(T, ya, "->", yb, stats, "laws", len(by_law), flush=True)

    # the block must end at the anchor's text exactly
    want = {fname(T, n): rend(n, s) for n, s in anchor["sections"].items() if "#" not in n and rend(n, s)}
    bad = [p for p in set(state) | set(want) if state.get(p) != want.get(p)]
    report["end_mismatch"] = len(bad)
    os.makedirs(BLOCKS, exist_ok=True)
    with gzip.open(os.path.join(BLOCKS, f"title{T}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(commits, f, ensure_ascii=False)
    with open(os.path.join(BLOCKS, f"title{T}.report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(T, "commits", len(commits), "end mismatch", len(bad))


if __name__ == "__main__":
    main()
