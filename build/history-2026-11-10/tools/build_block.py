"""Builds the pre-2017 block of one US Code title: commits from the earliest GovInfo edition (1994) to the text
main's 2017 baseline gives, one commit per public law per date, credited from the editions' own records.

    python build_block.py <title> [--first 1994]

Reads data/title<T>/<year>.json.gz (fetch_parse.py) and the clone's main; writes blocks/title<T>.json.gz: a list of
commits {author, email, date, message, files: {path: text | null}} and blocks/title<T>.report.json.

How a change is credited. Between two consecutive editions, a section whose text changed is credited to the public
laws the newer edition names for it and the older one did not: in the section's source credit or its amendment notes.
One new law: the whole change is its. Several: each changed run of lines goes to the law whose amendment-note entry
quotes the new words, else names the provision, else amends the section as a whole; two or more such laws: the latest
(its words are the ones printed). A change no law can be matched to is committed under the newer edition's name, as
"Printed text differs", with the laws it could be listed. A law's commit is dated the day it was enacted (from the
source credit, else GovInfo's metadata), or the day after the older edition's cutoff if it was enacted before it.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import json
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from render import render_lines  # noqa: E402
from services.us_code_history.notes import parse_amendment_notes  # noqa: E402

CLONE = ROOT / "clone"
UA = "Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)"
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "aug": 8,
          "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_PL = re.compile(r"Pub\.\s*L\.\s*(\d+)\s*[–—\-]\s*(\d+)")
_PL_DATED = re.compile(r"Pub\.\s*L\.\s*(\d+)\s*[–—\-]\s*(\d+)\b([^;]*?)\b(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),\s+(\d{4})")
_STAT = re.compile(r"(\d+)\s+Stat\.\s+(\d+)")
_SUFFIX = re.compile(r"\s+(?:text|closing words)(?:\s+\d+)?$")


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


def pl_key(pl: str):
    c, n = pl.split("-")
    return (int(c), int(n))


# ---- Laws: enactment dates and names ----

class Laws:
    def __init__(self) -> None:
        self.path = ROOT / "data" / "laws.json"
        self.db: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.main_names = self._main_names()

    @staticmethod
    def _main_names() -> dict[str, str]:
        out = subprocess.run(["git", "log", "--format=%ae|%an", "origin/main"], cwd=CLONE, capture_output=True, text=True, encoding="utf-8").stdout
        names = {}
        for line in out.splitlines():
            email, _, name = line.partition("|")
            m = re.fullmatch(r"pl-(\d+-\d+)@public-law\.invalid", email)
            if m:
                names[m.group(1)] = name
        return names

    def save(self) -> None:
        self.path.write_text(json.dumps(self.db, indent=0, sort_keys=True), encoding="utf-8")

    def note_credit(self, credit: str) -> None:
        """Enactment dates and Statutes at Large pages from a source credit."""
        for m in _PL_DATED.finditer(credit):
            pl = f"{int(m.group(1))}-{int(m.group(2))}"
            if ";" in m.group(3) or _PL.search(m.group(3)):
                continue
            d = date(int(m.group(6)), MONTHS[m.group(4).lower()], int(m.group(5))).isoformat()
            rec = self.db.setdefault(pl, {})
            rec.setdefault("enacted_credit", d)
            stat = _STAT.search(credit[m.end(): m.end() + 40])
            if stat:
                rec.setdefault("stat", f"{stat.group(1)} Stat. {stat.group(2)}")

    def mods(self, pl: str) -> None:
        rec = self.db.setdefault(pl, {})
        if "mods" in rec:
            return
        c, n = pl.split("-")
        if int(c) < 104:
            rec["mods"] = None
            return
        url = f"https://www.govinfo.gov/metadata/pkg/PLAW-{c}publ{n}/mods.xml"
        for attempt in range(3):
            try:
                r = httpx.get(url, headers={"user-agent": UA}, timeout=60, follow_redirects=True)
                time.sleep(1.5)
                if r.status_code == 404 or b"<mods" not in r.content[:3000]:
                    rec["mods"] = None
                    return
                r.raise_for_status()
                text = r.text
                title = re.search(r"<shortTitle[^>]*>([^<]+)</shortTitle>", text)
                issued = re.search(r"<dateIssued[^>]*>(\d{4}-\d{2}-\d{2})<", text)
                rec["mods"] = {"short_title": title.group(1).strip() if title else "", "issued": issued.group(1) if issued else ""}
                return
            except httpx.HTTPError:
                time.sleep(10 + 20 * attempt)
        rec["mods"] = None

    def enacted(self, pl: str) -> str | None:
        rec = self.db.get(pl, {})
        mods = rec.get("mods") or {}
        return rec.get("enacted_credit") or mods.get("issued") or None

    def author(self, pl: str) -> tuple[str, str]:
        if pl in self.main_names:
            return self.main_names[pl], f"pl-{pl}@public-law.invalid"
        name = ((self.db.get(pl, {}).get("mods") or {}).get("short_title") or "").strip()
        label = f"Pub. L. {pl}"
        return (f"{label} ({name})" if name else label), f"pl-{pl}@public-law.invalid"

    def name(self, pl: str) -> str:
        a = self.author(pl)[0]
        m = re.fullmatch(r"Pub\. L\. \S+ \((.*)\)", a)
        return m.group(1) if m else a

    def source(self, pl: str) -> str:
        c, n = pl.split("-")
        if int(c) >= 104:
            return f"https://www.govinfo.gov/content/pkg/PLAW-{c}publ{n}/html/PLAW-{c}publ{n}.htm"
        stat = self.db.get(pl, {}).get("stat")
        if stat:
            v, p = stat.split(" Stat. ")
            return f"https://www.govinfo.gov/app/details/STATUTE-{v}/STATUTE-{v}-Pg{p}"
        return ""


# ---- Editions ----

def load(title: int, year: int) -> dict | None:
    p = ROOT / "data" / f"title{title}" / f"{year}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


_NOTE_YEAR = re.compile(r"^\s*(\d{4})\s*(&mdash;|\u2014)")


def amend_entries(sec: dict | None) -> list:
    """The section's amendment-note entries. Editions before about 2009 print a year group as "1998&mdash;" rather
    than "<b>1998</b>&mdash;", which notes.py expects; the year is wrapped here so both read the same."""
    if not sec:
        return []
    paras = [_NOTE_YEAR.sub(r"<b>\1</b>\2", x) for x in sec.get("notes", {}).get("amendment-note") or []]
    return parse_amendment_notes(paras)


def laws_of(sec: dict | None) -> set[str]:
    """Public laws a section's record names: its source credit, its heading ("Repealed. Pub. L. 115-97, ...") and its
    amendment notes."""
    if not sec:
        return set()
    found = {f"{int(a)}-{int(b)}" for a, b in _PL.findall(sec.get("source_credit", "") + " " + sec.get("heading", ""))}
    for e in amend_entries(sec):
        found |= {l.pl for l in e.laws}
    return found


_FRACTIONS = {"\u00bd": "1/2", "\u00bc": "1/4", "\u00be": "3/4", "\u2153": "1/3", "\u2154": "2/3", "\u215b": "1/8",
              "\u215c": "3/8", "\u215d": "5/8", "\u215e": "7/8", "\u2155": "1/5", "\u2156": "2/5", "\u2157": "3/5",
              "\u2158": "4/5", "\u2159": "1/6", "\u215a": "5/6", "\u2150": "1/7", "\u2151": "1/9", "\u2152": "1/10"}


def typo_norm(t: str) -> str:
    """The words of a line without the publisher's typography: quotes, apostrophes, fractions, dashes and spacing."""
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"').replace("\u00a0", " ")
    for k, v in _FRACTIONS.items():
        t = re.sub(r"(\d)" + k, r"\1 " + v, t).replace(k, v)
    t = t.replace("\u2013", "-").replace("--", "\u2014")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*\u2014\s*", "\u2014", t)
    return t.strip()


