"""Reads a public law (GovInfo USLM XML plus its MODS metadata) and extracts every instruction that amends a title.

USLM tags an amending instruction's parts: ``<ref href="/us/usc/t11/s101/51D/B">`` names the target,
``<amendingAction type="insert|delete|amend|...">`` the action and ``<quotedText>``/``<quotedContent>`` the words.
Instructions nest: "Section 101(51D)(B) ... is amended— (1) in clause (i), by inserting ... ". Each leaf instruction
is resolved to a full target (section and provision path) and a list of operations a program can replay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

from .sources import fetch, law_page, law_url

NS = "http://schemas.gpo.gov/xml/uslm"
_Q = f"{{{NS}}}"
LEVELS = ["section", "subsection", "paragraph", "subparagraph", "clause", "subclause", "item", "subitem", "subsubitem"]
_LEVEL_TAGS = {_Q + name for name in LEVELS} | {_Q + n for n in ("division", "title", "subtitle", "part", "subpart", "chapter", "subchapter")}
_UNIT = r"(?:section|subsection|paragraph|subparagraph|clause|subclause|item|subitem)s?"
_SKIP = {_Q + "page", _Q + "sidenote", _Q + "footnote", _Q + "note"}
# A section number in an amending law's words: "101", "25A", "1400Z–2" (printed with an en dash; kept with a hyphen,
# as the Code's document ids have it).
_SEC = r"\d+[A-Za-z]*(?:[-–]\d+[A-Za-z]*)?"


def _sec(number: str) -> str:
    return number.replace("–", "-")


_IRC = r"(?:the )?Internal Revenue Code of 1986"
_IRC_RULE = re.compile(
    r"whenever in this (?P<unit>Act|division|title|subtitle|part|subpart|chapter|subchapter|section),? an amendment or repeal "
    r"is expressed in terms of an amendment to,? or repeal of,? a section or other provision,? the reference shall be "
    r"considered to be made to a section or other provision of " + _IRC, re.I)
_IRC_UNITS = r"(?:subsection|paragraph|subparagraph|clause|subclause|item|subitem)s?"
# "Section 45Q", "Subsection (g) of section 6695", "Paragraph (2) of section 529A(b)", "The last sentence of section
# 179(d)(1)", "So much of section 448(c) as precedes paragraph (2)", at the start of an instruction.
_IRC_LEAD = re.compile(
    r"\s*(?:(?:So much of |The (?:first|second|third|fourth|last) sentence of |The heading (?:of|for) )?"
    r"(?:" + _IRC_UNITS + r" (?P<des>(?:\([^)]+\))+)(?P<more>(?:(?:,|,? and) (?:\([^)]+\))+)*) of )?)?"
    r"[Ss]ections? (?P<sec>" + _SEC + r")(?![\w–-])(?P<path>(?:\([^)]+\))*)", re.I)
# "Part IV of subchapter A of chapter 1 is amended by adding at the end the following new section": the new sections
# are matched like a chapter added whole.
_IRC_CHAPTER = re.compile(
    r"\s*(?:(?:Subpart|Part|Subchapter) [A-Z0-9]+ of )*(?:(?:subpart|part|subchapter) [A-Z0-9]+ of )*[Cc]hapter (?P<ch>\d+[A-Z]?)\b"
    r"(?P<rest>[^.]{0,60})")


def _irc_target(words: str, *, in_scope: bool) -> Optional[tuple[int, str, str]]:
    """Title 26 target named in an instruction's own words: by "of the Internal Revenue Code of 1986" anywhere, or, in
    a part of a law whose amendments are to that Code, by a section or chapter number at the start of the words. A
    number followed by "of" another law or title ("Section 1001 of the Social Security Act") is not taken."""
    # Only the reference the instruction opens with names its target; a section named later in the words ("as defined
    # in section 7701 of the Internal Revenue Code of 1986") is not what is amended.
    words = re.sub(r"^\s*(?:Effective [^,]{0,120},|On the date that is [^,]{0,120},|In the case of [^,]{0,120},)\s*", "", words)
    named = re.compile(r",?\s*of (?:such Code\b|" + _IRC + r")")
    other = re.compile(r",?\s*of (?!such Code\b|" + _IRC + r")")
    m = _IRC_LEAD.match(words)
    if m:
        rest = words[m.end():]
        rest = re.sub(r"^\s*(?:\((?:as|relating to)[^()]*(?:\([^()]*\)[^()]*)*\)|,\s*as [^,]*,)\s*", " ", rest)
        if other.match(rest) or not (in_scope or named.match(rest)):
            return None
        # "Paragraph (2) of section 529A(b)" is (b)(2); a list ("Paragraphs (3) and (4) of ...") is left to the
        # instructions below it.
        des = m.group("des") if m.group("des") and not m.group("more") else ""
        return 26, _sec(m.group("sec")), m.group("path") + des
    m = _IRC_CHAPTER.match(words)
    if m and not other.match(m.group("rest")) and (in_scope or named.match(m.group("rest"))):
        return 26, f"ch{m.group('ch')}", ""
    return None


_BILL_PATH = {"HR": "house-bill", "S": "senate-bill", "HJRES": "house-joint-resolution", "SJRES": "senate-joint-resolution"}


@dataclass
class Op:
    kind: str                  # replace, replace_all, replace_to_end, replace_range, insert_after, insert_before, delete,
                               # delete_all, append_block, replace_block, insert_block_after, insert_block_before,
                               # delete_provision, redesignate
    args: dict


@dataclass
class Instruction:
    identifier: str            # "/us/pl/117/151/s2/a/1"
    label: str                 # "§2(a)(1)"
    title: int
    section: str               # "101"
    path: str                  # "(51D)(B)(i)"
    text: str                  # the instruction as enacted, from the ref down to this provision
    ops: list[Op] = field(default_factory=list)
    unparsed: bool = False     # true when no operation could be read from the wording
    effective: Optional[str] = None     # when the law itself delays the change: "2024-06-21"
    timing: str = ""                    # the words that set that date
    order: int = 0                      # position in the law, for replaying in enacted order
    context: str = ""                   # the wording of the provisions this instruction sits in, up to its section
    heading: bool = False               # "in the section heading": the instruction changes the heading, not the text


@dataclass
class Law:
    congress: int
    number: int
    title: str
    short_title: str
    approved: str
    bill: Optional[dict]
    history: list[str]
    affected_sections: dict[int, list[str]]     # title -> sections listed in GovInfo's metadata
    url: str
    page: str
    sha256: str
    fetched_at: str
    instructions: list[Instruction] = field(default_factory=list)
    effective_notes: list[str] = field(default_factory=list)
    kind: str = "law"               # "law", or "notice" for a Federal Register notice that adjusts dollar amounts
    key: Optional[str] = None       # a notice's id, "87-FR-6625"

    @property
    def pl(self) -> str:
        return self.key or f"{self.congress}-{self.number}"


def _text(el, keep_quotes: bool = True) -> str:
    """Visible text of an element, with quoted words wrapped in curly quotes (as printed)."""
    parts: list[str] = []

    def walk(node) -> None:
        tag = node.tag if isinstance(node.tag, str) else ""
        if tag in _SKIP:
            return  # page numbers and margin notes are not part of the text
        if tag == _Q + "quotedText" and keep_quotes:
            parts.append("“" + "".join(node.itertext()) + "”")
        else:
            if node.text:
                parts.append(node.text)
            for child in node:
                walk(child)
                if child.tail:
                    parts.append(child.tail)

    walk(el)
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    # Some laws also print the quotation marks as plain characters next to <quotedText>; keep one pair.
    return re.sub(r"[\"“]“", "“", re.sub(r"”[\"”]", "”", text))


def _plain(el) -> str:
    """An element's words with quoted text and quoted content left out: the instruction's own wording only."""
    parts: list[str] = []

    def walk(node) -> None:
        if node.tag in _SKIP:
            return
        if node.tag in (_Q + "quotedText", _Q + "quotedContent"):
            parts.append(" … ")
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _has_child_instructions(el) -> bool:
    for child in el:
        if child.tag in _LEVEL_TAGS and any(True for _ in child.iter(_Q + "amendingAction")):
            return True
    return False


def _own_parts(el):
    """The element's own words (num, heading, chapeau, content, continuation), not its nested levels."""
    for child in el:
        if child.tag in (_Q + "chapeau", _Q + "content", _Q + "continuation", _Q + "heading", _Q + "num"):
            yield child


