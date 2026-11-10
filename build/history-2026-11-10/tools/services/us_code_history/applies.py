"""When a change came into force, and what it applies to, from the effective-date notes in an edition.

A law rarely dates its amendments in the amending instruction itself. It does so in a separate provision ("The
amendments made by subsection (a) shall take effect 180 days after the date of enactment of this Act"), which the
Office of the Law Revision Counsel prints as an effective-date note under each section it touches, either quoted:

    Pub. L. 116–136, div. A, title I, §1113(a)(3), Mar. 27, 2020, 134 Stat. 311, provided that: "The amendment made by
    paragraph (1) [amending this section] shall apply only with respect to cases commenced under title 11, United States
    Code, on or after the date of enactment of this Act [Mar. 27, 2020]."

or as a cross-reference:

    Amendment by section 2(c) of Pub. L. 117–151 effective June 21, 2022, see section 2(h)(1) of Pub. L. 117–151, set
    out as a note under section 104 of this title.

One note can carry several such provisions, for several laws. Each is read here into the amendments it covers (by the
law's own designations, resolved against where the provision sits) and what it says: a date the amendments take
effect, a condition they wait on, or the cases, proceedings or events they apply to. A change then takes the most
specific provision of its own law that covers its instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Optional

from .laws import _NUMBER_WORDS, _add

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_DATE = r"(?:Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}[,.]\s*\d{4}"
_N = r"(?P<n>\d+|one|two|three|four|five|six)"
_DASH = "[–—-]"
_UNITS = {"subsection": 1, "paragraph": 2, "subparagraph": 3, "clause": 4, "subclause": 5}
_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def iso(text: str) -> Optional[str]:
    """"Mar. 27, 2020", "March 27, 2020" or "Dec. 27. 2020" (a typo the notes carry) -> "2020-03-27"."""
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})[,.]\s*(\d{4})", text.strip())
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    return _date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()


def spoken(d: str) -> str:
    y, m, day = (int(x) for x in d.split("-"))
    return f"{_MONTH_NAMES[m - 1]} {day}, {y}"


@dataclass(frozen=True)
class Place:
    """A provision of a public law: division, title, section and the designations below it. Section None is the whole
    law; a title with no section is the whole title."""
    division: Optional[str] = None
    title: Optional[str] = None
    section: Optional[str] = None
    path: tuple[str, ...] = ()

    def covers(self, other: "Place") -> bool:
        if self.division and other.division and self.division != other.division:
            return False
        if self.section is None:
            return self.title is None or self.title == other.title
        return self.section == other.section and other.path[: len(self.path)] == self.path

    @property
    def rank(self) -> int:
        return 0 if self.section is None and self.title is None else 1 if self.section is None else 2 + len(self.path)


def place_of_identifier(identifier: str) -> Optional[tuple[str, Place]]:
    """"/us/pl/116/136/dA/tI/s1113/b/1/A/i" -> ("116-136", Place("A", "I", "1113", ("b", "1", "A", "i")))."""
    m = re.match(r"/us/pl/(\d+)/(\d+)/(.*)$", identifier or "")
    if not m:
        return None
    division = title = section = None
    path: list[str] = []
    for part in m.group(3).split("/"):
        if section is None:
            if part.startswith("d") and part[1:].isupper():
                division = part[1:]
            elif part.startswith("t") and re.fullmatch(r"t[IVXLC]+", part):
                title = part[1:]
            elif part.startswith("s") and re.match(r"s\d", part):
                section = part[1:]
        else:
            path.append(part)
    return f"{m.group(1)}-{m.group(2)}", Place(division, title, section, tuple(path))


def place_of_ref(ref: str) -> Place:
    """"div. A, title I, §1113(b)(1)(D)(i)" -> Place("A", "I", "1113", ("b", "1", "D", "i"))."""
    div = re.search(r"div\.\s*([A-Z]+)", ref)
    title = re.search(r"title\s+([IVXLC]+)\b", ref)
    sec = re.search(r"§\s*(\d+[A-Za-z\-]*)((?:\([^)]+\))*)", ref)
    return Place(div.group(1) if div else None, title.group(1) if title else None,
                 sec.group(1) if sec else None, tuple(re.findall(r"\(([^)]+)\)", sec.group(2))) if sec else ())


@dataclass
class Provision:
    law: str                   # "116-136": the law whose amendments this provision dates
    source: str                # "Pub. L. 116–136, div. A, title I, §1113(a)(3)", where the provision is
    covers: list[Place]
    words: str                 # the provision's own words, as the note gives them
    in_force: Optional[str] = None
    in_force_words: str = ""
    condition: Optional[str] = None
    applies: list[dict] = field(default_factory=list)


# ---- Splitting a note into its provisions ----

_START = re.compile(rf"(?:(?:^|(?<=\. )|(?<=\.\" )|(?<=\.” )|(?<=\] ))(?=Pub\. L\. \d+{_DASH}\d+,|Amendments? by )|(?<=, and )(?=amendments? by ))")
_HEAD = re.compile(
    rf"^Pub\. L\. (?P<c>\d+){_DASH}(?P<n>\d+),\s*(?P<ref>.*?),\s*(?P<date>{_DATE}),\s*\d+ Stat\. [\d, ]*?\d,\s*"
    rf"(?:as amended by .*?\d+ Stat\. [\d, ]*?\d,\s*)?provided(?: in part)? that:?,?\s*(?P<body>.*)$",
    re.S,
)
_CROSS = re.compile(
    rf"^[Aa]mendments? by (?:(?:section|sections) (?P<sec>\d+[A-Za-z\-]*)(?P<path>(?:\([^)]+\))*)(?: of)? )?(?:div\. (?P<div>[A-Z]+) of )?"
    rf"Pub\. L\. (?P<c>\d+){_DASH}(?P<n>\d+),?\s*(?P<body>.*)$",
    re.S,
)


def provisions(text: str, kind: str = "effective") -> list[Provision]:
    starts = [m.start() for m in _START.finditer(text)]
    out: list[Provision] = []
    for a, b in zip(starts, starts[1:] + [len(text)]):
        piece = text[a:b].strip()
        head = _HEAD.match(piece)
        if head:
            law = f"{head.group('c')}-{head.group('n')}"
            approved = iso(head.group("date"))
            ref = head.group("ref").strip()
            base = place_of_ref(ref)
            source = f"Pub. L. {head.group('c')}–{head.group('n')}, {ref}"
            body = head.group("body").strip().strip('"“”').strip()
            if kind == "future amendment":
                # The note is the amending instruction itself, dated: it covers its own provision.
                out += _read(law, source, [Place(base.division, base.title, base.section, base.path)], body, approved)
            else:
                out += _segments(law, source, base, body, approved)
            continue
        cross = _CROSS.match(piece)
        if cross:
            law = f"{cross.group('c')}-{cross.group('n')}"
            covers = [Place(cross.group("div"), None, cross.group("sec"), tuple(re.findall(r"\(([^)]+)\)", cross.group("path") or "")))] if cross.group("sec") else [Place()]
            body = re.sub(r",?\s*see (?:section|sections) .*$", "", cross.group("body"), flags=re.S).strip(" ,")
            source = f"Pub. L. {cross.group('c')}–{cross.group('n')}"
            see = re.search(r"see ((?:section|sections) [^,]+(?:, [^,]*?)?) of (?:div\. [A-Z]+ of )?Pub\. L\.", cross.group("body"))
            if see:
                source = f"{source}, {see.group(1).replace('section ', '§').replace('sections ', '§§')}"
            out += _read(law, source, covers, body, None)
    return out


# The anchors that start a statement inside a quoted provision: "the amendments made by subsection (c)", "This Act".
_ANCHOR = re.compile(
    r"(?:[Tt]he amendments? made by |(?<![a-z] )(?=(?:This|Such) (?:Act|title|subtitle|section|subsection)\b)|(?<=\. )(?=(?:Sections?|Subsections?) [\d(]))"
    r"(?P<what>(?:this|such) (?:Act|title|subtitle|section|subsection|paragraph|subparagraph)|This (?:Act|title|subtitle|section|subsection)|Such (?:Act|title|section)"
    r"|(?:[Ss]ections?|[Ss]ubsections?|[Pp]aragraphs?|[Ss]ubparagraphs?|[Cc]lauses?) (?:\d+[A-Za-z\-]*)?(?:\([^)]+\))+(?:(?:,\s*|,? and |,? or )(?:\d+[A-Za-z\-]*)?(?:\([^)]+\))+)*"
    r"|[Ss]ections? \d+[A-Za-z\-]*(?:(?:,\s*|,? and )\d+[A-Za-z\-]*)*)"
)


def _resolve(what: str, base: Place) -> list[Place]:
    w = what.lower()
    if w.endswith("act"):
        return [Place()]
    if w.endswith("title") and not w.endswith("subtitle"):
        return [Place(base.division, base.title)]
    if w in ("this section", "such section"):
        return [Place(base.division, base.title, base.section)]
    if w in ("this subsection", "such subsection"):
        return [Place(base.division, base.title, base.section, base.path[:1])]
    if w in ("this paragraph",):
        return [Place(base.division, base.title, base.section, base.path[:2])]
    if w in ("this subparagraph",):
        return [Place(base.division, base.title, base.section, base.path[:3])]
    if w.endswith("subtitle"):
        return [Place(base.division, base.title)]
    unit = re.match(r"(section|subsection|paragraph|subparagraph|clause)s?\b", w)
    if not unit:
        return []
    items = re.findall(r"(\d+[A-Za-z\-]*)?((?:\([^)]+\))+)|(\d+[A-Za-z\-]*)", what[unit.end():])
    out = []
    for num, parens, bare in items:
        designations = tuple(re.findall(r"\(([^)]+)\)", parens or ""))
        if unit.group(1) == "section":
            out.append(Place(base.division, base.title, num or bare, designations))
        else:
            depth = _UNITS[unit.group(1)] - 1
            out.append(Place(base.division, base.title, base.section, base.path[:depth] + designations))
    return out


def _segments(law: str, source: str, base: Place, body: str, approved: Optional[str]) -> list[Provision]:
    anchors = list(_ANCHOR.finditer(body))
    if not anchors:
        return _read(law, source, [Place(base.division, base.title, base.section)], body, approved)
    out: list[Provision] = []
    for i, m in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(body)
        segment = body[m.start():end]
        # "This Act [...] and the amendments made by this Act shall take effect": the second anchor names the same
        # thing, so the statement belongs to both.
        covers = _resolve(m.group("what"), base)
        if covers:
            out += _read(law, source, covers, segment, approved)
    # A segment with no statement of its own ("Section 3 and") borrows the next one's.
    for i, p in enumerate(out):
        if not (p.in_force or p.condition or p.applies) and i + 1 < len(out):
            n = out[i + 1]
            p.in_force, p.in_force_words, p.condition, p.applies = n.in_force, n.in_force_words, n.condition, n.applies
    return out


# ---- Reading what a provision says ----

def _dates(text: str, approved: Optional[str]) -> str:
    """Turn every date in the words into ⟨ISO⟩: the bracketed date of enactment, "the date of enactment of this Act",
    printed dates, and periods after them."""
    t = re.sub(r"\[(?:Pub\. L\. [^\]]*?, approved )?(" + _DATE + r")\]", lambda m: f"⟨{iso(m.group(1))}⟩", text)
    t = re.sub(r"the date of (?:the )?enactment of (?:this Act|the [A-Z][^⟨\[]{0,120}?)\s*(?=⟨)", "", t)
    if approved:
        t = re.sub(r"the date of (?:the )?enactment of this Act", f"⟨{approved}⟩", t)
        t = re.sub(r"the date of (?:the )?enactment\b", f"⟨{approved}⟩", t)
    t = re.sub(_DATE, lambda m: f"⟨{iso(m.group(0))}⟩", t)
    t = re.sub(r"\[[^\]]*\]\s*", "", t)   # the publisher's bracketed asides
    period = re.compile(rf"(?:on )?(?:the date that is )?{_N} (?P<u>year|month|day)s? after ⟨(?P<d>[\d-]+)⟩")
    while True:
        m = period.search(t)
        if not m:
            break
        n = int(m.group("n")) if m.group("n").isdigit() else _NUMBER_WORDS[m.group("n").lower()]
        t = t[:m.start()] + f"⟨{_add(m.group('d'), n, m.group('u'))}⟩" + t[m.end():]
    # "October 1 that first occurs after the date of enactment": the next such day.
    m = re.search(r"(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December) (?P<day>\d{1,2}) that first occurs (?P<on>on or )?after ⟨(?P<d>[\d-]+)⟩", t)
    if m:
        y = int(m.group("d")[:4])
        nxt = _date(y, _MONTH_NAMES.index(m.group("mon")) + 1, int(m.group("day"))).isoformat()
        if nxt < m.group("d") or (nxt == m.group("d") and not m.group("on")):
            nxt = _date(y + 1, _MONTH_NAMES.index(m.group("mon")) + 1, int(m.group("day"))).isoformat()
        t = t[:m.start()] + f"⟨{nxt}⟩" + t[m.end():]
    m = re.search(r"(?:on )?the first day of the calendar quarter that first occurs on or after ⟨([\d-]+)⟩", t)
    if m:
        y, mo, d = (int(x) for x in m.group(1).split("-"))
        q = _date(y, ((mo - 1) // 3) * 3 + 1, 1)
        if q.isoformat() < m.group(1):
            q = _date(y + (1 if q.month == 10 else 0), 1 if q.month == 10 else q.month + 3, 1)
        t = t[:m.start()] + f"⟨{q.isoformat()}⟩" + t[m.end():]
    return t


_IN_FORCE = re.compile(r"(?:take effect|(?:is |be |become )?effective|shall apply) (?:on |as of |beginning on )?⟨(?P<d>[\d-]+)⟩")
_LEAD = re.compile(r"^,?\s*(?:effective )?(?:on )?⟨(?P<d>[\d-]+)⟩,")
_FISCAL = re.compile(r"(?:take effect|effective) with respect to fiscal year (?P<y>\d{4})")
_CONDITION = re.compile(r"(?:take effect|effective) on the date on which (?P<c>[^;]+?)(?:,? and applicable|[;.]|$)")
_APPLIES = re.compile(
    r"(?P<neg>not )?(?:apply|applicable)(?: only)?(?: with respect)?(?: to| in)? (?P<what>(?:(?!⟨)[^.;])+?)"
    r"(?P<rel>before, on, or after|on or after|before|after|pending on) ⟨(?P<d>[\d-]+)⟩"
)


def _tidy(what: str) -> str:
    w = re.sub(r"[\"“”]", "", what)
    w = re.sub(r"\s*—\s*", " ", w)
    w = re.sub(r"\(\s*[A-Za-z0-9]{1,4}\s*\)\s*", "", w)
    w = re.sub(r"(?:, United States Code,?| of the United States Code)", "", w)   # "title 11, United States Code," -> "title 11"
    w = re.sub(r"\s+", " ", w).strip(" ,")
    return w


def _read(law: str, source: str, covers: list[Place], words: str, approved: Optional[str]) -> list[Provision]:
    t = _dates(words, approved)
    p = Provision(law, source, covers, re.sub(r"\s+", " ", words).strip())
    m = _IN_FORCE.search(t) or _LEAD.search(t)
    if m and not re.search(r"apply (?:only )?(?:with respect )?(?:to|in)", t[max(0, m.start() - 5):m.end()]):
        p.in_force, p.in_force_words = m.group("d"), m.group(0)
    f = _FISCAL.search(t)
    if f and not p.in_force:
        p.in_force, p.in_force_words = f"{int(f.group('y')) - 1}-10-01", f"with respect to fiscal year {f.group('y')} and each fiscal year after"
    c = _CONDITION.search(t)
    if c and not p.in_force:
        p.condition = re.sub(r"\s+", " ", c.group("c")).strip()
    for a in _APPLIES.finditer(t):
        what, rel = _tidy(a.group("what")), a.group("rel")
        if a.group("neg"):
            # "shall not apply with respect to cases commenced before the date of enactment"
            rel = {"before": "on or after", "on or after": "before", "after": "on or before"}.get(rel, rel)
        if not what:
            continue
        p.applies.append(_scope(what, rel, a.group("d"), t[a.end():]))
        # "..., and with respect to a case that was commenced on or after ⟨…⟩, and before ⟨…⟩, that is pending on ⟨…⟩":
        # further groups of cases the same provision reaches, each with all of its conditions.
        rest = t[a.end():]
        for more in _MORE.finditer(rest):
            if _APPLIES.search(rest[:more.start()]):
                break
            w = _tidy(more.group("what"))
            if w:
                p.applies.append(_scope(w, more.group("rel"), more.group("d"), rest[more.end():]))
    return [p]


# A further group of cases after the first ("and with respect to a case that was commenced on or after ⟨…⟩"), and the
# extra conditions that can follow any group ("and before ⟨…⟩", "that is pending on ⟨…⟩").
_MORE = re.compile(
    r",?\s*and (?:with respect )?to (?P<what>(?:(?!⟨)[^.;])+?)(?P<rel>before, on, or after|on or after|before|after|pending on) ⟨(?P<d>[\d-]+)⟩"
)
_EXTRA = re.compile(r"^,?\s*(?:and |that |which )?(?:(?:is|was|are|were) )?(?P<rel>on or after|before|after|pending on) ⟨(?P<d>[\d-]+)⟩")


def _scope(what: str, rel: str, d: str, after: str) -> dict:
    """One group of cases a change applies to, with every condition the law sets on it, not only the first."""
    conditions = [{"relation": rel, "date": d}]
    while (x := _EXTRA.match(after)):
        conditions.append({"relation": x.group("rel"), "date": x.group("d")})
        after = after[x.end():]
    parts = [f"{rel} {spoken(d)}"] + [f"and {'is pending on' if c['relation'] == 'pending on' else c['relation']} {spoken(c['date'])}" for c in conditions[1:]]
    return {"text": f"{what[0].upper()}{what[1:]} {', '.join(parts)}", "relation": rel, "date": d, "conditions": conditions}


# ---- For one change ----

def applies(law: str, identifier: str, notes: list, enacted: Optional[str], effective: Optional[str], timing: str) -> dict:
    """What dates one recorded change: when it came into force and what it applies to. `notes` are the DateNotes of
    the section in the edition that first printed the change; `effective` and `timing` are what the law's own
    instruction says, which takes precedence over the notes."""
    found = place_of_identifier(identifier)
    mine: list[tuple[int, Provision]] = []
    if found:
        _, at = found
        for note in notes:
            for p in provisions(note.text, note.kind):
                if p.law != law:
                    continue
                best = max((c.rank for c in p.covers if c.covers(at)), default=-1)
                if best >= 0:
                    mine.append((best, p))
    else:
        # A change known only from the publisher's note has no amending provision to match. The law's date provisions
        # in this section's notes still govern it, but only when they are about a single amendment, or all say the
        # same thing; otherwise one written for another amendment could be applied to this one.
        own = [p for note in notes for p in provisions(note.text, note.kind) if p.law == law]
        targets = {tuple(sorted(map(repr, p.covers))) for p in own}
        readings = {(p.in_force, p.condition, tuple(a["text"] for a in p.applies)) for p in own}
        if own and (len(targets) == 1 or len(readings) == 1):
            mine = [(0, p) for p in own]
    mine.sort(key=lambda x: -x[0])
    # The most specific provision that dates the change, or sets a condition for it, decides when it came into force.
    dated = next((p for _, p in mine if p.in_force or p.condition), None)
    applying = next((p for _, p in mine if p.applies), None)
    if effective:
        in_force = {"date": effective, "basis": "law", "words": timing, "source": "", "condition": None}
    elif dated and dated.in_force:
        in_force = {"date": dated.in_force, "basis": "note", "words": dated.words, "source": dated.source, "condition": None}
    elif dated:
        in_force = {"date": None, "basis": "condition", "words": dated.words, "source": dated.source, "condition": dated.condition}
    else:
        in_force = {"date": enacted, "basis": "enactment", "words": "", "source": "", "condition": None}
    to = [{**a, "words": applying.words, "source": applying.source} for a in applying.applies] if applying else []
    return {"in_force": in_force, "to": to}


_WHOLE = re.compile(r"(?:\(a\) In General\.\W+)?(?:Except as provided in [^,]+, )?(?:This Act|[Tt]he amendments made by this Act)")


def whole_act_dates(notes: list[tuple[str, dict]]) -> dict[str, dict]:
    """In-force dates set for a whole Act by a quoted provision, by law: {"116-54": in_force}. `notes` are (law,
    date note as recorded) pairs. A publisher's cross-reference naming only the law is not enough: it is often a
    summary for one amendment of a large Act."""
    out: dict[str, dict] = {}
    for _, n in notes:
        for p in provisions(n["text"], n["kind"]):
            if p.law in out or not p.in_force or "§" not in p.source or not _WHOLE.match(p.words):
                continue
            if any(c == Place() for c in p.covers):
                out[p.law] = {"date": p.in_force, "basis": "note", "words": p.words, "source": p.source, "condition": None}
    return out
