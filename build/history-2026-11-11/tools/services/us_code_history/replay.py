"""Replays a law's amending instructions on the older text of a section and records which instruction changed what.

The state is the section as a list of lines (one per provision, as the Code prints them), each with a path and the
instruction that last changed it. Text operations work inside the target provision's subtree; block operations add or
replace whole provisions. The replay is judged against the newer edition after normalising typography (curly and
straight quotes, dash forms, spacing), which publishers render differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .editions import Provision, Section
from .laws import Instruction, Op

_DESIGNATION = re.compile(r"^\((?P<d>[^)]+)\)")


def norm(text: str) -> str:
    t = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = t.replace("—", "—").replace("--", "—").replace("–", "-").replace(" ", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:)\]])", r"\1", t)
    t = re.sub(r"([(\[])\s+", r"\1", t)
    t = re.sub(r"\)(?=[A-Za-z])", ") ", t)      # "(c)and" in a bill's markup is "(c) and" in the Code
    t = re.sub(r"\s*—\s*", "—", t)
    return t.strip()


@dataclass
class Line:
    path: str
    level: int
    text: str
    origin: Optional[str] = None      # identifier of the instruction that last changed this line


@dataclass
class OpResult:
    instruction: str
    op: str
    applied: bool
    detail: str = ""


@dataclass
class Replay:
    lines: list[Line]
    results: list[OpResult] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(norm(l.text) for l in self.lines)


def start(section: Optional[Section]) -> Replay:
    if section is None:
        return Replay([])
    return Replay([Line(p.path, p.level, p.text) for p in section.provisions])


def _blocks(state: "Replay", target: str) -> list[list[int]]:
    """The lines under each provision at ``target``, one list per provision. Two provisions that share a letter (Congress
    sometimes enacts two subsections (c)) each start at a line whose path is exactly the target."""
    blocks: list[list[int]] = []
    for j, line in enumerate(state.lines):
        if not _in_subtree(line.path, target):
            continue
        if line.path == target or not blocks:
            blocks.append([j])
        else:
            blocks[-1].append(j)
    return blocks


def _in_subtree(path: str, target: str) -> bool:
    if target == "":
        return True
    return path == target or path.startswith(target + "(") or path.startswith(target + " ")


def _indices(state: Replay, target: str) -> list[int]:
    return [i for i, l in enumerate(state.lines) if _in_subtree(l.path, target)]


def _rebuild_paths(lines: list[Line], base: str, base_level: int) -> None:
    """Give inserted lines paths from their designations, nested under base. Closing words after a list (marked by
    the law reader) belong to the provision that opened the list."""
    stack: list[tuple[int, str]] = []
    for n, line in enumerate(lines):
        closing = line.text.endswith("\u0000closing")
        if closing:
            line.text = line.text[: -len("\u0000closing")]
        m = _DESIGNATION.match(norm(line.text))
        rel = line.level
        while stack and (stack[-1][0] > rel if closing else stack[-1][0] >= rel):
            stack.pop()
        prefix = base + "".join(d for _, d in stack)
        if closing:
            line.path = prefix + " closing words"
        elif m:
            d = f"({m.group('d')})"
            line.path = prefix + d
            stack.append((rel, d))
        else:
            line.path = "" if (n == 0 and not prefix) else prefix + " text"
        line.level = base_level + rel


def canon(lines: list[Line]) -> list[tuple[str, str]]:
    """(key, normalised text) pairs where undesignated lines are keyed by their parent and their order among that
    parent's undesignated lines, so "(b) text 1" and "(b) closing words" compare as the same kind of line."""
    counts: dict[str, int] = {}
    out = []
    for line in lines:
        m = re.match(r"^(?P<parent>.*?)\s+(?:text|closing words)(?:\s+\d+)?$", line.path)
        if m:
            parent = m.group("parent")
            counts[parent] = counts.get(parent, 0) + 1
            key = f"{parent}~{counts[parent]}"
        else:
            key = line.path
        out.append((key, norm(line.text)))
    return out


_BARE = re.compile(r"^(?:\([^)]+\))+$")


