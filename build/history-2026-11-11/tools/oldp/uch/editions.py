"""Parses an annual edition of a US Code title (GovInfo's HTML) into sections, provisions and notes.

GovInfo marks each section with a comment (``documentid:11_101 ... currentthrough:20230105``) and each part of it
with ``field-start``/``field-end`` comments: the heading, the statute text, the source credit and typed notes. The
statute text is a run of paragraphs whose class gives the nesting level (``statutory-body`` for subsections,
``statutory-body-1em`` for paragraphs and so on), so each paragraph can be given a path such as ``(51D)(B)(i)``.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from typing import Optional

from .structure import leading, path_of, push, unambiguous_rank

_SECTION = re.compile(r"<!-- documentid:(?P<doc>\S+)\s+usckey:\S+\s+currentthrough:(?P<through>\d{8})[^>]*-->")
_FIELD = re.compile(r"<!-- field-start:(?P<name>[a-z\-]+) -->(?P<body>.*?)<!-- field-end:(?P=name) -->", re.S)
_PARA = re.compile(r'<p class="(?P<cls>[^"]+)">(?P<body>.*?)</p>', re.S)
_DESIGNATION = re.compile(r'^\((?P<d>[0-9]+[A-Za-z]*(?:-[0-9]+)?|[a-z]{1,4}|[A-Z]{1,4}|[ivxlcdm]+|[IVXLCDM]+)\)')
_SUP = re.compile(r"<sup>.*?</sup>", re.S)
# A section number as the Code prints it: digits, then any letters, then an optional hyphenated part ("25A",
# "1395w-4", "1400Z-2"). The publisher's document ids use a hyphen where the text prints an en dash.
SECTION_NUMBER = re.compile(r"\d+[A-Za-z]*(?:-\d+[A-Za-z]*)?")
_NOTE_PART = re.compile(r'<(?P<tag>h4|p) class="[^"]*">(?P<body>.*?)</(?P=tag)>', re.S)


def clean(fragment: str) -> str:
    """Visible text of an HTML fragment, with footnote markers removed and spaces collapsed."""
    text = _SUP.sub("", fragment)
    text = re.sub(r"<br[^>]*>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Provision:
    path: str           # "(51D)(B)(i)"; "" for the section's opening words; "(b)(2) closing words" for text after a list
    level: int
    text: str
    order: int


@dataclass
class Section:
    number: str          # "101", "1182"
    heading: str
    current_through: str  # "2023-01-05": the date the edition says this section is current to
    provisions: list[Provision] = field(default_factory=list)
    repealed: bool = False
    source_credit: str = ""
    notes: dict[str, list[str]] = field(default_factory=dict)   # note type -> list of note paragraphs (HTML)

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.provisions)

    def subtree(self, path: str) -> list[Provision]:
        """The provision at path and everything nested under it, in order."""
        if path == "":
            return list(self.provisions)
        return [p for p in self.provisions if p.path == path or p.path.startswith(path + "(") or p.path.startswith(path + " ")]


@dataclass
class Edition:
    """One printed version of a title: an annual edition (key "2024") or an OLRC release point (key "pl119-83")."""
    title: int
    year: int
    sections: dict[str, Section]
    sha256: str
    url: str
    fetched_at: str
    key: str = ""
    label: str = ""
    title_name: str = ""                          # "Copyrights", from the title's heading
    kind: str = "edition"
    through_law: Optional[tuple[int, int]] = None   # a release point includes every law up to and including this one
    page: str = ""

    def __post_init__(self) -> None:
        self.key = self.key or str(self.year)
        self.label = self.label or f"{self.year} edition"

    @property
    def current_through(self) -> str:
        dates = sorted({s.current_through for s in self.sections.values()})
        return dates[-1] if dates else ""


def _level(cls: str) -> Optional[int]:
    m = re.fullmatch(r"statutory-body(?:-(\d)em)?", cls)
    if m:
        return int(m.group(1) or 0)
    return None


def _block_level(cls: str) -> Optional[int]:
    m = re.fullmatch(r"statutory-body-block(?:-(\d)em)?", cls)
    if m:
        return int(m.group(1) or 0)
    m = re.fullmatch(r"statutory-body-flush(\d)_hang\d", cls)
    if m:
        return int(m.group(1))
    return None


# "(E) Continuity of rates and terms.—(i) If the decision ...": a list can open on its heading's line, after the dash.
_INLINE = re.compile(r"—(?=\((?:[0-9]+[A-Z]?|[a-z]{1,4}|[A-Z]{1,4})\)\s)")


# Some titles (7, 15, 26, 42 and others) print a provision's designation and heading as a heading element of its own,
# "<h4 class="paragraph-head">(1) In general</h4>", with its words in the paragraph after it.
_HEAD_LEVELS = {"subsection": 0, "paragraph": 1, "subparagraph": 2, "clause": 3, "subclause": 4, "item": 5, "subitem": 6, "subsubitem": 7}
_BLOCK = re.compile(r'<(?P<tag>p|h4) class="(?P<cls>[^"]+)">(?P<body>.*?)</(?P=tag)>', re.S)


def _body_class(level: int) -> str:
    return "statutory-body" if level == 0 else f"statutory-body-{level}em"


def _lines(body: str) -> list[tuple[str, str]]:
    """The statute's paragraphs as (class, text), with a list that opens after a heading's dash on a line of its own,
    one indent deeper, the way the provisions it holds are printed. A heading printed as an element of its own is read
    the way the statute prints it and amending laws quote it: "(1) In general.—" followed by the provision's own words
    when the next paragraph holds them, or on a line of its own when the provision goes straight into a list."""
    out: list[tuple[str, str]] = []
    head: Optional[tuple[int, str]] = None
    for m in _BLOCK.finditer(body):
        cls, text = m.group("cls"), clean(m.group("body"))
        if m.group("tag") == "h4":
            kind = cls[:-5] if cls.endswith("-head") else ""
            if kind not in _HEAD_LEVELS or not text:
                continue
            if head:
                out.append((_body_class(head[0]), head[1] + ".—"))
            head = (_HEAD_LEVELS[kind], text.rstrip(".—: "))
            continue
        if not text:
            continue
        level = _level(cls)
        if head:
            # The provision's own words follow its heading at the provision's own indent and carry no designation.
            if level == head[0] and not leading(text)[0]:
                text, cls = f"{head[1]}.—{text}", _body_class(head[0])
                level = head[0]
            else:
                out.append((_body_class(head[0]), head[1] + ".—"))
            head = None
        hit = _INLINE.search(text) if level is not None and leading(text)[0] else None
        if hit:
            out.append((cls, text[: hit.start() + 1]))
            out.append((f"statutory-body-{level + 1}em", text[hit.start() + 1:]))
        else:
            out.append((cls, text))
    if head:
        out.append((_body_class(head[0]), head[1] + ".—"))
    return out


def parse_statute(body: str) -> list[Provision]:
    """Provisions with paths built from their designations (see structure.py). Printed indentation is used only to
    place undesignated text: closing words after a list belong to the deepest open provision printed at or left of
    their indent."""
    provisions: list[Provision] = []
    stack: list[tuple[int, str]] = []
    printed: list[int] = []          # printed indent of each open provision, parallel to stack
    offset: Optional[int] = None     # printed indent minus rank, from the last unambiguous designation
    counts: dict[str, int] = {}

    def owner(level: int) -> str:
        depth = 0
        for n, lvl in enumerate(printed):
            if lvl <= level:
                depth = n + 1
        return path_of(stack[:depth])

    for order, (cls, text) in enumerate(_lines(body)):
        level = _level(cls)
        if level is not None:
            designations, _ = leading(text)
            if designations:
                # "(B)(i) includes ...": a provision with no words of its own is printed on its first child's line.
                # Indentation is read relative to the last designation that could only be one thing, so it holds
                # whether a section starts with subsections or with paragraphs.
                first = designations[0]
                known = unambiguous_rank(first)
                expected = level - offset if offset is not None and known is None else None
                for k, d in enumerate(designations):
                    push(stack, d, expected if k == 0 else None)
                    del printed[len(stack) - 1:]
                    printed.append(level)
                if known is not None:
                    offset = level - known
                path = path_of(stack)
            elif not provisions:
                path = ""
            else:
                parent = owner(level)
                counts[parent] = counts.get(parent, 0) + 1
                path = f"{parent} text {counts[parent]}".strip()
            provisions.append(Provision(path, level, text, order))
            continue
        level = _block_level(cls)
        if level is None:
            level = 0
        parent = owner(level)
        counts[parent] = counts.get(parent, 0) + 1
        provisions.append(Provision(f"{parent} closing words {counts[parent]}".strip(), level, text, order))
    return provisions


_START = re.compile(r"<!-- field-start:(?P<name>[a-z\-]+) -->")


def _fields(chunk: str) -> dict[str, list[str]]:
    """Every field in a section, including fields nested inside others (notes sit inside a "notes" field)."""
    fields: dict[str, list[str]] = {}
    for start in _START.finditer(chunk):
        name = start.group("name")
        end = chunk.find(f"<!-- field-end:{name} -->", start.end())
        if end >= 0:
            fields.setdefault(name, []).append(chunk[start.end():end])
    return fields


def parse_edition(raw: bytes, *, title: int, year: int, sha256: str, url: str, fetched_at: str, **version) -> Edition:
    page = raw.decode("utf-8", errors="replace")
    head = re.search(r'class="usc-title-head">\s*TITLE\s+\d+[A-Z]?\s*(?:&mdash;|—)\s*([^<]+)<', page)
    version.setdefault("title_name", head.group(1).strip().title() if head else "")
    marks = list(_SECTION.finditer(page))
    sections: dict[str, Section] = {}
    for i, mark in enumerate(marks):
        doc = mark.group("doc")
        chunk = page[mark.end(): marks[i + 1].start() if i + 1 < len(marks) else len(page)]
        number = doc.split("_", 1)[1] if "_" in doc else doc
        # Section numbers: "101", "1395w", "25A", "4980H", "78a-1", "1400Z-2". Chapter and subchapter headings, the
        # analysis tables and bracketed placeholders for repealed or renumbered sections ("[28") are left out.
        if not SECTION_NUMBER.fullmatch(number):
            continue
        fields = _fields(chunk)
        through = mark.group("through")
        heading = clean((fields.get("head") or fields.get("repealedhead") or [""])[0])
        section = Section(
            number=number,
            heading=re.sub(r"^§\s*" + re.escape(number).replace(r"\-", "[-–]") + r"\.\s*", "", heading),
            current_through=f"{through[:4]}-{through[4:6]}-{through[6:]}",
            repealed="repealedhead" in fields or "repealsummary" in fields,
            source_credit=clean((fields.get("sourcecredit") or [""])[0]),
        )
        if "statute" in fields:
            section.provisions = parse_statute(fields["statute"][0])
        elif "repealsummary" in fields:
            section.provisions = [Provision("", 0, clean(fields["repealsummary"][0]), 0)]
        for name, bodies in fields.items():
            if name.endswith("-note"):
                # Note headings are <h4> elements; they are kept, wrapped in <h4>, so readers can split notes on them.
                for b in bodies:
                    for p in _NOTE_PART.finditer(b):
                        part = p.group("body") if p.group("tag") == "p" else f"<h4>{p.group('body')}</h4>"
                        section.notes.setdefault(name, []).append(part)
        sections[number] = section
    return Edition(title=title, year=year, sections=sections, sha256=sha256, url=url, fetched_at=fetched_at, **version)