def _href_target(href: str) -> Optional[tuple[int, str, str]]:
    """"/us/usc/t11/s101/51D/B" -> (11, "101", "(51D)(B)"); a chapter target is "ch11" with no path."""
    c = re.match(r"/us/usc/t(\d+)/ch([0-9]+[A-Z]?)(?:/sch([IVX]+))?$", href)
    if c:
        return int(c.group(1)), f"ch{c.group(2)}", ""
    t = re.match(r"/us/usc/t(\d+)$", href)
    if t:
        return int(t.group(1)), "", ""   # the whole title: the section is named in the words below
    m = re.match(r"/us/usc/t(\d+)/s([0-9]+[A-Za-z]*(?:-[0-9]+[A-Za-z]*)?)((?:/[^/]+)*)", href)
    if not m:
        return None
    path = "".join(f"({p})" for p in m.group(3).split("/") if p)
    return int(m.group(1)), m.group(2), path


def _refs_outside_quotes(el) -> list:
    out = []
    for ref in el.iter(_Q + "ref"):
        anc = ref.getparent()
        quoted = False
        while anc is not None and anc is not el:
            if anc.tag in (_Q + "quotedText", _Q + "quotedContent", _Q + "sidenote", _Q + "note"):
                quoted = True
                break
            anc = anc.getparent()
        if not quoted:
            out.append(ref)
    return out


def _relative_path(words: str) -> list[tuple[str, str]]:
    """"in subparagraph (B), in clause (i)" -> [("subparagraph","(B)"), ("clause","(i)")]; also the matter before or after."""
    found = []
    words = re.sub(r"\s*\(relating to [^()]*(?:\([^()]*\)[^()]*)*\)", "", words)
    pattern = (
        r"\bin section (?P<sec>" + _SEC + r")(?P<secpath>(?:\([^)]+\))*)"
        r"|\bin (?P<inner>" + _UNIT + r") \((?P<di>[^)]+)\) of (?P<outer>" + _UNIT + r") \((?P<do>[^)]+)\)"
        r"|\bin the heading of (?P<hunit>" + _UNIT + r") \((?P<hd>[^)]+)\)(?P<hmore>(?:\([^)]+\))*)"
        r"|\bat the end of (?P<eunit>" + _UNIT + r") \((?P<ed>[^)]+)\)(?P<emore>(?:\([^)]+\))*)"
        r"|\bin (?:the matter (?P<side>preceding|following) )?(?:the (?P<nth>first|second|third) )?(?P<unit>" + _UNIT + r") \((?P<d>[^)]+)\)(?P<more>(?:\([^)]+\))*)"
    )
    for m in re.finditer(pattern, words):
        if m.group("inner"):
            found.append(("path", f"({m.group('do')})({m.group('di')})"))
            continue
        if m.group("eunit"):
            found.append((m.group("eunit").rstrip("s"), f"({m.group('ed')}){m.group('emore') or ''}"))
            continue
        if m.group("hunit"):
            # "in the heading of subsection (b)": the subsection's own line, which carries its heading.
            found.append(("path", f"({m.group('hd')}){m.group('hmore') or ''}"))
            continue
        if m.group("nth"):
            found.append(("nth", {"first": "1", "second": "2", "third": "3"}[m.group("nth")]))
        if m.group("sec"):
            found.append(("in-section", _sec(m.group("sec"))))
            for d in re.findall(r"\([^)]+\)", m.group("secpath") or ""):
                found.append(("path", d))
            continue
        unit = m.group("unit").rstrip("s")
        found.append((m.group("side") or unit, f"({m.group('d')}){m.group('more') or ''}"))
    return found


def content_sections(block) -> dict[str, list[tuple[int, str]]]:
    """New sections inside a quotedContent block (a subchapter added whole), keyed by section number.

    The Code prints a section without its number and heading, so a section's lines start with its opening words."""
    out: dict[str, list[tuple[int, str]]] = {}
    for sec in block.iter(_Q + "section"):
        num = sec.find(_Q + "num")
        # Kept as the Code numbers it: "121A", "1400Z-2" (case and hyphen matter; an en dash becomes a hyphen).
        raw = num.get("value") if num is not None and num.get("value") else "".join(num.itertext()) if num is not None else ""
        number = re.sub(r"[^0-9A-Za-z-]", "", raw.replace("–", "-")).strip("-")
        if number:
            out[number] = _content_lines([sec], skip_heading_of=sec, base_level=-1)
    return out


def _quoted_line(text: str) -> str:
    """A line of quoted matter as the Code prints it: no opening or closing quotation marks from the bill, and
    quotations within it in double quotes."""
    t = text.strip()
    t = re.sub(r"^[“\"]\s*", "", t)
    t = re.sub(r"[”\"]\s*[.;,]?\s*$", "", t) if t.endswith(("”.", "”;", "”,", "”")) and t.count("“") < t.count("”") else t
    t = re.sub(r"(^|[\s(\[—-])‘([^‘’]+)’", lambda m: f"{m.group(1)}“{m.group(2)}”", t)
    return t


