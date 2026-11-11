"""Reads the Office of the Law Revision Counsel's notes in an edition: amendment notes and effective-date notes.

An amendment note is grouped by year ("2022—") and made of entries such as
``Par. (51D)(B)(i). Pub. L. 117–151, §2(a)(1), inserted "under this title" after "affiliated debtors".``
Paragraphs that start with a quotation mark continue the entry above (they quote the provision's former text).
These notes are the publisher's own description of each amendment, so they are quoted beside our comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .editions import clean

_YEAR = re.compile(r"^\s*<b>(?P<y>\d{4})</b>\s*(?:&mdash;|—)\s*")
_LOCATION = re.compile(
    r"^(?P<loc>(?:Subsecs?|Pars?|Subpars?|Cls?|Subcls?|Items?|Subitems?)\.\s*"
    r"\([^)]+\)(?:\([^)]+\))*(?:(?:,\s*|\s+and\s+|\s+to\s+|,\s*and\s+)\([^)]+\)(?:\([^)]+\))*)*)\.\s+"
)
_LAW = re.compile(
    r"Pub\.\s*L\.\s*(?P<c>\d+)[–—\-](?P<n>\d+)"
    r"(?:,\s*(?P<ref>(?:div\.\s*[A-Z]+,\s*)?(?:title\s*[IVXLC]+,\s*)?(?:subtitle\s*[A-Z]+,\s*)?(?:part\s*[IVXLC0-9]+,\s*)?"
    r"§§?\s*[0-9]+[A-Za-z0-9\-]*(?:\([^)]+\))*(?:,\s*\([^)]+\)(?:\([^)]+\))*)*))?"
)


@dataclass
class LawRef:
    congress: int
    number: int
    ref: str = ""            # "div. A, title I, §1113(a)(4)(A)"

    @property
    def pl(self) -> str:
        return f"{self.congress}-{self.number}"

    def identifier_suffix(self) -> Optional[str]:
        """"§1113(a)(4)(A)" -> "/s1113/a/4/A", the tail of the law's USLM identifier for that provision."""
        m = re.search(r"§\s*([0-9]+[A-Za-z0-9\-]*)((?:\([^)]+\))*)", self.ref)
        if not m:
            return None
        parts = [f"s{m.group(1)}"] + re.findall(r"\(([^)]+)\)", m.group(2))
        return "/" + "/".join(parts)


@dataclass
class NoteEntry:
    year: int
    location: str             # "Par. (51D)(B)(i)"; "" when the entry covers the whole section
    paths: list[str]          # ["(51D)(B)(i)"]
    laws: list[LawRef]
    text: str                 # the entry as the publisher wrote it, plain text
    quotes: list[str] = field(default_factory=list)   # quoted passages in the entry

    def mentions(self, congress: int, number: int) -> bool:
        return any(l.congress == congress and l.number == number for l in self.laws)


def _paths(location: str) -> list[str]:
    """"subsec. (b)(5)(C), (6)(C), (10)(C)" -> ["(b)(5)(C)", "(b)(6)(C)", "(b)(10)(C)"]: a shorter group continues the
    first path at the same depth from the end."""
    paths: list[str] = []
    first: list[str] = []
    for m in re.finditer(r"(\([^)]+\)(?:\([^)]+\))*)", location):
        parts = re.findall(r"\([^)]+\)", m.group(1))
        if not first:
            first = parts
            paths.append("".join(parts))
        elif len(parts) < len(first):
            paths.append("".join(first[: len(first) - len(parts)] + parts))
        else:
            paths.append("".join(parts))
    return paths


def parse_amendment_notes(paragraphs: list[str]) -> list[NoteEntry]:
    entries: list[NoteEntry] = []
    year: Optional[int] = None
    location = ""
    for para in paragraphs:
        m = _YEAR.match(para)
        if m:
            year = int(m.group("y"))
            para = para[m.end():]
            location = ""
        if para.startswith("<h4>"):
            continue  # the "Amendments" heading
        text = clean(para)
        if not text or year is None:
            continue
        if text.startswith('"') and entries:
            entries[-1].text += " " + text
            entries[-1].quotes = re.findall(r'"([^"]+)"', entries[-1].text)
            continue
        lm = _LOCATION.match(text)
        if lm:
            location = lm.group("loc")
            body = text[lm.end():]
        else:
            body = text
        laws = [LawRef(int(x.group("c")), int(x.group("n")), (x.group("ref") or "").strip()) for x in _LAW.finditer(body)]
        entries.append(NoteEntry(year=year, location=location, paths=_paths(location), laws=laws, text=text, quotes=re.findall(r'"([^"]+)"', text)))
    return entries


@dataclass
class DateNote:
    kind: str                 # "effective", "termination", "effective and termination", "future amendment"
    heading: str              # "Effective Date of 2022 Amendment; Retroactive Application"
    text: str
    laws: list[LawRef]


_DATE_KINDS = {
    "effectivedate-amendment-note": "effective",
    "effectivedate-terminationdate-amendment-note": "effective and termination",
    "terminationdate-amendment-note": "termination",
    "futureamendment-note": "future amendment",
}


def parse_date_notes(notes: dict[str, list[str]]) -> list[DateNote]:
    out: list[DateNote] = []
    for kind_key, kind in _DATE_KINDS.items():
        paragraphs = notes.get(kind_key) or []
        heading, buffer = "", []

        def flush() -> None:
            if heading or buffer:
                text = " ".join(buffer)
                out.append(DateNote(kind, heading, text, [LawRef(int(x.group("c")), int(x.group("n")), (x.group("ref") or "").strip()) for x in _LAW.finditer(text)]))

        for para in paragraphs:
            text = clean(para)
            if para.startswith("<h4>"):
                flush()
                heading, buffer = text, []
            elif text:
                buffer.append(text)
        flush()
    return out
