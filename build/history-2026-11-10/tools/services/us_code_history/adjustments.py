"""Dollar-amount adjustments: changes to the Code made by a Federal Register notice, not by a bill.

Every three years the Judicial Conference adjusts the dollar amounts in title 11 under section 104, by a notice in the
Federal Register. The Law Revision Counsel records each one in an "Adjustment of Dollar Amounts" note:
``By notice dated Jan. 31, 2022, 87 F.R. 6625, effective Apr. 1, 2022, in subsec. (b), dollar amount "6,825" was
adjusted to "7,575" each time it appeared.`` Each notice becomes a cause with instructions that can be replayed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .editions import Section, clean
from .laws import Instruction, Op
from .notes import _paths

_ENTRY = re.compile(
    # Each entry's body ends at the next notice, so an older notice's clauses are never filed under a newer one.
    r"By notice dated (?P<dated>[A-Z][a-z]+\.? \d{1,2}, \d{4}), (?P<vol>\d+) F\.R\. (?P<page>\d+), effective (?P<eff>[A-Z][a-z]+\.? \d{1,2}, \d{4}), (?P<body>.+?)(?=\.\s*See notice|\s*By notice dated|$)"
)
_CLAUSE = re.compile(
    r"in (?:subsecs?|pars?|subpars?|cls?|subcls?|items?)\.\s*(?P<loc>\([^)]+\)(?:\([^)]+\))*(?:,\s*(?:and\s+)?\([^)]+\)(?:\([^)]+\))*)*),\s*"
    r"dollar amounts? (?P<olds>\"[^\"]+\"(?:,? (?:and )?\"[^\"]+\")*) (?:was|were) adjusted to (?P<news>\"[^\"]+\"(?:,? (?:and )?\"[^\"]+\")*)"
    r"(?P<each>,? each time (?:it|they) appeared)?"
)


def _date(text: str) -> str:
    text = text.replace(".", "")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


@dataclass
class Notice:
    id: str                 # "87-FR-6625"
    citation: str           # "87 F.R. 6625"
    dated: str
    effective: str
    url: str
    instructions: list[Instruction] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"Judicial Conference notice, {self.citation}"


def notices_in(section: Section, title: int) -> list[Notice]:
    out: dict[str, Notice] = {}
    paragraphs = [clean(p) for k, v in section.notes.items() if k == "miscellaneous-note" for p in v]
    text = " ".join(paragraphs)
    start = text.find("Adjustment of Dollar Amounts")
    if start < 0:
        return []
    for m in _ENTRY.finditer(text[start:]):
        nid = f"{m.group('vol')}-FR-{m.group('page')}"
        notice = out.setdefault(nid, Notice(
            id=nid, citation=f"{m.group('vol')} F.R. {m.group('page')}", dated=_date(m.group("dated")),
            effective=_date(m.group("eff")), url=f"https://www.federalregister.gov/citation/{m.group('vol')}-FR-{m.group('page')}",
        ))
        for n, c in enumerate(_CLAUSE.finditer(m.group("body"))):
            olds = re.findall(r'"([^"]+)"', c.group("olds"))
            news = re.findall(r'"([^"]+)"', c.group("news"))
            if len(olds) != len(news):
                continue
            for path in _paths(c.group("loc")):
                ops = [Op("replace_all" if c.group("each") else "replace", {"old": "$" + o, "new": "$" + w}) for o, w in zip(olds, news)]
                notice.instructions.append(Instruction(
                    identifier=f"/notice/{nid}/s{section.number}{path}/{n}",
                    label=f"{notice.citation}, in {path or 'the section'}",
                    title=title,
                    section=section.number,
                    path=path,
                    text=f"In {('§' + section.number + path)}, dollar amount{'s' if len(olds) > 1 else ''} " + ", ".join(f'"{o}"' for o in olds)
                         + f" adjusted to " + ", ".join(f'"{w}"' for w in news) + (" each time it appeared" if c.group("each") else "") + ".",
                    ops=ops,
                    effective=notice.effective,
                    timing=f"effective {m.group('eff')}",
                ))
    return list(out.values())