def carry_typography(eds: list[dict]) -> int:
    """The editions change typography now and then (fractions as "½" from 2011, curly apostrophes from 2013) without a
    change in the words. A line whose words are the same as the next edition's line at the same place takes that
    line's typography, latest edition first, so a typographic change does not show as a change to the law (git blame
    would otherwise credit the whole line to the edition). Returns the number of lines retouched."""
    n = 0
    for later, earlier in zip(eds[::-1], eds[::-1][1:]):
        for num, sec in earlier["sections"].items():
            nxt = later["sections"].get(num)
            if not nxt:
                continue
            by_path: dict[str, list] = {}
            by_norm: dict[str, str] = {}
            for line in nxt["lines"]:
                by_path.setdefault(line[0], []).append(line)
                by_norm.setdefault(typo_norm(line[1]), line[1])
            for line in sec["lines"]:
                key = typo_norm(line[1])
                cand = next((l[1] for l in by_path.get(line[0], []) if typo_norm(l[1]) == key), None) or by_norm.get(key)
                if cand is not None and cand != line[1]:
                    line[1] = cand
                    n += 1
            if sec.get("heading") and nxt.get("heading") and sec["heading"] != nxt["heading"] and typo_norm(sec["heading"]) == typo_norm(nxt["heading"]):
                sec["heading"] = nxt["heading"]
                n += 1
    return n