def _content_lines(block, base_level: int = 0, skip_heading_of=None) -> list[tuple[int, str]]:
    """A quotedContent block as (relative level, line) pairs, the way the Code prints each provision: a provision's
    own words on one line, its sub-provisions below it, and any closing words after them on a line of their own."""
    lines: list[tuple[int, str]] = []

    def walk(node, level: int) -> None:
        own_parts = [p for p in _own_parts(node) if p.tag != _Q + "continuation"]
        if node is skip_heading_of:
            own_parts = [p for p in own_parts if p.tag not in (_Q + "num", _Q + "heading")]
        own = " ".join(_text(p) for p in own_parts)
        if own:
            lines.append((max(level, 0), _quoted_line(own)))
        for child in node:
            if child.tag in _LEVEL_TAGS:
                walk(child, level + 1)
        for cont in node.findall(_Q + "continuation"):
            lines.append((max(level, 0), _quoted_line(_text(cont)) + "\u0000closing"))

    if not isinstance(block, list) and (block.text or "").strip():
        lines.append((max(base_level, 0), _quoted_line(block.text)))   # words before the first provision
    for child in block:
        if child.tag in _LEVEL_TAGS:
            walk(child, base_level)
        elif isinstance(child.tag, str) and child.tag in (_Q + "p", _Q + "content", _Q + "text", _Q + "inline"):
            lines.append((max(base_level, 0), _quoted_line(_text(child))))
    return [(lvl, t) for lvl, t in lines if t.strip()]


_ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"]


def _designation_list(words: str) -> list[str]:
    """"subsections (i) through (k)" -> ["i", "j", "k"]; "(3), (4), and (5)" -> ["3", "4", "5"]. A compound item such as
    "(6)(E)" is kept whole as "6)(E", so wrapping it in parentheses gives the path "(6)(E)"."""
    out: list[str] = []
    parts = re.findall(r"((?:\([^)]+\))+)|(through)", words)
    items = [p[0][1:-1] if p[0] else p[1] for p in parts]
    n = 0
    while n < len(items):
        if n + 2 < len(items) and items[n + 1] == "through":
            a, b = items[n], items[n + 2]
            if a.isdigit() and b.isdigit():
                out += [str(x) for x in range(int(a), int(b) + 1)]
            elif a in _ROMANS and b in _ROMANS and _ROMANS.index(a) < _ROMANS.index(b) and not (len(a) == 1 and len(b) == 1 and a not in "iv"):
                out += _ROMANS[_ROMANS.index(a): _ROMANS.index(b) + 1]
            elif len(a) == 1 and len(b) == 1 and a.isalpha() and b.isalpha():
                out += [chr(c) for c in range(ord(a), ord(b) + 1)]
            else:
                out += [a, b]
            n += 3
            continue
        if items[n] != "through":
            out.append(items[n])
        n += 1
    return out