def merge_bare(lines: list[Line]) -> list[Line]:
    """Join a provision that has no words of its own ("(B)") to its first child's line, as the Code prints it:
    "(B)(i) includes ...". The joined line takes the child's path."""
    out: list[Line] = []
    carry: Optional[Line] = None
    for line in lines:
        if _BARE.match(norm(line.text)):
            carry = Line(line.path, line.level, norm(line.text) if carry is None else norm(carry.text) + norm(line.text), line.origin)
            continue
        if carry is not None:
            line = Line(line.path, carry.level, norm(carry.text) + norm(line.text), line.origin or carry.origin)
            carry = None
        out.append(line)
    if carry is not None:
        out.append(carry)
    return out


def _block_lines(lines_spec: list, base: str, base_level: int, origin: str) -> list[Line]:
    out = [Line("", lvl, text, origin) for lvl, text in lines_spec]
    _rebuild_paths(out, base, base_level)
    return merge_bare(out)


def _parent(path: str) -> str:
    return path[: path.rfind("(")] if "(" in path else ""


def _text_op(state: Replay, idx: list[int], op: Op, origin: str) -> bool:
    """Apply a text operation to the first line in the subtree where its words are found (all lines for 'each place')."""
    a = op.args
    kind = op.kind

    def sub_first(old: str, new: str, every: bool = False) -> bool:
        # Quoted words match whole words only: striking "or" must not touch "order".
        o = norm(old)
        if not o:
            return False
        pattern = re.compile((r"(?<![A-Za-z0-9])" if o[0].isalnum() else "") + re.escape(o) + (r"(?![A-Za-z0-9])" if o[-1].isalnum() else ""))
        if not any(pattern.search(norm(state.lines[i].text)) for i in idx):
            # Laws sometimes quote words with different capitals from the Code ("secretary of State"); the publisher
            # still makes the change, so fall back to matching without regard to case.
            pattern = re.compile(pattern.pattern, re.I)
        hit = False
        for i in idx:
            t = norm(state.lines[i].text)
            if pattern.search(t):
                def put(m: re.Match) -> str:
                    words = norm(new) if new else ""
                    # Struck words that began with punctuation (", whichever is later") leave the word before them
                    # bare; new words that start with a letter need a space after it.
                    if words[:1].isalnum() and not o[0].isalnum() and m.start() and t[m.start() - 1].isalnum():
                        return " " + words
                    return words
                state.lines[i].text = norm(pattern.sub(put, t, count=0 if every else 1))
                state.lines[i].origin = origin
                hit = True
                if not every:
                    return True
        return hit

    if kind in ("replace", "replace_all"):
        if sub_first(a["old"], a["new"], kind == "replace_all"):
            return True
        old, new = norm(a["old"]), norm(a["new"])
        if len(old) > 1 and old[-1] in ",;." and new.endswith(old[-1]):
            return sub_first(old[:-1], new[:-1], kind == "replace_all")
        return False
    if kind in ("delete", "delete_all"):
        return sub_first(a["old"], "", kind == "delete_all")
    if kind in ("insert_after", "insert_before"):
        anchor, new = norm(a["anchor"]), norm(a["new"])
        # "(3)" + "(A)" prints as "(3)(A)"; punctuation attaches with no space.
        joiner = "" if new[:1] in ",.;:)" or (re.fullmatch(r"\([^)]+\)", anchor) and new.startswith("(")) else " "
        # The anchor matches whole words, and a cited number is not matched inside a longer citation: "section 122"
        # is not the start of "section 122(j)(2)(C)".
        pattern = re.compile(
            (r"(?<![A-Za-z0-9])" if anchor[:1].isalnum() else "") + re.escape(anchor)
            + (r"(?![A-Za-z0-9]|\((?:[0-9]+|[a-zA-Z]{1,4})\))" if anchor[-1:].isalnum() else "")
        )
        repl = anchor + joiner + new if kind == "insert_after" else new + " " + anchor
        for i in idx:
            t = norm(state.lines[i].text)
            if pattern.search(t):
                state.lines[i].text = norm(pattern.sub(lambda _m: repl, t, count=0 if a.get("all") else 1))
            elif anchor in t:
                state.lines[i].text = norm(t.replace(anchor, repl, 1))  # no whole-word match: take the plain one
            else:
                continue
            state.lines[i].origin = origin
            return True
        return False
    if kind == "replace_to_end":
        start_words = norm(a["start"])
        for n, i in enumerate(idx):
            t = norm(state.lines[i].text)
            pos = t.find(start_words)
            if pos >= 0:
                new = norm(a["new"])
                # "striking '; except that' and all that follows and inserting 'and there shall'": a word follows a word.
                joiner = " " if t[:pos][-1:].isalnum() and new[:1].isalnum() else ""
                state.lines[i].text = norm(t[:pos] + joiner + new) if new else norm(t[:pos])
                state.lines[i].origin = origin
                drop = set(idx[n + 1:])
                state.lines = [l for j, l in enumerate(state.lines) if j not in drop]
                return True
        return False
    if kind == "replace_range":
        joined = "\n".join(norm(state.lines[i].text) for i in idx)
        s, e = joined.find(norm(a["start"])), -1
        if s >= 0:
            e = joined.find(norm(a["through"]), s)
        if s < 0 or e < 0:
            return False
        e += len(norm(a["through"]))
        new_joined = joined[:s] + norm(a["new"]) + joined[e:]
        parts = new_joined.split("\n")
        first = idx[0]
        kept = [Line(state.lines[first].path, state.lines[first].level, parts[0], origin)]
        for part in parts[1:]:
            kept.append(Line("", state.lines[first].level, part, origin))
        state.lines[first: idx[-1] + 1] = kept
        return True
    if kind == "replace_sentence":
        # The provision's own line, after its designation and heading: "(f) Heading.—First sentence. Second."
        i = idx[0]
        t = norm(state.lines[i].text)
        head = re.match(r"^(?:\([^)]+\))*\s*(?:[^—.]{1,120}\.—)?", t).group(0)
        sentences = _sentences(t[len(head):])
        order = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "sixth": 5, "last": len(sentences) - 1}
        n = order.get(a["which"], -1)
        if not 0 <= n < len(sentences):
            return False
        new = norm(a["new"])
        spec = a.get("lines") or []
        if spec and re.match(r"^\(", norm(spec[0][1])):
            # The sentence is replaced by new provisions ("(b) Definitions.—(1) ..."): strike it and add them after.
            del sentences[n]
            line = state.lines[i]
            line.text = norm(head + (" " if head and not head.endswith("—") else "") + " ".join(sentences))
            line.origin = origin
            end = idx[-1] + 1
            state.lines[end:end] = _block_lines(spec, _parent(line.path), line.level, origin)
            return True
        if new:
            sentences[n] = new
        else:
            del sentences[n]
        state.lines[i].text = norm(head + (" " if head and not head.endswith("—") else "") + " ".join(sentences))
        state.lines[i].origin = origin
        return True
    if kind in ("replace_end", "insert_before_end", "append_text"):
        # "At the end" of a provision is the end of everything in it: its last child or its closing words. A provision
        # with no children ends on its own line.
        i = idx[-1]
        t = norm(state.lines[i].text)
        if kind == "append_text":
            state.lines[i].text = norm(t + " " + a["new"])
        elif kind == "insert_before_end":
            end = a["end"]
            if not t.endswith(end):
                return False
            head, new = t[: -len(end)], norm(a["new"])
            joiner = " " if head[-1:].isalnum() and new[:1].isalnum() else ""
            state.lines[i].text = norm(head + joiner + new + end)
        else:
            old, new = norm(a["old"]), norm(a["new"])
            if old and t.endswith(old):
                state.lines[i].text = norm(t[: -len(old)] + new)
            elif old and old[-1].isalnum() and re.search(re.escape(old) + r"([.;,])$", t):
                # Words struck "at the end" of a sentence sit before its closing punctuation.
                cut = re.search(re.escape(old) + r"([.;,])$", t)
                state.lines[i].text = norm(t[: cut.start()] + new + cut.group(1))
            elif not old:
                state.lines[i].text = norm(t + new)
            else:
                return False
        state.lines[i].origin = origin
        return True
    return False