_PH = re.compile(r"^\[\s*§§?\s*(?P<nums>.+?)\.\s+(?P<kind>Repealed|Transferred|Renumbered|Omitted|Reserved|Vacant|Redesignated)", re.I)


def placeholder_for(n: str, edition: dict) -> tuple[str, str] | None:
    """The edition's bracketed placeholder that covers section n ("[§§54A to 54F. Repealed. Pub. L. 115–97, ...]"):
    (its text, its kind), or None."""
    for ph in edition.get("placeholders", []):
        m = _PH.match(ph)
        if not m:
            continue
        nums = m.group("nums").replace("\u2013", "-")
        if " to " in nums:
            lo, hi = [x.strip() for x in nums.split(" to ", 1)]
            if sec_key(lo) <= sec_key(n) <= sec_key(hi):
                return ph, m.group("kind").capitalize()
        elif n in [x.strip() for x in re.split(r",\s*|\s+and\s+", nums)]:
            return ph, m.group("kind").capitalize()
    return None


def main_targets(title: int) -> dict[str, str]:
    """title-T/<file> -> text, as main's 2017 baseline commits added them."""
    log = subprocess.run(["git", "log", "--format=%H %ae", "origin/main"], cwd=CLONE, capture_output=True, text=True).stdout
    bases = [h for h, e in (l.split() for l in log.splitlines()) if e == "2017@uscode-version.invalid"]
    blobs: dict[str, str] = {}
    for b in bases:
        out = subprocess.run(["git", "diff-tree", "-r", "--root", "--no-commit-id", "--diff-filter=A", b, "--", f"title-{title}/"], cwd=CLONE, capture_output=True, text=True).stdout
        for line in out.splitlines():
            meta, path = line.split("\t", 1)
            blobs[path] = meta.split()[3]
    if not blobs:
        return {}
    shas = list(blobs.values())
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=CLONE, input="\n".join(shas).encode() + b"\n", capture_output=True)
    data, pos, texts = proc.stdout, 0, {}
    for sha in shas:
        nl = data.index(b"\n", pos)
        size = int(data[pos:nl].split()[2])
        texts[sha] = data[nl + 1: nl + 1 + size].decode("utf-8")
        pos = nl + 1 + size + 1
    return {p: texts[s] for p, s in blobs.items()}


# ---- Crediting one section's change ----

def base_path(p: str) -> str:
    return _SUFFIX.sub("", p).strip()


def hunks(a: list[tuple[str, str]], b: list[tuple[str, str]]):
    sm = difflib.SequenceMatcher(None, [tuple(x) for x in a], [tuple(x) for x in b], autojunk=False)
    return sm.get_opcodes()


