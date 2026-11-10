"""Provision paths from designations, the way the US Code nests them.

The Code's hierarchy is fixed: subsection (a), paragraph (1), subparagraph (A), clause (i), subclause (I), item (aa),
subitem (AA). Printed indentation is not reliable enough to nest by, so a path is built from each designation's rank.
"(i)" and "(I)" are ambiguous (a letter or a roman numeral); context decides: under an open subparagraph "(i)" is a
clause, after subsection "(h)" it is the next subsection.
"""

from __future__ import annotations

import re
from typing import Optional

# The Code numbers clauses i, ii, ... xxx; "(c)" and "(l)" are always letters.
_ROMAN = re.compile(r"^(?=[ivx]+$)x{0,3}(ix|iv|v?i{0,3})$")
_ROMAN_UP = re.compile(r"^(?=[IVX]+$)X{0,3}(IX|IV|V?I{0,3})$")


def _letter_before(d: str) -> str:
    return chr(ord(d[0]) - 1) if len(d) == 1 and d[0] not in "aA" else ""


def rank(designation: str, stack: list[tuple[int, str]], expected: Optional[int] = None) -> int:
    """0 subsection, 1 paragraph, 2 subparagraph, 3 clause, 4 subclause, 5 item, 6 subitem.

    ``expected`` is the rank the printed indentation suggests, when known. It settles the letters that are also roman
    numerals: "(i)" is subsection (i) or clause (i), "(I)" is subparagraph (I) or subclause (I)."""
    d = designation.strip("()")
    if expected is not None:
        if d in ("i", "v", "x") and expected in (0, 3):
            return expected
        if d in ("I", "V", "X") and expected in (2, 4):
            return expected
        # "(aa)" is subsection (aa) after subsection (z), or item (aa) under a subclause.
        if re.fullmatch(r"([a-z])\1", d) and expected in (0, 5):
            return expected
    top = stack[-1][0] if stack else -1
    siblings = {r: x.strip("()") for r, x in stack}
    if re.fullmatch(r"\d+[A-Za-z]*(?:-\d+)?", d):
        return 1
    if re.fullmatch(r"([a-z])\1", d) and re.fullmatch(r"z|([a-z])\1", siblings.get(0, "")) and top <= 3:
        return 0   # the subsection after (z) is (aa), then (bb)
    if re.fullmatch(r"[a-z]{2,}", d) and not _ROMAN.fullmatch(d):
        return 5
    if re.fullmatch(r"[A-Z]{2,}", d) and not _ROMAN_UP.fullmatch(d):
        return 6
    if re.fullmatch(r"[a-z]+", d):
        if _ROMAN.fullmatch(d):
            # A roman numeral is a clause under an open subparagraph or next to another clause; otherwise a letter.
            if top >= 2 or (3 in siblings and _ROMAN.fullmatch(siblings[3])):
                if not (top == 0 and siblings.get(0) == _letter_before(d)):
                    return 3
            if len(d) > 1 and top >= 1:
                return 3
        return 0
    if re.fullmatch(r"[A-Z]+", d):
        if _ROMAN_UP.fullmatch(d) and (top >= 3 or (4 in siblings and _ROMAN_UP.fullmatch(siblings[4]))):
            if not (top == 2 and siblings.get(2) == _letter_before(d)):
                return 4
        if len(d) > 1 and _ROMAN_UP.fullmatch(d) and top >= 2:
            return 4
        return 2
    return top + 1 if top >= 0 else 0


def unambiguous_rank(designation: str) -> Optional[int]:
    """The rank of a designation that can only be one thing: "(3)" a paragraph, "(B)" a subparagraph, "(aaa)" an item.
    "(aa)" is not one of them: it is also the subsection after (z)."""
    d = designation.strip("()")
    if re.fullmatch(r"\d+[A-Za-z]*(?:-\d+)?", d):
        return 1
    if re.fullmatch(r"[a-z]", d) and d not in "ivxl":
        return 0
    if re.fullmatch(r"[A-Z]", d) and d not in "IVXL":
        return 2
    if re.fullmatch(r"[a-z]+", d) and _ROMAN.fullmatch(d) and len(d) > 1:
        return 3
    if re.fullmatch(r"[A-Z]+", d) and _ROMAN_UP.fullmatch(d) and len(d) > 1:
        return 4
    if re.fullmatch(r"([a-z])\1{2,}", d):
        return 5
    if re.fullmatch(r"([A-Z])\1+", d):
        return 6
    return None


def push(stack: list[tuple[int, str]], designation: str, expected: Optional[int] = None) -> list[tuple[int, str]]:
    """The stack after a provision with this designation: siblings and deeper provisions are closed first."""
    r = rank(designation, stack, expected)
    while stack and stack[-1][0] >= r:
        stack.pop()
    stack.append((r, designation))
    return stack


def path_of(stack: list[tuple[int, str]]) -> str:
    return "".join(d for _, d in stack)


def stack_for(path: str) -> list[tuple[int, str]]:
    """Rebuild a stack from an existing path, e.g. to nest inserted provisions under it."""
    stack: list[tuple[int, str]] = []
    for d in re.findall(r"\([^)]+\)", path):
        push(stack, d)
    return stack


def leading(text: str) -> tuple[list[str], str]:
    """"(3)(A)(i) The debtor ..." -> (["(3)", "(A)", "(i)"], "The debtor ...")."""
    found = []
    rest = text.lstrip()
    while True:
        m = re.match(r"^\(([0-9]+[A-Za-z]*(?:-[0-9]+)?|[a-z]{1,4}|[A-Z]{1,4})\)", rest)
        if not m:
            break
        found.append(m.group(0))
        rest = rest[m.end():]
    return found, rest.lstrip()