_INLINE = re.compile(r"—(?=\((?:[0-9]+[A-Z]?|[a-z]{1,4}|[A-Z]{1,4}|[ivxl]+|[IVXL]+)\)\s)")


_ABBREVIATIONS = ("Pub", "L", "No", "Nos", "Sec", "Secs", "Stat", "U.S", "U.S.C", "Inc", "Co", "Corp", "St", "Mr", "Ms", "Dr", "v", "et seq", "e.g", "i.e")


def _sentences(text: str) -> list[str]:
    """Split at a period followed by a capital or an opening quotation, except after a common abbreviation."""
    out, start = [], 0
    for m in re.finditer(r"\.\s+(?=[A-Z\"“(])", text):
        before = text[start: m.start()].split()
        if before and before[-1].rstrip(".") in _ABBREVIATIONS:
            continue
        out.append(text[start: m.start() + 1].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


_ORDINALS = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9}


def _in_sentence(state: Replay, idx: list[int], which: str, op: Op, origin: str) -> bool:
    """Apply a text operation to one sentence of a line, then put the line back together."""
    if not idx:
        return False
    i = idx[0]
    t = norm(state.lines[i].text)
    head = re.match(r"^(?:\([^)]+\))*\s*(?:[^—.]{1,120}\.—)?", t).group(0)
    sentences = _sentences(t[len(head):])
    n = len(sentences) - 1 if which == "last" else _ORDINALS.get(which, -1)
    if not 0 <= n < len(sentences):
        return False
    scratch = Replay([Line("", 0, sentences[n])])
    if not _text_op(scratch, [0], op, origin):
        return False
    sentences[n] = scratch.lines[0].text
    state.lines[i].text = norm(head + (" " if head and not head.endswith("—") else "") + " ".join(sentences))
    state.lines[i].origin = origin
    return True