def assemble(a, b, ops, take: set[int]) -> list:
    out = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal" or k not in take:
            out.extend(a[i1:i2])
        else:
            out.extend(b[j1:j2])
    return out


def straight(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))


def quotes_of(e) -> list[str]:
    return re.findall(r'"([^"]+)"', straight(e.text))


def credit_hunk(old: list, new: list, entries: dict[str, list], laws: list[str], dates: dict[str, str]) -> tuple[str | None, str, list[str]]:
    """Returns (law or None, how, other laws that also fit)."""
    new_text = straight(" ".join(x[1] for x in new))
    old_text = straight(" ".join(x[1] for x in old))
    paths = {base_path(x[0]) for x in old + new}
    latest = lambda xs: sorted(xs, key=lambda l: (dates.get(l) or "9999", pl_key(l)))[-1]  # noqa: E731
    quoted = [l for l in laws if any(len(q) >= 12 and q in new_text and q not in old_text for e in entries.get(l, []) for q in quotes_of(e))]
    if quoted:
        return latest(quoted), "its amendment note quotes the new words", [l for l in quoted if l != latest(quoted)]
    by_path = []
    for l in laws:
        for e in entries.get(l, []):
            if any(h == p or h.startswith(p) or (h and p.startswith(h)) for p in e.paths for h in paths if p):
                by_path.append(l)
                break
    if by_path:
        return latest(by_path), "its amendment note names the provision", [l for l in by_path if l != latest(by_path)]
    whole = [l for l in laws if any(not e.paths for e in entries.get(l, []))]
    if len(whole) == 1:
        return whole[0], "its amendment note covers the section", []
    return None, "", laws


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("title", type=int)
    ap.add_argument("--first", type=int, default=1994)
    ap.add_argument("--last", type=int, default=2017)
    args = ap.parse_args()
    T = args.title
    lawdb = Laws()
    eds = []
    for y in range(args.first, args.last + 1):
        e = load(T, y)
        if e is None:
            if (ROOT / "data" / f"title{T}" / f"{y}.missing").exists():
                continue   # GovInfo does not publish this title for this year (title 26, 2004)
            raise SystemExit(f"missing data for title {T} {y}")
        eds.append(e)
        for s in e["sections"].values():
            lawdb.note_credit(s.get("source_credit", ""))
    retouched = carry_typography(eds)
    print(f"title {T}: typography carried back on {retouched} lines", flush=True)
    targets = main_targets(T)
    if not targets:
        raise SystemExit(f"main has no 2017 baseline for title {T}")
    prefix = f"title-{T}/"

    def fname(n: str) -> str:
        return f"{prefix}{n}.md"

    # Title 17's §104A, §106A and §121A came into main with title 26's block, written by the newer generator.
    v2_files = {"104A", "106A", "121A"} if T == 17 else set()

    def rend(n: str, heading: str, lines) -> str | None:
        return render_lines(T, n, heading, [tuple(x) for x in lines], "v2" if n in v2_files else None)

    commits: list[dict] = []
    report = {"title": T, "windows": [], "credited_hunks": 0, "edition_hunks": 0, "laws": {}}
    first = eds[0]
    # state: n -> (heading, lines); files: path -> text
    state: dict[str, tuple[str, list]] = {}
    files: dict[str, str] = {}
    for n, s in first["sections"].items():
        state[n] = (s["heading"], [tuple(x) for x in s["lines"]])
        r = rend(n, s["heading"], s["lines"])
        if r is not None:
            files[fname(n)] = r
    ed0 = first["year"]
    commits.append({
        "author": f"{ed0} edition of the US Code", "email": f"{ed0}@uscode-version.invalid", "date": first["through"],
        "message": (f"The {ed0} edition of the US Code, title {T}: the start of this record\n\n"
                    + wrap(f"The text of title {T} as printed in the {ed0} edition of the United States Code, current "
                           f"through {fmt(first['through'])} (laws enacted through that day), as published by GovInfo. "
                           f"GovInfo publishes no earlier edition, so this record of title {T} starts here: lines first "
                           f"seen in this commit are credited to this edition, not to the Acts that wrote them, which "
                           f"each section's source credit lists.") + "\n\n"
                    + wrap(f"The commits after it, up to the 2017 edition, are built from the annual editions and their "
                           f"own records: one commit for each public law, on the day it was enacted, with the changes "
                           f"the next edition printed and credited to it in the section's source credit or amendment "
                           f"notes. Changes no law could be matched to are committed under the edition that first "
                           f"printed them. From the 2017 edition on, the history is main's, unchanged.") + "\n\n"
                    + wrap(f"Typography follows the latest printing: where an edition prints the same words as the next "
                           f"edition with other quotation marks, apostrophes, fractions or spacing, the later form is "
                           f"used, so a change of typesetting does not show as a change to the law. The words are the "
                           f"edition's own.") + "\n\n"
                    + f"Consolidated: {first['through']}\nPrinted-in: {ed0}\nSource: {first['url']}\n"),
        "files": dict(files),
    })

    for P, E in zip(eds, eds[1:]):
        final = E is eds[-1]
        p_through, e_through = P["through"], E["through"]
        floor = (date.fromisoformat(p_through) + timedelta(days=1)).isoformat()
        per_law: dict[str, dict] = {}            # law -> {"files": {path: (hunk set, ...)}, "lines": [...]}
        assigned: dict[str, dict[int, str]] = {}  # section -> hunk index -> law
        edition_notes: list[str] = []
        plans = {}
        names = set(state) | set(E["sections"])
        if final:
            names |= {p[len(prefix):-3] for p in targets}
        for n in sorted(names, key=sec_key):
            sb = E["sections"].get(n)
            sa = P["sections"].get(n)
            cur = state.get(n)
            target_lines = [tuple(x) for x in sb["lines"]] if sb else []
            target_head = sb["heading"] if sb else (cur[0] if cur else "")
            target_text = rend(n, target_head, target_lines) if sb else None
            if final:
                target_text = targets.get(fname(n))
            have = files.get(fname(n))
            if target_text is None and sb is None:
                # Left the edition as a section: the file goes (main's 2017 text keeps no file for such sections). The
                # edition's placeholder for it ("[§54. Repealed. Pub. L. 115–97, ...]") names the law, if any.
                if have is not None:
                    ph = placeholder_for(n, E)
                    ph_laws = sorted({f"{int(x)}-{int(y)}" for x, y in _PL.findall(ph[0])}, key=pl_key) if ph else []
                    plans[n] = {"kind": "removed", "ph": ph, "new": ph_laws[-1:]}
                    for l in ph_laws[-1:]:
                        if not lawdb.enacted(l) or l not in lawdb.main_names:
                            lawdb.mods(l)
                continue
            if have == target_text:
                if sb is not None:
                    state[n] = (target_head, target_lines)
                continue
            new = sorted(laws_of(sb) - laws_of(sa), key=pl_key) if sb else []
            if sb and sa:
                # A law the older edition already named can amend the section again (or have more of its amendments
                # carried out): laws named in note entries the older edition did not have count too.
                old_entries = {typo_norm(e.text) for e in amend_entries(sa)}
                # The law an entry is about is the first it names ("Pub. L. 105-206 made a technical amendment to ...
                # Pub. L. 105-34" is Pub. L. 105-206's).
                fresh = {e.laws[0].pl for e in amend_entries(sb) if e.laws and typo_norm(e.text) not in old_entries and e.year >= P["year"] - 3}
                new = sorted(set(new) | fresh, key=pl_key)
            if sb and not sa:
                # A section new to the Code: the laws its credit and notes name, enacted since about a year before.
                cutoff = (date.fromisoformat(p_through) - timedelta(days=366)).isoformat()
                new = [l for l in sorted(laws_of(sb), key=pl_key) if (lawdb.enacted(l) or "0000") >= cutoff]
            plans[n] = {"kind": "change", "sb": sb, "new": new, "target_text": target_text, "target_head": target_head, "target_lines": target_lines}
            for l in new:
                lawdb.mods(l) if not lawdb.enacted(l) or l not in lawdb.main_names else None

        dates = {l: lawdb.enacted(l) for p in plans.values() for l in p.get("new", [])}
        # Work out which law each changed run of lines goes to.
        law_changes: dict[str, list] = {}   # law -> [(n, hunk idxs, how, also, entries)]
        leftovers: list[tuple[str, str]] = []  # (n, why)
        for n, plan in plans.items():
            if plan["kind"] == "removed" and plan["new"]:
                law_changes.setdefault(plan["new"][0], []).append((n, f"the {E['year']} edition's placeholder for the section names it", [], []))
            if plan["kind"] != "change":
                continue
            cur = state.get(n, (plan["target_head"], []))
            a, b = list(cur[1]), plan["target_lines"]
            ops = hunks(a, b)
            idx = [k for k, o in enumerate(ops) if o[0] != "equal"]
            head_changed = cur[0] != plan["target_head"]
            entries: dict[str, list] = {}
            old_entries = {typo_norm(e.text) for e in amend_entries(P["sections"].get(n))}
            for e in amend_entries(plan["sb"]):
                if e.laws and e.laws[0].pl in plan["new"]:
                    e.fresh = typo_norm(e.text) not in old_entries
                    entries.setdefault(e.laws[0].pl, []).append(e)
            for l in entries:
                # Entries this edition added first: they are the ones that describe this change.
                entries[l].sort(key=lambda e: not e.fresh)
            plan.update(a=a, ops=ops, cur_head=cur[0], is_new=n not in state)
            new = plan["new"]
            give: dict[int, str] = {}
            if len(new) == 1:
                give = {k: new[0] for k in idx}
                if head_changed:
                    give[-1] = new[0]
                law_changes.setdefault(new[0], []).append((n, "the only law the edition newly names for this section", [], entries.get(new[0], [])))
            elif new:
                hows: dict[str, set] = {}
                for k in idx:
                    _, i1, i2, j1, j2 = ops[k]
                    law, how, also = credit_hunk(a[i1:i2], b[j1:j2], entries, new, dates)
                    if law:
                        give[k] = law
                        hows.setdefault(law, set()).add(how)
                        report["credited_hunks"] += 1
                    else:
                        report["edition_hunks"] += 1
                if head_changed:
                    heads = [l for l in new if any(re.search(r"catchline|heading", e.text, re.I) for e in entries.get(l, []))]
                    if heads:
                        give[-1] = sorted(heads, key=lambda l: (dates.get(l) or "9999", pl_key(l)))[-1]
                for law in sorted(set(give.values())):
                    law_changes.setdefault(law, []).append((n, "; ".join(sorted(hows.get(law, {"its amendment note names the section heading"}))), [], entries.get(law, [])))
                if len(set(give)) < len(idx) + (1 if head_changed else 0):
                    leftovers.append((n, "the edition newly names " + ", ".join(f"Pub. L. {l}" for l in new) + ", and part of the change could not be matched to one of them"))
            else:
                why = "the section is new to the edition and names no recent law" if plan["is_new"] else \
                    "neither its source credit nor its amendment notes name a law the earlier edition did not"
                leftovers.append((n, why))
            plan["give"] = give

        # Commits for each law, in order of enactment.
        def law_date(l: str) -> str:
            d = dates.get(l)
            if not d or d > e_through:
                return e_through
            return max(d, floor)

        applied: dict[str, set] = {n: set() for n in plans}
        for law in sorted(law_changes, key=lambda l: (law_date(l), pl_key(l))):
            day = law_date(law)
            changed_files = {}
            body = []
            for n, how, _, entries in sorted(law_changes[law], key=lambda x: sec_key(x[0])):
                plan = plans[n]
                if plan["kind"] == "removed":
                    if files.get(fname(n)) is not None:
                        changed_files[fname(n)] = None
                        files.pop(fname(n), None)
                        state.pop(n, None)
                        body.append(f"{T} U.S.C. §{n}. {plan['ph'][1]}. Publisher's note only.")
                        body.append(wrap(f"Credited to this law because {how}: {plan['ph'][0]}", 72, "  "))
                    plan["done"] = True
                    continue
                take = {k for k, l in plan["give"].items() if l == law}
                applied[n] |= take
                lines = assemble(plan["a"], plan["target_lines"], plan["ops"], {k for k in applied[n] if k >= 0})
                head = plan["target_head"] if -1 in applied[n] else plan["cur_head"]
                text = rend(n, head, lines)
                state[n] = (head, lines)
                if text != files.get(fname(n)):
                    changed_files[fname(n)] = text
                    if text is None:
                        files.pop(fname(n), None)
                    else:
                        files[fname(n)] = text
                    kind = "Added" if plan["is_new"] else ("Repealed" if (plan["sb"] or {}).get("repealed") and not P["sections"].get(n, {}).get("repealed") else "Amended")
                    body.append(f"{T} U.S.C. §{n}. {kind}. Publisher's note only.")
                    body.append(wrap(f"Credited to this law because {how}.", 72, "  "))
                    for e in entries[:4]:
                        body.append(wrap(f"Note: {e.text[:500]}{'…' if len(e.text) > 500 else ''}", 72, "  "))
            if not changed_files:
                continue
            places = [f"{T} U.S.C. §{p[len(prefix):-3]}" for p in changed_files]
            name = lawdb.name(law)
            author, email = lawdb.author(law)
            enacted = dates.get(law)
            if not enacted:
                why_day = f"Its enactment date is not in the record, so it is dated the day the {E['year']} edition is current through."
            elif enacted < floor:
                why_day = (f"Enacted {fmt(enacted)}, but the {P['year']} edition, current through {fmt(p_through)}, does not print "
                           f"this change, so it is dated the day after that edition's cutoff.")
            elif enacted > e_through:
                why_day = f"Enacted {fmt(enacted)}; dated the day the {E['year']} edition that prints it is current through."
            else:
                why_day = "Dated the day it was enacted: this part of the record does not read effective dates."
            head = "\n".join(wrap(p) for p in [
                f"Pub. L. {law}, {name}." if name != f"Pub. L. {law}" else f"Pub. L. {law}.",
                f"In force {fmt(day)}. {why_day}",
                f"Enacted {fmt(enacted) if enacted else 'on a date not in the record'}. First printed in the {E['year']} edition (current through {fmt(e_through)}).",
                f"The {E['year']} edition names this law in the source credit or amendment notes of each section below; "
                f"the change is the difference between the {P['year']} and {E['year']} editions that the law accounts for. "
                f"Laws before the 113th Congress are not published as structured text, so it is not confirmed by replay.",
            ])
            trailers = [f"Law: Pub. L. {law}", f"Enacted: {enacted or 'unknown'}", f"In-force: {day}", f"Printed-in: {E['year']}"]
            src = lawdb.source(law)
            if src:
                trailers.append(f"Source: {src}")
            subject = f"{name}: {', '.join(places[:2])}{f' and {len(places) - 2} more' if len(places) > 2 else ''}"
            commits.append({"author": author, "email": email, "date": day,
                            "message": f"{subject}\n\n{head}\n\n" + "\n".join(body) + "\n\n" + "\n".join(trailers) + "\n",
                            "files": changed_files})
            report["laws"][law] = report["laws"].get(law, 0) + len(changed_files)

        # The edition: whatever no law accounts for, and sections that left the Code.
        changed_files = {}
        lines_out = []
        for n, plan in sorted(plans.items(), key=lambda x: sec_key(x[0])):
            if plan["kind"] == "removed":
                if plan.get("done"):
                    report["law"] = report.get("law", 0) + 1
                    continue
                changed_files[fname(n)] = None
                files.pop(fname(n), None)
                state.pop(n, None)
                report["edition"] = report.get("edition", 0) + 1
                lines_out.append(wrap(f"- {T} U.S.C. §{n}: not in the {E['year']} edition as a section; removed"
                                      + (f" (the edition's placeholder: {plan['ph'][0]})" if plan["ph"] else ""), 72).replace("\n", "\n  "))
                continue
            text = plan["target_text"]
            outcome = "law" if files.get(fname(n)) == text else ("partial" if plan.get("give") else "edition")
            report[outcome] = report.get(outcome, 0) + 1
            if files.get(fname(n)) != text:
                changed_files[fname(n)] = text
                if text is None:
                    files.pop(fname(n), None)
                else:
                    files[fname(n)] = text
                why = next((w for m, w in leftovers if m == n), "the text differs from what the laws credited above account for")
                if final and plan["sb"] is not None:
                    printed = rend(n, plan["target_head"], plan["target_lines"])
                    if printed != text:
                        gone = [l for l in difflib.ndiff((printed or "").splitlines(), (text or "").splitlines()) if l[:2] in ("- ", "+ ")]
                        if gone and all(l.startswith("- ") for l in gone):
                            gap = (f"main's 2017 text lacks {len(gone)} line(s) the 2017 edition prints, paragraphs GovInfo "
                                   f"marks with a style attribute, which the parser behind main skips")
                        else:
                            gap = "main's 2017 text differs from the printed 2017 edition here"
                        why = gap if files.get(fname(n)) == printed else f"{why}; and {gap}"
                        report["main_gap_files"] = report.get("main_gap_files", 0) + 1
                lines_out.append(wrap(f"- {T} U.S.C. §{n}: {why}", 72) .replace("\n", "\n  "))
            if plan["sb"] is not None:
                state[n] = (plan["target_head"], plan["target_lines"])
            elif n in state and text is None:
                state.pop(n, None)
        if final:
            for p in list(files):
                if p not in targets:
                    changed_files[p] = None
                    files.pop(p)
                    lines_out.append(f"- {T} U.S.C. §{p[len(prefix):-3]}: removed; main's 2017 text keeps no file for it")
        if changed_files:
            places = [f"{T} U.S.C. §{p[len(prefix):-3]}" for p in changed_files]
            ey = E["year"]
            intro = (f"The text below changed between the {P['year']} edition (current through {fmt(p_through)}) and the "
                     f"{ey} edition (current through {fmt(e_through)}), and the record does not credit it to a law: the "
                     f"reason is given for each section. It is committed under the {ey} edition's name on the day that "
                     f"edition is current through, so the difference stays visible instead of being folded into a law's "
                     f"commit. Most are editorial changes by the publisher; some are changes by laws the edition's notes "
                     f"name but this record could not match to the words.")
            if final:
                intro += (f" This is the last commit before main's history of title {T}: it brings every file to the text "
                          f"main's 2017 edition commit gives, so the history continues from it unchanged.")
            commits.append({"author": f"{ey} edition of the US Code", "email": f"{ey}@uscode-version.invalid", "date": e_through,
                            "message": f"Printed text differs: {', '.join(places[:2])}{f' and {len(places) - 2} more' if len(places) > 2 else ''}\n\n"
                                       + wrap(intro) + "\n\n" + "\n".join(lines_out) + f"\n\nPrinted-in: {ey}\nSource: {E['url']}\n",
                            "files": changed_files})
            report["edition_sections"] = report.get("edition_sections", 0) + len(changed_files)
        report["windows"].append({"from": P["year"], "to": E["year"], "laws": len(law_changes), "edition_files": len(changed_files)})
        lawdb.save()
        print(f"title {T} {P['year']}->{E['year']}: {len(law_changes)} laws, {len(changed_files)} edition files", flush=True)

    # The block must end at main's 2017 text exactly.
    assert files == targets, (len(files), len(targets), sorted(set(files) ^ set(targets))[:5])
    out = ROOT / "blocks"
    out.mkdir(exist_ok=True)
    with gzip.open(out / f"title{T}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(commits, f, ensure_ascii=False)
    report["commits"] = len(commits)
    (out / f"title{T}.report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"title {T}: {len(commits)} commits", flush=True)


if __name__ == "__main__":
    main()