def _quoted_words(node) -> str:
    """The words of a quotedText element, without page numbers or margin notes printed inside it."""
    parts: list[str] = [node.text or ""]
    for child in node:
        if child.tag not in _SKIP:
            parts.append(_quoted_words(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _ops(el) -> tuple[list[Op], bool]:
    """Operations in one instruction's own words. Quoted words become placeholders so the grammar stays simple."""
    quotes: list[str] = []
    blocks: list = []
    tokens: list[str] = []

    def walk(node) -> None:
        tag = node.tag if isinstance(node.tag, str) else ""
        if tag in _SKIP:
            return
        if tag == _Q + "quotedText":
            quotes.append(_quoted_words(node))
            tokens.append(f" Q{len(quotes) - 1} ")
            return
        if tag == _Q + "quotedContent":
            blocks.append(node)
            tokens.append(f" C{len(blocks) - 1} ")
            return
        if node.text:
            tokens.append(node.text)
        for child in node:
            if child.tag in _LEVEL_TAGS:
                continue
            walk(child)
            if child.tail:
                tokens.append(child.tail)

    for part in _own_parts(el):
        if part.tag in (_Q + "num", _Q + "heading"):
            continue
        walk(part)
    joined = "".join(tokens)
    # Some conversions leave quotation marks as plain characters instead of quotedText; treat those as quotes too.
    def literal(m: re.Match) -> str:
        quotes.append(m.group(1))
        return f" Q{len(quotes) - 1} "
    joined = re.sub(r"“(?!\s*[QC]\d+\s*”)([^“”]*)”", literal, joined)
    s = re.sub(r"\s+", " ", joined.replace("“", "").replace("”", "")).strip()
    s = re.sub(r"\b(?:\d+ STAT\. \d+)\s*", "", s)   # page markers inside the text
    s = re.sub(r"\s*\(relating to [^()]*\)", "", s)    # "(relating to Q3)" only names the provision
    q = lambda i: quotes[int(i)]  # noqa: E731
    ops: list[Op] = []
    ends = {"period": ".", "semicolon": ";", "comma": ",", "colon": ":"}
    end_word = r"(?P<{0}>period|semicolon|comma|colon)"
    special = re.compile(
        r"striking the " + end_word.format("e1") + r" at the end(?: of [^,;]+?)? and insert(?:ing)? (?:(?:the following:? )?Q(?P<q1>\d+)|a (?P<w1>period|semicolon|comma|colon))"
        r"|striking Q(?P<q2>\d+) at the end(?: of [^,;]+?)? and insert(?:ing)? (?:Q(?P<r2>\d+)|a (?P<w2>period|semicolon|comma|colon))"
        r"|striking Q(?P<q3>\d+) and insert(?:ing)? a (?P<w3>period|semicolon|comma|colon)"
        r"|adding Q(?P<q4>\d+) at the end"
        r"|adding an? (?P<w22>period|comma|semicolon|colon) at the end"
        r"|adding at (?:the )?end (?:thereof )?the following(?: new (?:sentence|sentences|matter|text|flush text))?:? Q(?P<q9>\d+)"
        r"|striking the " + end_word.format("e10") + r" after Q(?P<q10>\d+)"
        r"|inserting Q(?P<q5>\d+) before the " + end_word.format("e5") + r"(?: at the end)?"
        r"|striking the " + end_word.format("e6") + r" at the end(?![^;]*inserting)"
        r"|striking Q(?P<q8>\d+) at the end(?: of [^,;]+?)?(?![^;]*inserting)"
        r"|amended to read as (?:such|that) (?P<unit7>" + _UNIT + r"|provision) read on the day before the date of enactment"
        r"|\b(?:is|are) (?:hereby )?(?P<rep11>repealed)\b"
        r"|\b(?P<ord16>first|second|third|fourth|fifth|sixth|last) sentence of .*?\b(?:is|are) amended to read as follows:? Q(?P<q16>\d+)"
        r"|striking the (?P<ord17>first|second|third|fourth|fifth|sixth|last) sentence(?: and insert(?:ing)?(?: the following:?)? (?P<k17>[QC])(?P<q17>\d+))?"
        r"|striking Q(?P<a19>\d+) after Q(?P<b19>\d+)(?: and insert(?:ing)? (?:Q(?P<c19>\d+)|a (?P<w19>period|semicolon|comma|colon)))?"
        r"|inserting before the " + end_word.format("e20") + r"(?: at the end)? the following:? Q(?P<q20>\d+)"
        r"|inserting the following (?P<pos18>after|before) Q(?P<a18>\d+)\s*:?\s*(?P<kind18>[QC])(?P<b18>\d+)(?P<more18>(?:\s*Q\d+)*)"
    )
    found: list[tuple[int, Op]] = []
    taken: list[tuple[int, int]] = []
    for m in special.finditer(s):
        g = m.groupdict()
        ops = []
        taken.append(m.span())
        if g["e1"]:
            ops.append(Op("replace_end", {"old": ends[g["e1"]], "new": q(g["q1"]) if g["q1"] else ends[g["w1"]]}))
        elif g["q2"] is not None:
            ops.append(Op("replace_end", {"old": q(g["q2"]), "new": q(g["r2"]) if g["r2"] else ends[g["w2"]]}))
        elif g["q3"] is not None:
            ops.append(Op("replace", {"old": q(g["q3"]), "new": ends[g["w3"]]}))
        elif g["w22"]:
            ops.append(Op("append_text", {"new": ends[g["w22"]]}))
        elif g["q4"] is not None:
            ops.append(Op("append_text", {"new": q(g["q4"])}))
        elif g["q9"] is not None:
            ops.append(Op("append_text", {"new": q(g["q9"])}))
        elif g["q10"] is not None:
            ops.append(Op("replace", {"old": q(g["q10"]) + ends[g["e10"]], "new": q(g["q10"])}))
        elif g["q5"] is not None:
            ops.append(Op("insert_before_end", {"new": q(g["q5"]), "end": ends[g["e5"]]}))
        elif g["e6"]:
            ops.append(Op("replace_end", {"old": ends[g["e6"]], "new": ""}))
        elif g["q8"] is not None:
            ops.append(Op("replace_end", {"old": q(g["q8"]), "new": ""}))
        elif g["unit7"]:
            ops.append(Op("revert", {"to": "day before enactment"}))
        elif g["rep11"]:
            ops.append(Op("repeal", {}))
        elif g["ord16"]:
            ops.append(Op("replace_sentence", {"which": g["ord16"], "new": q(g["q16"])}))
        elif g["ord17"]:
            new = ""
            if g["q17"]:
                new = q(g["q17"]) if g["k17"] == "Q" else " ".join(t for _, t in _content_lines(blocks[int(g["q17"])]))
            args = {"which": g["ord17"], "new": new}
            if g["q17"] and g["k17"] == "C":
                args["lines"] = _content_lines(blocks[int(g["q17"])])
            ops.append(Op("replace_sentence", args))
        elif g["a19"] is not None:
            # "striking 'or' after 'possession of the United States' and insert(?:ing)? a comma": only where it follows.
            anchor, old = q(g["b19"]), q(g["a19"])
            # Punctuation attaches to the word before it, and a designation to the one before it: "(3)(A)".
            join = lambda words: ("" if words.lstrip()[:1] in ",.;:" or (anchor.endswith(")") and words.lstrip().startswith("(")) else " ") + words.lstrip()  # noqa: E731
            if g["c19"] is not None:
                new = anchor + join(q(g["c19"]))
            elif g["w19"]:
                new = anchor + ends[g["w19"]]
            else:
                new = anchor
            ops.append(Op("replace", {"old": anchor + join(old), "new": new}))
        elif g["q20"] is not None:
            ops.append(Op("insert_before_end", {"new": q(g["q20"]), "end": ends[g["e20"]]}))
        elif g["pos18"]:
            # New words given as a block ("except that—(i) ...") run together; the replay splits the list onto lines.
            new = q(g["b18"]) if g["kind18"] == "Q" else " ".join(t for _, t in _content_lines(blocks[int(g["b18"])]))
            # Further quoted pieces are inserted with the quotation marks the law prints between them; the Code
            # reproduces them as enacted ("...2027; and" " (ii) with respect to ...").
            for i in re.findall(r"Q(\d+)", g["more18"] or ""):
                new += "” “ " + q(i)
            ops.append(Op("insert_after" if g["pos18"] == "after" else "insert_before", {"new": new, "anchor": q(g["a18"]), "all": False}))
        found.extend((m.start(), op) for op in ops)
    pattern = re.compile(
        r"striking Q(?P<a1>\d+) and all that follows through Q(?P<b1>\d+) and insert(?:ing)? Q(?P<c1>\d+)"
        r"|striking Q(?P<a2>\d+) and all that follows and insert(?:ing)? Q(?P<c2>\d+)"
        r"|striking Q(?P<a3>\d+)(?P<each3> each (?:subsequent )?place (?:it|such term|that term|the term) appears(?: in the text(?: and in the heading)?| in the heading)?| in (?:each|both) places? (?:it|such term) appears)? (?:in the heading(?: thereof)? )?and insert(?:ing)?(?: the following:?)? Q(?P<b3>\d+)(?P<after3> each (?:subsequent )?place (?:it|such term|that term|the term) appears| in (?:each|both) places? (?:it|such term) appears)?"
        r"|inserting Q(?P<a4>\d+) after Q(?P<b4>\d+)(?P<each4> each place (?:it|such term) appears)?"
        r"|inserting Q(?P<a5>\d+) before Q(?P<b5>\d+)"
        r"|striking Q(?P<a6>\d+) and all that follows(?: through the (?:period|semicolon) at the end)?(?!\s*and inserting)"
        r"|striking Q(?P<a7>\d+)(?P<each7> each place (?:it|such term) appears)?(?! and)"
        r"|adding at (?:the )?end (?:thereof )?the following(?: new [a-z]+)?:? C(?P<c8>\d+)"
        r"|(?:adding|inserting) (?:after|before) chapter \d+[A-Z]? the following(?: new chapters?)?:? C(?P<c24>\d+)"
        r"|(?:is )?amended to read as follows:? C(?P<c9>\d+)"
        r"|inserting (?P<pos10>after|before) (?P<unit10>" + _UNIT + r") \((?P<d10>[^)]+)\)(?:,? as (?:so )?redesignated(?: by [^,]+?)?| \(as (?:so )?redesignated[^)]*\))?,? the following(?: new [a-z]+(?: \([^)]+\))?)?:? C(?P<c10>\d+)"
        r"|amending (?P<unit14>" + _UNIT + r") (?P<d14>(?:\([^)]+\))+) to read as follows:? C(?P<c14>\d+)"
        r"|striking Q(?P<a13>\d+) and insert(?:ing)? (?:the following:? )?C(?P<c13>\d+)"
        r"|striking (?P<unit11>" + _UNIT + r") (?P<d11>(?:\([^)]+\))+(?:(?:,\s*|\s+and\s+|,\s*and\s+|\s+through\s+)(?:\([^)]+\))+)*)(?: and insert(?:ing)? the following:? C(?P<c11>\d+))?"
        r"|striking sections? (?P<s21>" + _SEC + r"(?:(?:,\s*|\s+and\s+|,\s*and\s+|\s+through\s+)" + _SEC + r")*)(?![\w–-])(?! of)(?: and insert(?:ing)? the following:? C(?P<c21>\d+))?"
        r"|inserting (?:after|before) section " + _SEC + r" the following(?: new sections?)?:? C(?P<c22>\d+)"
        r"|inserting (?P<pos23>after|before) Q(?P<a23>\d+),? the following:? Q(?P<b23>\d+)"
        r"|redesignating (?P<from12>.+?) as (?P<to12>.+?)(?:, respectively|;|$)"
    )
    for m in pattern.finditer(s):
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue  # already read as one of the special forms above
        g = m.groupdict()
        ops = []
        if g["a1"] is not None:
            ops.append(Op("replace_range", {"start": q(g["a1"]), "through": q(g["b1"]), "new": q(g["c1"])}))
        elif g["a2"] is not None:
            ops.append(Op("replace_to_end", {"start": q(g["a2"]), "new": q(g["c2"])}))
        elif g["a3"] is not None:
            ops.append(Op("replace_all" if g["each3"] or g["after3"] else "replace", {"old": q(g["a3"]), "new": q(g["b3"])}))
        elif g["a4"] is not None:
            ops.append(Op("insert_after", {"new": q(g["a4"]), "anchor": q(g["b4"]), "all": bool(g["each4"])}))
        elif g["a5"] is not None:
            ops.append(Op("insert_before", {"new": q(g["a5"]), "anchor": q(g["b5"])}))
        elif g["a6"] is not None:
            ops.append(Op("replace_to_end", {"start": q(g["a6"]), "new": ""}))
        elif g["a7"] is not None:
            ops.append(Op("delete_all" if g["each7"] else "delete", {"old": q(g["a7"])}))
        elif g["c8"] is not None or g["c24"] is not None:
            # A block added at the end, or a whole chapter added after another ("adding after chapter 36").
            block = blocks[int(g["c8"] if g["c8"] is not None else g["c24"])]
            sections = content_sections(block)
            if block.find(_Q + "toc") is not None and not sections:
                ops.append(Op("table_of_contents", {}))
            else:
                chapter = block.find(_Q + "chapter")
                number = chapter.find(_Q + "num") if chapter is not None else None
                ops.append(Op("append_block", {
                    "lines": _content_lines(block), "sections": sections,
                    "chapter": (number.get("value") or "").strip() if number is not None else "",
                }))
        elif g["c9"] is not None:
            # A whole section rewritten: the Code prints its number and heading apart from its text.
            block = blocks[int(g["c9"])]
            sec = block.find(_Q + "section")
            lines = _content_lines([sec], skip_heading_of=sec, base_level=-1) if sec is not None else _content_lines(block)
            heading = sec.find(_Q + "heading") if sec is not None else None
            words = re.sub(r"\s+", " ", _quoted_words(heading)).strip().strip("“”\"") if heading is not None else ""
            ops.append(Op("replace_block", {"lines": lines, **({"heading": words} if words else {})}))
        elif g["c14"] is not None:
            ops.append(Op("replace_provision", {"target": g["d14"], "lines": _content_lines(blocks[int(g["c14"])])}))
        elif g["c10"] is not None:
            kind = "insert_block_after" if g["pos10"] == "after" else "insert_block_before"
            ops.append(Op(kind, {"sibling": f"({g['d10']})", "lines": _content_lines(blocks[int(g["c10"])])}))
        elif g["a13"] is not None:
            # The new words are a block ("does not include— (i) any member"): replace with its lines run together;
            # the replay splits the new list onto lines of its own.
            text = " ".join(t for _, t in _content_lines(blocks[int(g["c13"])]))
            ops.append(Op("replace", {"old": q(g["a13"]), "new": text}))
        elif g["unit11"] is not None:
            targets = [f"({d})" for d in _designation_list(g["d11"])]
            if g["c11"] is not None:
                ops.append(Op("replace_provision", {"target": targets[0], "lines": _content_lines(blocks[int(g["c11"])])}))
                ops.extend(Op("delete_provision", {"target": t}) for t in targets[1:])
            else:
                ops.extend(Op("delete_provision", {"target": t}) for t in targets)
        elif g["pos23"] is not None:
            # "by inserting after 'subsection (c)' the following: '(as in effect ...)'"
            ops.append(Op("insert_after" if g["pos23"] == "after" else "insert_before", {"new": q(g["b23"]), "anchor": q(g["a23"]), "all": False}))
        elif g["c22"] is not None:
            # "inserting after section 21 the following new section": a section added whole.
            ops.append(Op("replace_sections", {"remove": [], "sections": content_sections(blocks[int(g["c22"])])}))
        elif g["s21"] is not None:
            # Whole sections struck from a title, and the sections that take their place.
            nums = [_sec(x) for x in re.findall(_SEC, g["s21"])]
            if " through " in g["s21"] and len(nums) == 2 and nums[0].isdigit() and nums[1].isdigit():
                nums = [str(n) for n in range(int(nums[0]), int(nums[1]) + 1)]
            added = content_sections(blocks[int(g["c21"])]) if g["c21"] is not None else {}
            ops.append(Op("replace_sections", {"remove": nums, "sections": added}))
        elif g["from12"] is not None:
            froms = _designation_list(g["from12"])
            tos = _designation_list(g["to12"])
            which = re.match(r"\s*the (first|second|third) ", g["from12"])
            if froms and len(froms) == len(tos):
                args = {"pairs": [(f"({a})", f"({b})") for a, b in zip(froms, tos)]}
                if which:
                    args["nth"] = {"first": 1, "second": 2, "third": 3}[which.group(1)]
                ops.append(Op("redesignate", args))
        found.extend((m.start(), op) for op in ops)
    ordered = [op for _, op in sorted(found, key=lambda x: x[0])]
    return ordered, not ordered


def _label(identifier: str) -> str:
    """"/us/pl/116/136/dA/tI/s1113/a/4/A" -> "div. A, title I, §1113(a)(4)(A)"."""
    parts = identifier.split("/")[5:]
    out, sec = [], ""
    for p in parts:
        if p.startswith("d") and p[1:].isalpha() and p[1:].isupper():
            out.append(f"div. {p[1:]}")
        elif p.startswith("t") and re.fullmatch(r"t[IVXLC]+", p):
            out.append(f"title {p[1:]}")
        elif p.startswith("st") and p[2:].isupper():
            out.append(f"subtitle {p[2:]}")
        elif p.startswith("s") and p[1:2].isdigit():
            sec = f"§{p[1:]}"
        elif sec:
            sec += f"({p})"
    return ", ".join(out + ([sec] if sec else []))


def parse_law(xml: bytes, mods: Optional[bytes], *, congress: int, number: int, url: str, sha256: str, fetched_at: str, title: int) -> Law:
    root = etree.fromstring(xml)
    meta = root.find(_Q + "meta")
    dc = "{http://purl.org/dc/elements/1.1/}"
    law_title = (meta.findtext(dc + "title") if meta is not None else "") or ""
    approved = (meta.findtext(_Q + "approvedDate") if meta is not None else "") or ""
    cover = root.find(f".//{_Q}coverTitle")
    short = " ".join(cover.itertext()).strip().title() if cover is not None else ""
    bill, history, affected = None, [], {}
    if mods:
        mroot = etree.fromstring(mods)
        m = "{http://www.loc.gov/mods/v3}"
        b = mroot.find(f".//{m}bill[@priority='primary']")
        if b is not None:
            kind = (b.get("type") or "").upper()
            bill = {
                "type": kind,
                "number": b.get("number"),
                "congress": b.get("congress"),
                "label": {"HR": "H.R.", "S": "S.", "HJRES": "H.J.Res.", "SJRES": "S.J.Res."}.get(kind, kind) + " " + (b.get("number") or ""),
                "url": f"https://www.congress.gov/bill/{b.get('congress')}th-congress/{_BILL_PATH.get(kind, kind.lower())}/{b.get('number')}" if kind in _BILL_PATH else None,
            }
        st = mroot.find(f".//{m}shortTitle")
        if st is not None and st.text:
            # GovInfo lists alternatives in one title: 'X Act" or the "Y Act'. The first is the law's name.
            short = re.split(r'["”]\s+or\s+(?:as\s+)?the\s+["“]', st.text.strip())[0].strip(' "“”')
        lh = mroot.find(f".//{m}legislativeHistory")
        if lh is not None and lh.text:
            raw = re.sub(r"&lt;br/&gt;|<br/>|&amp;lt;br/&amp;gt;", "\n", lh.text)
            history = [re.sub(r"\s+", " ", x).strip() for x in raw.split("\n") if x.strip()]
        for usc in mroot.iter(f"{m}USCode"):
            t = int(usc.get("title") or 0)
            affected.setdefault(t, [])
            for s in usc.iter(f"{m}section"):
                label = (s.get("number") or "") + (s.get("detail") or "")
                if label and label not in affected[t]:
                    affected[t].append(label)
    law = Law(congress, number, law_title, short, approved, bill, history, affected, url, law_page(congress, number), sha256, fetched_at)

    leaves: dict[int, object] = {}
    for action in root.iter(_Q + "amendingAction"):
        el = action.getparent()
        while el is not None and el.tag not in _LEVEL_TAGS:
            el = el.getparent()
        if el is not None:
            leaves[id(el)] = el
    last_section, last_part, last_path = "", "", ""

    def part_of(node) -> str:
        """The section of the law an amending provision sits in: "/us/pl/119/60/dA/tXVII/s1702"."""
        m = re.match(r"^(.*?/s[0-9A-Za-z]+)(?:/|$)", ident(node))
        return m.group(1) if m else ""

    def ident(node) -> str:
        """The provision's identifier; some laws leave it out, so one is built from the numbers of the provisions it
        sits in, up to the nearest ancestor that has one: "/us/pl/116/260/dFF/tII/s116" + "/e/2"."""
        if node.get("identifier"):
            return node.get("identifier")
        prefix = {"section": "s", "title": "t", "division": "d", "subtitle": "st", "part": "p", "subpart": "sp", "chapter": "ch", "subchapter": "sch"}
        parts, up = [], node
        while up is not None and up.tag in _LEVEL_TAGS and not up.get("identifier"):
            n = _num(up)
            parts.insert(0, prefix.get(up.tag.replace(_Q, ""), "") + n if n else "")
            up = up.getparent()
        base = up.get("identifier") if up is not None and up.get("identifier") else f"/us/pl/{congress}/{number}"
        return base + "".join(f"/{p}" for p in parts if p)

    # "Except as otherwise expressly provided, whenever in this title an amendment or repeal is expressed in terms of an
    # amendment to, or repeal of, a section or other provision, the reference shall be considered to be made to a
    # section or other provision of the Internal Revenue Code of 1986": the part of the law it names ("this title",
    # "this subtitle", "this Act") amends that Code by section number alone.
    irc_scopes: set[int] = set()
    irc_nodes: list = [root]   # held so lxml keeps the same proxy objects, and so the same ids, for these elements
    if title == 26:
        for node in root.iter(*_LEVEL_TAGS):
            words = " ".join(_plain(p) for p in _own_parts(node) if p.tag != _Q + "num")
            m = _IRC_RULE.search(words)
            if not m:
                continue
            unit = m.group("unit").lower()
            if unit == "act":
                irc_scopes.add(id(root))
                continue
            up = node
            while up is not None and up.tag != _Q + unit:
                up = up.getparent()
            irc_nodes.append(up if up is not None else root)
            irc_scopes.add(id(irc_nodes[-1]))

    def _in_irc_scope(node) -> bool:
        if not irc_scopes:
            return False
        while node is not None:
            if id(node) in irc_scopes:
                return True
            node = node.getparent()
        return False

    for el in leaves.values():
        # Walk up to the nearest provision that names a target in this title.
        chain = []
        node, target = el, None
        matter_scope = None
        while node is not None and node.tag in _LEVEL_TAGS:
            chain.append(node)
            # The most specific reference wins: a heading such as "Title 35, United States Code" labels the
            # provision, while "Section 11 of title 35" in its words names what is amended.
            hits = [h for part in _own_parts(node) for ref in _refs_outside_quotes(part)
                    if not re.search(r"\bnote\b", "".join(ref.itertext()) + (ref.tail or "")[:8])
                    and (h := _href_target(ref.get("href") or "")) and h[0] == title]
            own_words = " ".join(_plain(p) for p in _own_parts(node) if p.tag not in (_Q + "num", _Q + "heading"))
            if hits:
                target = next((h for h in hits if h[1]), hits[0])
                if not target[1]:
                    # Only the title is marked up: "Sections 16 of title 3, United States Code, is amended".
                    # "Section 3013 (matter after paragraph (6)) of title 39": the parenthesis names the part amended.
                    named = re.search(r"\b[Ss]ections? (" + _SEC + r")((?:\([^)]+\))*)(?:\s*\((?P<matter>(?:the )?matter (?:preceding|following|after|before) [^()]*\([^)]*\)[^()]*)\))? of title \d+", own_words)
                    if named:
                        target = (title, _sec(named.group(1)), named.group(2))
                        matter = re.match(r"(?:the )?matter (preceding|following|after|before) [a-z]+ (\([^)]+\))", named.group("matter") or "")
                        if matter:
                            matter_scope = ("following" if matter.group(1) in ("following", "after") else "preceding", matter.group(2))
                break
            # "Section 10 of such title": the title already named, within the same section of the law.
            such = re.search(r"\b[Ss]ections? (" + _SEC + r")((?:\([^)]+\))*) of such (?:title|Code)\b", own_words)
            if such and (title == 26 or such.group(0).endswith("title")) and last_part and part_of(el) == last_part:
                target = (title, _sec(such.group(1)), such.group(2))
                break
            # Some laws name the target only in words, with no markup: "Section 11 of title 35, United States Code".
            words_here = " ".join(_plain(p) for p in _own_parts(node) if p.tag not in (_Q + "num", _Q + "heading"))
            cited = re.search(r"\b[Ss]ection (" + _SEC + r")((?:\([^)]+\))*) of title (\d+), United States Code", words_here)
            if cited and int(cited.group(3)) == title:
                target = (title, _sec(cited.group(1)), cited.group(2))
                break
            # The Internal Revenue Code of 1986 is title 26, section for section. Laws amend it by name ("Section 45Q
            # of the Internal Revenue Code of 1986 is amended"), or, where a provision of the law says that amendments
            # in it are to be read as amendments to that Code, by number alone ("Section 1(f)(2)(A) is amended").
            if title == 26:
                irc = _irc_target(words_here, in_scope=_in_irc_scope(node))
                if irc:
                    target = irc
                    break
            # "Such section is further amended": the section the instruction before this one named. Only a bare "Such
            # section" (with no number of its own) and only within the same section of the law.
            own = " ".join(_plain(p) for p in _own_parts(node) if p.tag not in (_Q + "num", _Q + "heading"))
            same = last_section and last_part and part_of(el) == last_part
            if same and re.match(r"\s*(?:Such|That|The same) section\b(?!\s+\d)", own):
                target = (title, last_section, "")
                break
            # "Such subsection is further amended": the subsection the instruction before this one named.
            if same and last_path and re.match(r"\s*(?:Such|That|The same) subsection\b(?!\s+\()", own):
                target = (title, last_section, re.match(r"\([^)]+\)", last_path).group(0))
                break
            node = node.getparent()
        if not target:
            continue
        words = []
        for n in reversed(chain):
            words.append(" ".join(_text(p) for p in _own_parts(n) if p.tag not in (_Q + "num", _Q + "heading")))
        section, path = target[1], target[2]
        sides = [matter_scope] if matter_scope else []
        nth = 0
        # "in clause (i)" phrases between the provision that names the target and this one narrow the target. The
        # target's own wording counts only after the reference itself ("Section 101 ... is amended in paragraph (5)").
        scopes = [" ".join(_plain(p) for p in _own_parts(n) if p.tag not in (_Q + "heading", _Q + "num")) for n in reversed(chain[:-1])]
        top = " ".join(_plain(p) for p in _own_parts(chain[-1]) if p.tag not in (_Q + "heading", _Q + "num"))
        after_ref = re.split(r"\bis amended\b|\bare amended\b|\bis further amended\b", top, maxsplit=1)
        scopes.insert(0, after_ref[1] if len(after_ref) > 1 else "")
        named = re.match(r"\s*(?:" + _UNIT + r") (\([^)]+\)(?:\([^)]+\))*) of section " + re.escape(section) + r"\b", after_ref[0] if after_ref else "", re.I)
        if named and not path:
            path = named.group(1)
        for unit, designation in _relative_path(" ".join(scopes)):
            if unit == "in-section":
                section, path, sides = designation, "", []
            elif unit in ("preceding", "following"):
                sides.append((unit, designation))
            elif unit == "nth":
                nth = int(designation)
            else:
                path += designation
        ops, unparsed = _ops(el)
        said = " ".join(scopes)
        if re.search(r"\btable of (?:sections|chapters|contents|subchapters)\b", top + " " + said):
            ops, unparsed = [Op("table_of_contents", {})], False
        listed = []
        if not section and re.search(r"each place (?:it|such term) appears in the following sections", " ".join(scopes) + " " + top):
            for child in el:
                if child.tag in _LEVEL_TAGS:
                    listed += re.findall(r"\b[Ss]ection (" + _SEC + r")\b", " ".join(_plain(x) for x in _own_parts(child)))
        if listed and ops and all(op.kind in ("replace", "replace_all") for op in ops):
            each = [Op("replace_all", op.args) for op in ops]
            base = ident(el)
            for n in dict.fromkeys(listed):
                instr = Instruction(identifier=f"{base}#{n}", label=_label(base), title=title, section=n, path="",
                                    text=" ".join(w for w in words if w), ops=list(each))
                instr.effective, instr.timing = _timing(el, law.approved)
                instr.order = len(law.instructions)
                law.instructions.append(instr)
            continue
        if not section:
            # The whole title is amended: a chapter added at its end is matched to the new sections it brings.
            chapter = next((op.args.get("chapter") for op in ops if op.kind == "append_block" and op.args.get("sections")), "")
            if not chapter and any(op.kind == "replace_sections" for op in ops):
                chapter = "-sections"   # whole sections of the title struck or replaced
            if not chapter:
                continue
            section = f"ch{chapter}"
        if unparsed and _has_child_instructions(el):
            continue  # "Section 101 is amended—" introduces the instructions below it
        instr_text = " ".join(_plain(p) for p in _own_parts(el) if p.tag not in (_Q + "num", _Q + "heading"))
        instr = Instruction(
            identifier=ident(el),
            label=_label(ident(el)),
            title=title,
            section=section,
            path=path,
            text=" ".join(w for w in words if w),
            ops=ops,
            unparsed=unparsed,
            # "in the section heading" changes the section's heading; "in the heading of subsection (b)" changes the
            # subsection's own line, which is part of the text.
            heading=bool(re.search(r"\bin the (?:section )?heading\b(?! of )", said)) and not path and "in the text" not in instr_text,
        )
        if sides:
            instr.ops.insert(0, Op("scope", {"side": sides[-1][0], "of": sides[-1][1]}))
        if nth:
            instr.ops.insert(0, Op("nth", {"n": nth}))
        sentence = re.match(r"\s*The (first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last) sentence of\b", top)
        if sentence:
            instr.ops.insert(0, Op("sentence", {"which": sentence.group(1)}))   # "the second subsection (c)": the second of two with that letter
        instr.effective, instr.timing = _timing(el, law.approved)
        instr.order = len(law.instructions)
        up, ctx = el.getparent(), []
        while up is not None and up.tag in _LEVEL_TAGS:
            ctx.insert(0, " ".join(_plain(p) for p in _own_parts(up) if p.tag != _Q + "num"))
            if up.tag == _Q + "section":
                break
            up = up.getparent()
        instr.context = " ".join(c for c in ctx if c)[:800]
        each = _each_targets(top, section, title)
        if len(each) > 1:
            # "Subparagraphs (B) and (C) of section 1256(e)(3) are each amended", "Sections 22(c)(3), 104(b)(2), and
            # 140(a)(3) are each amended": the same change made in every provision named, one instruction each.
            first_sec, first_path = each[0]
            extra = path[len(first_path):] if path.startswith(first_path) else ""
            base = instr.identifier
            for n, (sec, p) in enumerate(each):
                copy = Instruction(identifier=base if n == 0 else f"{base}#{n}", label=instr.label, title=title, section=sec,
                                   path=p + extra, text=instr.text, ops=list(instr.ops), unparsed=instr.unparsed,
                                   effective=instr.effective, timing=instr.timing, order=len(law.instructions),
                                   context=instr.context, heading=instr.heading)
                law.instructions.append(copy)
        else:
            law.instructions.append(instr)
        last_section, last_part, last_path = section, part_of(el), path
    return law


_EACH_SECTIONS = re.compile(
    r"^\s*Sections (?P<list>" + _SEC + r"(?:\([^)]+\))*(?:(?:,\s*(?:and\s+)?|\s+and\s+)" + _SEC + r"(?:\([^)]+\))*(?:,\s*as amended [^,]*,)?)+)"
    r"(?:,?\s*of (?:the Internal Revenue Code of 1986|such Code|title (?P<t>\d+), United States Code))?,?\s*(?:as amended [^,]*,\s*)?are each amended")
_EACH_UNITS = re.compile(
    r"^\s*(?:Subsections|Paragraphs|Subparagraphs|Clauses|Subclauses|Items) (?P<list>(?:\([^)]+\))+(?:(?:,\s*(?:and\s+)?|\s+and\s+)(?:\([^)]+\))+)+)"
    r",? of section (?P<sec>" + _SEC + r")(?P<path>(?:\([^)]+\))*)(?![(\w])[^.;—]*?\bare each amended")


def _each_targets(words: str, section: str, title: int) -> list[tuple[str, str]]:
    """The provisions an "are each amended" instruction names, as (section, path), when the first is the one the
    instruction was resolved to; [] otherwise."""
    w = re.sub(r"\s*\((?:including|and) the heading[^()]*(?:\([^()]*\)[^()]*)*\)", "", words)
    m = _EACH_SECTIONS.match(w)
    if m and (not m.group("t") or int(m.group("t")) == title):
        items = [(_sec(s), p) for s, p in re.findall("(" + _SEC + r")((?:\([^)]+\))*)", re.sub(r",\s*as amended [^,]*,", ",", m.group("list")))]
        return items if items and items[0][0] == section else []
    m = _EACH_UNITS.match(w)
    if m and _sec(m.group("sec")) == section:
        return [(section, m.group("path") + d) for d in re.findall(r"(?:\([^)]+\))+", m.group("list"))]
    return []


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "180": 180, "90": 90}
_TIMING = re.compile(
    r"(?:effective|on the date that is|beginning on the date that is|as of the date that is)\s+(?:on the date that is\s+)?"
    r"(?P<n>\d+|one|two|three|four|five|six)\s+(?P<unit>year|month|day)s?\s+after\s+(?:(?:the\s+)?date of (?:the )?enactment|(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4}))",
    re.I,
)


def _add(date: str, n: int, unit: str) -> str:
    from datetime import date as _date, timedelta
    y, m, d = (int(x) for x in date.split("-"))
    if unit.startswith("year"):
        try:
            return _date(y + n, m, d).isoformat()
        except ValueError:
            return _date(y + n, m, 28).isoformat()
    if unit.startswith("month"):
        m2 = m + n
        y2, m2 = y + (m2 - 1) // 12, (m2 - 1) % 12 + 1
        return _date(y2, m2, min(d, 28)).isoformat()
    return (_date(y, m, d) + timedelta(days=n)).isoformat()


_SIBLING_TIMING = re.compile(
    r"amendments made by (?:this (?P<self>section|subsection|paragraph|subparagraph|clause)|(?P<unit>section|subsection|paragraph|subparagraph|clause)s? \((?P<d>[^)]+)\))"
    r"[^.]*?(?:shall )?(?:take effect|apply|be effective) (?:on|beginning on) the date that is\s+"
    r"(?P<n>\d+|one|two|three|four|five|six)\s+(?P<unit2>year|month|day)s?\s+after\s+(?:the\s+)?date of (?:the )?enactment",
    re.I,
)


def _num(node) -> str:
    n = node.find(_Q + "num")
    return (n.get("value") or "").strip() if n is not None else ""


def _timing(el, approved: str) -> tuple[Optional[str], str]:
    """A date the law sets for this instruction, from the instruction's own words or the provisions it sits in
    ("On the date that is 1 year after the date of enactment, section 1182(1) is amended"), or from a sibling that
    dates it ("(B) Effective date.—The amendments made by subparagraph (A) shall take effect on the date that is 1
    year after the date of enactment")."""
    node = el
    while node is not None and node.tag in _LEVEL_TAGS:
        words = " ".join(_plain(p) for p in _own_parts(node))
        m = _TIMING.search(words)
        if m and approved:
            n = int(m.group("n")) if m.group("n").isdigit() else _NUMBER_WORDS[m.group("n").lower()]
            return _add(approved, n, m.group("unit").lower()), m.group(0)
        parent = node.getparent()
        if parent is not None and approved:
            for sib in parent:
                if sib is node or sib.tag not in _LEVEL_TAGS:
                    continue
                s = _SIBLING_TIMING.search(_plain(sib))
                if s and (s.group("d") == _num(node) or (s.group("self") and False)):
                    n = int(s.group("n")) if s.group("n").isdigit() else _NUMBER_WORDS[s.group("n").lower()]
                    return _add(approved, n, s.group("unit2").lower()), s.group(0)
            own = " ".join(_plain(p) for p in _own_parts(parent))
            s = _SIBLING_TIMING.search(own)
            if s and s.group("self"):
                n = int(s.group("n")) if s.group("n").isdigit() else _NUMBER_WORDS[s.group("n").lower()]
                return _add(approved, n, s.group("unit2").lower()), s.group(0)
        if node.tag == _Q + "section":
            break
        node = parent
    return None, ""


def load_law(congress: int, number: int, *, title: int) -> Optional[Law]:
    got = fetch(law_url(congress, number))
    if got is None:
        return None
    mods = fetch(f"https://www.govinfo.gov/metadata/pkg/PLAW-{congress}publ{number}/mods.xml")
    return parse_law(got.data, mods.data if mods else None, congress=congress, number=number, url=got.url, sha256=got.sha256, fetched_at=got.fetched_at, title=title)