def repath(state: Replay) -> None:
    """A changed line that now opens with more designations than its path ("(3)(A) The trustee") takes the deeper
    path, as the Code does."""
    for line in state.lines:
        if line.origin is not None and line.path == "":
            m = re.match(r"^\(([^)]+)\)", norm(line.text))
            if m:
                line.path = f"({m.group(1)})"
            continue
        if line.origin is None or not line.path or " " in line.path:
            continue
        found = re.findall(r"\([^)]+\)", re.match(r"^(?:\([^)]+\))*", norm(line.text)).group(0))
        parts = re.findall(r"\([^)]+\)", line.path)
        if not found or found[0] not in parts:
            continue
        # Re-anchor at the line's first designation: "(3)(A) ..." under (d) is (d)(3)(A); "(3) ..." after "(A)" was
        # struck is (d)(3) again.
        at = len(parts) - 1 - parts[::-1].index(found[0])
        line.path = "".join(parts[:at] + found)


def split_inline(state: Replay) -> None:
    """Inserted words can open a new list ("does not include— (i) any member"); the Code prints each listed provision
    on its own line, so split there and nest the new line under the provision it came from."""
    out: list[Line] = []
    for line in state.lines:
        t = norm(line.text)
        m = _INLINE.search(t)
        if not m or line.origin is None:
            out.append(line)
            continue
        head, tail = t[: m.start() + 1], t[m.start() + 1:]
        d = _DESIGNATION.match(tail)
        out.append(Line(line.path, line.level, head, line.origin))
        out.append(Line(line.path + f"({d.group('d')})", line.level + 1, tail, line.origin))
    state.lines = out


def apply(state: Replay, instr: Instruction, *, before_text: Optional[list[Line]] = None) -> None:
    """Apply one instruction's operations in order; record what applied."""
    target = instr.path
    scope = None
    nth = 0
    sentence = None
    for op in instr.ops:
        if op.kind == "scope":
            scope = op.args
            continue
        if op.kind == "sentence":
            sentence = op.args["which"]
            continue
        if sentence and op.kind in ("replace", "replace_all", "delete", "delete_all", "insert_after", "insert_before", "insert_before_end", "append_text", "replace_end"):
            # "The sixth sentence of section 7(m) is amended": work on that sentence of the provision's own line.
            ok = _in_sentence(state, _indices(state, target)[:1], sentence, op, instr.identifier)
            state.results.append(OpResult(instr.identifier, op.kind, ok, "" if ok else "the sentence or its words were not found"))
            continue
        if op.kind == "nth":
            nth = op.args["n"]
            continue
        if op.kind == "table_of_contents":
            state.results.append(OpResult(instr.identifier, op.kind, True, "table of contents only"))
            continue
        idx = _indices(state, target)
        if nth and idx:
            # "The second subsection (c)": when two provisions share a letter, take the nth one.
            blocks = _blocks(state, target)
            idx = blocks[nth - 1] if len(blocks) >= nth else []
        if scope and idx:
            if scope["side"] == "preceding":
                # "in the matter preceding paragraph (1)": only the target's own opening words.
                idx = idx[:1]
            else:
                # "in the matter following paragraph (2)": the closing words after the target's list.
                closing = [i for i in idx if re.match(re.escape(target) + r"\s+(?:closing words|text)", state.lines[i].path)]
                idx = closing or idx[-1:]
        ok = False
        detail = ""
        if op.kind in ("replace", "replace_all", "delete", "delete_all", "insert_after", "insert_before", "replace_to_end",
                       "replace_range", "replace_end", "insert_before_end", "append_text", "replace_sentence"):
            ok = bool(idx) and _text_op(state, idx, op, instr.identifier)
            if ok:
                split_inline(state)
                repath(state)
            else:
                detail = "the quoted words were not found in the target"
        elif op.kind == "append_block":
            base_level = (state.lines[idx[0]].level + 1) if idx and target else (1 if target else 0)
            new = _block_lines(op.args["lines"], target, base_level - (0 if target else 0), instr.identifier)
            end = (idx[-1] + 1) if idx else len(state.lines)
            state.lines[end:end] = new
            ok = bool(new)
        elif op.kind in ("replace_block", "replace_provision"):
            sub = target + (op.args.get("target") or "") if op.kind == "replace_provision" else target
            sidx = _indices(state, sub)
            level = state.lines[sidx[0]].level if sidx else 0
            new = _block_lines(op.args["lines"], _parent(sub), level, instr.identifier)
            if sidx:
                state.lines[sidx[0]: sidx[-1] + 1] = new
            else:
                state.lines.extend(new)
            ok = bool(new)
        elif op.kind == "insert_block_after" or op.kind == "insert_block_before":
            sib = target + op.args["sibling"]
            sidx = _indices(state, sib)
            if sidx:
                level = state.lines[sidx[0]].level
                new = _block_lines(op.args["lines"], target, level, instr.identifier)
                at = sidx[-1] + 1 if op.kind == "insert_block_after" else sidx[0]
                state.lines[at:at] = new
                ok = True
            else:
                detail = f"{sib} was not found"
        elif op.kind == "delete_provision":
            sidx = _indices(state, target + op.args["target"])
            if sidx:
                del state.lines[sidx[0]: sidx[-1] + 1]
                ok = True
        elif op.kind == "repeal":
            idx = _indices(state, target)
            if idx:
                drop = set(idx)
                state.lines = [l for j, l in enumerate(state.lines) if j not in drop]
                ok = True
        elif op.kind == "redesignate":
            # All renumbering happens at once: "(i) through (k) as (j) through (l)" must not chain (i)->(j)->(k).
            pairs = [(target + old, target + new, old, new) for old, new in op.args["pairs"]]
            only: Optional[set[int]] = None
            if op.args.get("nth"):
                # "the second subsection (c)": renumber only the nth provision with that letter.
                blocks = _blocks(state, pairs[0][0])
                only = set(blocks[op.args["nth"] - 1]) if len(blocks) >= op.args["nth"] else set()
            for j, line in enumerate(state.lines):
                if only is not None and j not in only:
                    continue
                for full_old, full_new, old, new in pairs:
                    if _in_subtree(line.path, full_old):
                        # The provision's own line, or a combined line printed with it ("(4)(A) The Copyright").
                        was_head = line.path == full_old or line.path[len(target):].startswith(old)
                        line.path = full_new + line.path[len(full_old):]
                        if was_head and norm(line.text).startswith(old):
                            line.text = norm(new + norm(line.text)[len(old):])
                        line.origin = instr.identifier
                        ok = True
                        break
        elif op.kind == "revert" and before_text is not None:
            idx = _indices(state, target)
            old = [Line(l.path, l.level, l.text, instr.identifier) for l in before_text if _in_subtree(l.path, target)]
            if idx:
                state.lines[idx[0]: idx[-1] + 1] = old
            else:
                state.lines.extend(old)
            ok = bool(old)
        state.results.append(OpResult(instr.identifier, op.kind, ok, detail))
