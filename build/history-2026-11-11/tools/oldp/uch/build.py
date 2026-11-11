"""Builds the history of a US Code title: one record per amending instruction, verified by replay where possible.

For each pair of consecutive versions (annual editions, then the OLRC release points served after the last edition) it
finds the sections that changed, gathers the public laws enacted (or taking effect) between the two versions (by date
for editions, by law number for release points, which are each current through a named law), replays those laws' instructions on the older text
in date order, and compares the result with the newer edition. Each instruction becomes a change record, like a commit:
the provision before and after it, the law and bill that made it, the dates, the publisher's own note and how far the
replay matched. Whatever the replay cannot explain is published too, labelled as such.

    python -m services.us_code_history.build --title 11 --from 2017 --to 2024 --out <dir>
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .adjustments import notices_in
from .applies import applies
from .editions import Edition, Section, fingerprint, parse_edition
from .laws import _NUMBER_WORDS, Instruction, Law, _add, load_law
from .notes import NoteEntry, parse_amendment_notes, parse_date_notes
from .releasepoints import choose, list_release_points, load_release_point
from .replay import Line, OpResult, Replay, apply, canon, norm, start
from .sources import edition_page, edition_url, fetch, wayback

METHOD_VERSION = "1"


def load_edition(title: int, year: int) -> Edition:
    got = fetch(edition_url(year, title))
    if got is None:
        raise SystemExit(f"GovInfo has no {year} edition of title {title}")
    return parse_edition(got.data, title=title, year=year, sha256=got.sha256, url=got.url, fetched_at=got.fetched_at, page=edition_page(year, title))


def _between(law: Law, a: Edition, b: Edition) -> bool:
    """Whether a law was enacted after version a and is included in version b. A release point is current through a
    named law, so law numbers decide there; annual editions are compared by date."""
    number = (law.congress, law.number)
    if a.through_law and number <= a.through_law:
        return False
    if b.through_law and number > b.through_law:
        return False
    # A law enacted on the day an edition is current through may or may not be in it; it stays a candidate, and the
    # replay decides (an instruction the older text already shows cannot reproduce the newer one).
    return (a.through_law is not None or law.approved >= a.current_through) and (b.through_law is not None or law.approved <= b.current_through)


def words_diff(before: str, after: str) -> list[dict]:
    """Word-level differences as segments: {"t": "eq"|"del"|"ins", "s": text}."""
    tokens = lambda s: re.findall(r"\s+|[\w$§%]+|[^\w\s]", s)  # noqa: E731
    out: list[dict] = []

    def words(a: list[str], b: list[str]) -> None:
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                out.append({"t": "eq", "s": "".join(a[i1:i2])})
            else:
                if i2 > i1:
                    out.append({"t": "del", "s": "".join(a[i1:i2])})
                if j2 > j1:
                    out.append({"t": "ins", "s": "".join(b[j1:j2])})

    # Lines first, then words only inside the lines that differ: a word diff over a whole long section is quadratic.
    la, lb = before.split("\n"), after.split("\n")
    if len(la) + len(lb) <= 8:
        words(tokens(before), tokens(after))
    else:
        ka, kb = [l + "\n" for l in la], [l + "\n" for l in lb]
        ka[-1], kb[-1] = la[-1], lb[-1]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
            if tag == "equal":
                out.append({"t": "eq", "s": "".join(ka[i1:i2])})
            else:
                words(tokens("".join(ka[i1:i2])), tokens("".join(kb[j1:j2])))
    merged: list[dict] = []
    for seg in out:
        if merged and merged[-1]["t"] == seg["t"]:
            merged[-1]["s"] += seg["s"]
        else:
            merged.append(dict(seg))
    return merged


def _subtree(lines: list[Line], path: str) -> list[Line]:
    if path == "":
        return list(lines)
    return [l for l in lines if l.path == path or l.path.startswith(path + "(") or l.path.startswith(path + " ")]


def _lines_of(section: Optional[Section]) -> list[Line]:
    return [Line(p.path, p.level, p.text) for p in section.provisions] if section else []


def _line(l: Line) -> dict:
    return {"path": l.path, "level": l.level, "text": l.text}


def _edits(before: list[Line], after: list[Line]) -> list[list]:
    """The lines one replay step replaced, as [start, end, new lines] against the text before it, so a whole section
    after each step can be rebuilt without storing it each time."""
    key = lambda l: (l.path, l.level, l.text)
    ops = difflib.SequenceMatcher(None, [key(l) for l in before], [key(l) for l in after], autojunk=False).get_opcodes()
    return [[i1, i2, [_line(l) for l in after[j1:j2]]] for op, i1, i2, j1, j2 in ops if op != "equal"]


def _residual(state: list[Line], target: list[Line]) -> list[str]:
    """Paths where the replay and the edition disagree (keys from canon(), so closing words line up)."""
    placeholder = re.compile(r"^\[\([^)]+\)(?:\s*to\s*\([^)]+\))?\s+Repealed\.")
    heading = re.compile(r"^((?:\([^)]+\))+\s*)([^—]{1,150}?\.—)")

    def key(lines: list[Line]) -> dict[str, str]:
        kept = [l for l in lines if not placeholder.match(norm(l.text))]
        return {p: heading.sub(lambda m: m.group(1) + m.group(2).lower(), t) for p, t in canon(kept)}

    have = key(state)
    want = key(target)
    bad = [p for p, t in want.items() if have.get(p) != t]
    bad += [p for p in have if p not in want]
    return sorted(set(bad))


def _whole(instr: Instruction, section: str) -> bool:
    """Whether the instruction adds, replaces or strikes this section whole: a chapter or part added with its sections,
    or "inserting after section 121 the following: § 121A", whatever provision the instruction names as its target."""
    return instr.section != section and any(
        (op.kind == "append_block" and section in (op.args.get("sections") or {}))
        or (op.kind == "replace_sections" and (section in op.args["remove"] or section in op.args["sections"]))
        for op in instr.ops)


def _targets(instr: Instruction, section: str, b_section: Optional[Section]) -> bool:
    if instr.section == section:
        return True
    if not instr.section.startswith("ch") and _whole(instr, section):
        return True
    if instr.section.startswith("ch"):
        for op in instr.ops:
            if op.kind == "append_block" and b_section is not None and section in (op.args.get("sections") or {}):
                return True
            if op.kind == "replace_sections" and (section in op.args["remove"] or section in op.args["sections"]):
                return True
    return False


def _as_lines(spec: list, base_level: int = 0) -> list[Line]:
    from .replay import _rebuild_paths, merge_bare
    out = [Line("", lvl, text) for lvl, text in spec]
    _rebuild_paths(out, "", base_level)
    return merge_bare(out)


def _law_numbers_in(edition: Edition, years: set[int]) -> set[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for s in edition.sections.values():
        for e in parse_amendment_notes(s.notes.get("amendment-note") or []):
            if e.year in years:
                found.update((l.congress, l.number) for l in e.laws)
        for d in parse_date_notes(s.notes):
            found.update((l.congress, l.number) for l in d.laws if l.congress >= 110)
        # A section added whole has no amendment notes; its source credit names the law that added it. Only laws from
        # the Congresses that sat during these years are taken, so old laws in long credits are not fetched.
        congresses = {(y - 1789) // 2 + 1 for y in years} | {(y - 1790) // 2 + 1 for y in years}
        for c, n in re.findall(r"Pub\. L\. (\d+)[–—-](\d+)", s.source_credit or ""):
            if int(c) in congresses:
                found.add((int(c), int(n)))
    return found


def _notes_for(section: Optional[Section], law: Law, path: str, years: set[int]) -> list[NoteEntry]:
    if section is None:
        return []
    out = []
    for e in parse_amendment_notes(section.notes.get("amendment-note") or []):
        if e.year not in years or not e.mentions(law.congress, law.number):
            continue
        if not e.paths or not path or any(p.startswith(path) or path.startswith(p) for p in e.paths):
            out.append(e)
    return out


def build(title: int, first: int, last: int, out: Path, *, summaries: bool = False, release_points: bool = True) -> dict:
    editions = [load_edition(title, y) for y in range(first, last + 1)]
    if release_points:
        points = list_release_points()
        later = [p for p in points if p.date > editions[-1].current_through and not p.partial]
        chosen = choose(points, title, editions[-1].current_through)
        for point in chosen:
            version = load_release_point(point, title)
            if version is not None:
                editions.append(version)
            elif later and point.key == later[-1].key:
                # The newest release point is listed before its files are published. Fall back to the newest one that
                # loads, so the history still ends at the current text.
                for older in reversed(later[:-1]):
                    if older.key in {e.key.removeprefix("pl") for e in editions}:
                        break
                    fallback = load_release_point(older, title)
                    if fallback is not None:
                        editions.append(fallback)
                        break
    order = {e.key: n for n, e in enumerate(editions)}
    laws: dict[str, Law] = {}
    missing: set[str] = set()
    records: list[dict] = []
    transitions: list[dict] = []
    replays: list[dict] = []   # the whole section after each step, where a version's change took several instructions
    applied_ids: set[str] = set()
    pending: list[tuple[Law, Instruction]] = []      # instructions the law set to take effect later
    carried: list[tuple[Law, Instruction]] = []      # instructions the last edition did not show yet
    unparsed: list[dict] = []

    # The start of the previous window. Before the first window there is none, but a large law enacted in the year
    # before the first version's cutoff may not all be printed in it yet (Pub. L. 115-97, enacted nine days before the
    # 2017 edition's cutoff): such laws stay in play for the first window too, and the replay decides.
    from datetime import date as _d, timedelta as _td
    floor = (_d.fromisoformat(editions[0].current_through) - _td(days=365)).isoformat() if editions[0].kind == "edition" else ""
    for a, b in zip(editions, editions[1:]):
        window = (a.current_through, b.current_through)
        late_laws: list[Law] = []
        years = set(range(a.year, b.year + 2))
        wanted = _law_numbers_in(b, years)
        window_laws: list[Law] = []
        for congress, number in sorted(wanted):
            key = f"{congress}-{number}"
            if key in missing:
                continue
            if key not in laws:
                law = load_law(congress, number, title=title)
                if law is None:
                    missing.add(key)   # not published as USLM (before the 113th Congress): asked once per build
                    continue
                laws[key] = law
            law = laws[key]
            if _between(law, a, b):
                window_laws.append(law)
                for instr in law.instructions:
                    if instr.effective and instr.effective > window[1]:
                        pending.append((law, instr))
            elif a.through_law is None and floor and floor <= law.approved < a.current_through:
                # Enacted before the older edition's cutoff, but the publisher can take longer than that to execute a
                # very large law; whatever of it no edition has shown yet stays in play.
                late_laws.append(law)
        due_pending = [(l, i) for l, i in pending if i.identifier not in applied_ids and i.effective and i.effective <= window[1]]
        # Amendments an earlier edition did not show yet stay in play until an edition shows them.
        due_pending += [(l, i) for l, i in carried if i.identifier not in applied_ids and (l, i) not in due_pending]
        due_pending += [(l, i) for l in late_laws for i in l.instructions
                        if i.identifier not in applied_ids and not (i.effective and i.effective > window[1]) and (l, i) not in due_pending]
        changed = []
        for number in sorted(set(a.sections) | set(b.sections), key=lambda n: (int(re.match(r"\d+", n).group()), n)):
            sa, sb = a.sections.get(number), b.sections.get(number)
            if "\n".join(norm(p.text) for p in (sa.provisions if sa else [])) != "\n".join(norm(p.text) for p in (sb.provisions if sb else [])):
                changed.append(number)

        t_records: list[str] = []
        for number in changed:
            sa, sb = a.sections.get(number), b.sections.get(number)
            candidates: list[tuple[Law, Instruction]] = []
            for law in window_laws:
                for instr in law.instructions:
                    if _targets(instr, number, sb) and not instr.heading and not (instr.effective and instr.effective > window[1]):
                        candidates.append((law, instr))
            candidates += [(l, i) for l, i in due_pending if _targets(i, number, sb) and not i.heading]
            candidates.sort(key=lambda x: (x[1].effective or x[0].approved, x[0].approved, x[1].order))
            target_lines = _lines_of(sb)

            def run(chosen: list[tuple[Law, Instruction]]) -> tuple[Replay, list[dict]]:
                state = start(sa)
                steps = []
                for law, instr in chosen:
                    if instr.section.startswith("ch") or _whole(instr, number):
                        spec = next((op.args["sections"][number] for op in instr.ops if op.kind in ("append_block", "replace_sections") and number in (op.args.get("sections") or {})), [])
                        struck = any(op.kind == "replace_sections" and number in op.args["remove"] for op in instr.ops)
                        before = [Line(l.path, l.level, l.text) for l in state.lines] if struck else []
                        state.lines = [Line(l.path, l.level, l.text, instr.identifier) for l in _as_lines(spec)]
                        state.results.append(OpResult(instr.identifier, "replace_sections" if struck else "append_block", bool(spec) or struck))
                        steps.append({"law": law, "instr": instr, "before": before, "after": [Line(l.path, l.level, l.text) for l in state.lines],
                                      "state": [Line(l.path, l.level, l.text) for l in state.lines]})
                        continue
                    before = [Line(l.path, l.level, l.text) for l in _subtree(state.lines, instr.path)]
                    prior = None
                    if any(op.kind == "revert" for op in instr.ops):
                        prior = _prior_text(editions, number, law.approved)
                    apply(state, instr, before_text=prior)
                    after = [Line(l.path, l.level, l.text) for l in _subtree(state.lines, instr.path)]
                    steps.append({"law": law, "instr": instr, "before": before, "after": after, "state": [Line(l.path, l.level, l.text) for l in state.lines]})
                return state, steps

            chosen = [c for c in candidates if not c[1].unparsed]
            state, steps = run(chosen)
            best = len(_residual(state.lines, target_lines))
            # The edition is the judge of what has happened. A law can change its own dates later (an extension), the
            # publisher can hold an amendment until it takes effect, or two laws can make the same change. Leave out
            # any instruction whose replay makes the result further from the edition; it is tried again next edition.
            for c in list(chosen):
                trial = [x for x in chosen if x is not c]
                st, sp = run(trial)
                score = len(_residual(st.lines, target_lines))
                if score < best:
                    chosen, state, steps, best = trial, st, sp, score
            for law, instr in chosen:
                applied_ids.add(instr.identifier)
            for c in candidates:
                if c not in chosen and not c[1].unparsed and c not in carried and c[1].identifier not in applied_ids:
                    carried.append(c)

            residual = set(_residual(state.lines, target_lines))
            n = 0
            sequence: list[dict] = []
            for step in steps:
                law, instr = step["law"], step["instr"]
                ops = [r for r in state.results if r.instruction == instr.identifier]
                if not ops or not any(r.applied for r in ops):
                    continue
                n += 1
                whole = instr.section.startswith("ch") or _whole(instr, number)
                path = instr.path if not whole else ""
                in_edition = _subtree(target_lines, path)
                touched = {k for k, _ in canon(step["after"])} | {k for k, _ in canon(step["before"])}
                mismatch = sorted(p for p in residual if any(p == t or p.startswith(t) for t in touched) or (path and (p == path or p.startswith(path))))
                # A step is replayed when every operation applied and its result is what the edition prints: either
                # its own result already matches, or the provisions it touched end up matching after later steps.
                own_match = canon(step["after"]) == canon(in_edition) if path or whole else False
                if all(r.applied for r in ops) and (own_match or not mismatch):
                    status = "replayed"
                    mismatch = []
                else:
                    status = "partly replayed" if any(r.applied for r in ops) else "not replayed"
                before_text = "\n".join(l.text for l in step["before"])
                after_text = "\n".join(norm(l.text) for l in step["after"])
                edition_text = "\n".join(l.text for l in in_edition)
                rec_id = f"{b.key}-{law.pl}-{number}-{n}"
                notes = _notes_for(sb, law, path, years)
                date_notes = [d for d in parse_date_notes(sb.notes) if any(l.congress == law.congress and l.number == law.number for l in d.laws)] if sb else []
                records.append({
                    "id": rec_id,
                    "title": title,
                    "section": number,
                    "heading": (sb or sa).heading if (sb or sa) else "",
                    "path": path,
                    "kind": _kind(step["before"], step["after"], instr),
                    "edition_from": a.key,
                    "edition_to": b.key,
                    "law": law.pl,
                    "instruction": {"id": instr.identifier, "label": instr.label, "text": instr.text, "ops": [{"kind": o.kind, **{k: v for k, v in o.args.items() if k not in ("lines", "sections")}} for o in instr.ops], "effective": instr.effective, "timing": instr.timing},
                    "status": status,
                    "ops": [{"op": r.op, "applied": r.applied, "detail": r.detail} for r in ops],
                    "mismatch": mismatch,
                    "before": before_text,
                    "after": after_text,
                    "in_edition": edition_text,
                    "diff": words_diff(before_text, edition_text if status != "not replayed" else after_text),
                    "fingerprints": {"before": fingerprint(norm(before_text)), "after": fingerprint(norm(edition_text)), "edition_from": a.sha256, "edition_to": b.sha256, "law": law.sha256},
                    "dates": {"enacted": law.approved, "effective": instr.effective, "edition_current_through": b.current_through, "edition_year": b.year, "edition": b.key, "recorded": datetime.now(timezone.utc).date().isoformat()},
                    "publisher_notes": [{"year": e.year, "location": e.location, "text": e.text} for e in notes],
                    "date_notes": [{"kind": d.kind, "heading": d.heading, "text": d.text[:1500]} for d in date_notes][:3],
                    "applies": applies(law.pl, instr.identifier, date_notes, law.approved, instr.effective, instr.timing),
                })
                t_records.append(rec_id)
                sequence.append({"record": rec_id, "edits": _edits(sequence[-1]["state"] if sequence else _lines_of(sa), step["state"]), "state": step["state"]})
            if len(sequence) > 1:
                replays.append({"section": number, "from": a.key, "to": b.key, "start": [_line(l) for l in _lines_of(sa)],
                                "steps": [{"record": s["record"], "edits": s["edits"]} for s in sequence]})
            # What the replay could not explain, grouped by top-level provision.
            explained_paths = set()
            for step in steps:
                explained_paths |= {l.path for l in step["after"]} | {l.path for l in step["before"]}
            leftovers = sorted(p for p in residual)
            groups: dict[str, list[str]] = {}
            for p in leftovers:
                top = re.match(r"^(\([^)]+\))", p)
                groups.setdefault(top.group(1) if top else p, []).append(p)
            for top, paths in groups.items():
                before_lines = _subtree(_lines_of(sa), top if top.startswith("(") else "")
                after_lines = _subtree(target_lines, top if top.startswith("(") else "")
                replay_lines = _subtree(state.lines, top if top.startswith("(") else "")
                before_text = "\n".join(l.text for l in before_lines)
                after_text = "\n".join(l.text for l in after_lines)
                if norm(before_text) == norm(after_text) and not replay_lines:
                    continue
                notes_here: list[NoteEntry] = []
                if sb:
                    for e in parse_amendment_notes(sb.notes.get("amendment-note") or []):
                        if e.year in years and (not e.paths or any(p2.startswith(top) or top.startswith(p2) for p2 in e.paths)):
                            notes_here.append(e)
                unread = [
                    {"law": l.pl, "label": i.label, "text": i.text}
                    for l, i in candidates if i.unparsed and (not i.path or any(p.startswith(i.path) or i.path.startswith(p) for p in paths))
                ]
                n += 1
                rec_id = f"{b.key}-unexplained-{number}-{n}"
                laws_named = sorted({l.pl for e in notes_here for l in e.laws})
                records.append({
                    "id": rec_id,
                    "title": title,
                    "section": number,
                    "heading": (sb or sa).heading if (sb or sa) else "",
                    "path": top if top.startswith("(") else "",
                    "kind": _kind(before_lines, after_lines, None),
                    "edition_from": a.key,
                    "edition_to": b.key,
                    "law": None,
                    "candidate_laws": laws_named,
                    "unread_instructions": unread,
                    "instruction": None,
                    "status": "publisher's note only" if notes_here else "unexplained",
                    "ops": [],
                    "mismatch": paths,
                    "before": before_text,
                    "after": after_text,
                    "in_edition": after_text,
                    "replay": "\n".join(l.text for l in replay_lines),
                    "diff": words_diff(before_text, after_text),
                    "fingerprints": {"before": fingerprint(norm(before_text)), "after": fingerprint(norm(after_text)), "edition_from": a.sha256, "edition_to": b.sha256},
                    "dates": {"enacted": None, "effective": None, "edition_current_through": b.current_through, "edition_year": b.year, "edition": b.key, "recorded": datetime.now(timezone.utc).date().isoformat()},
                    "publisher_notes": [{"year": e.year, "location": e.location, "text": e.text} for e in notes_here],
                    "date_notes": [],
                })
                t_records.append(rec_id)
                unparsed.extend({"record": rec_id, **u} for u in unread)

        # Section headings: a law that says "in the section heading" changes the heading, which the text comparison
        # above does not see. Replay those instructions against the old heading and compare with the new one.
        for number in sorted(set(a.sections) & set(b.sections), key=lambda n: (int(re.match(r"\d+", n).group()), n)):
            sa, sb = a.sections[number], b.sections[number]
            if norm(sa.heading) == norm(sb.heading):
                continue
            def heads(i: Instruction) -> bool:
                return i.section == number and (i.heading or "in the heading" in i.text or any(o.kind == "replace_block" and o.args.get("heading") for o in i.ops))

            hc = [(l, i) for l in window_laws for i in l.instructions if heads(i) and not (i.effective and i.effective > window[1])]
            hc += [(l, i) for l, i in due_pending if heads(i) and (l, i) not in hc]
            state = Replay([Line("", 0, sa.heading)])
            for law, instr in hc:
                rewrite = next((o.args["heading"] for o in instr.ops if o.kind == "replace_block" and o.args.get("heading")), None)
                if rewrite is not None:
                    state.lines[0].text = rewrite   # the section was amended generally, heading and all
                else:
                    apply(state, instr)
            matched = norm(state.lines[0].text) == norm(sb.heading) if state.lines else False
            changed.append(number) if number not in changed else None
            for n, (law, instr) in enumerate(hc if matched else [], start=1):
                applied_ids.add(instr.identifier)
                rec_id = f"{b.key}-{law.pl}-{number}-h{n}"
                records.append(_heading_record(rec_id, title, number, sa, sb, a, b, law, instr, years, "replayed"))
                t_records.append(rec_id)
            if not matched:
                rec_id = f"{b.key}-unexplained-{number}-h1"
                records.append(_heading_record(rec_id, title, number, sa, sb, a, b, None, None, years, "unexplained"))
                t_records.append(rec_id)

        floor = a.current_through
        transitions.append({
            "from": a.key, "to": b.key, "window": list(window),
            "sections_changed": changed,
            "laws": sorted({r["law"] for r in records if r["id"] in t_records and r["law"]}),
            "records": t_records,
        })

    meta = _meta(title, editions, laws, transitions, records)
    # Instructions in the laws covered that no edition showed: clerical changes to tables of contents, changes held
    # beyond the last edition, or anything the replay could not place. Published so coverage is stated honestly.
    meta["not_shown"] = []
    covered = {l["pl"] for l in meta["laws"]}
    for law in laws.values():
        if law.pl not in covered:
            continue
        for i in law.instructions:
            if i.identifier in applied_ids:
                continue
            entry = {"law": law.pl, "label": i.label, "section": i.section, "path": i.path, "text": i.text[:600], "note": None}
            amends_law = re.search(r"[Ss]ection (\d+) of the .{0,160}?\((?:Public Law|Pub\. L\.) (\d+)[–—\-](\d+)[;)]", i.context + " " + i.text)
            if any(o.kind == "table_of_contents" for o in i.ops):
                entry["reason"] = "table of contents only"
            elif re.search(r"U\.S\.C\. \d+[a-z]? note\)", i.text) and amends_law:
                # An amendment to another law's provision printed as a note in the Code, such as a sunset date.
                entry["reason"] = "changes a provision of another law printed as a note"
                sub = re.search(r"in subsection \(([^)]+)\)((?:\([^)]+\))*)", i.text)
                target_label = f"§{amends_law.group(1)}" + (f"({sub.group(1)}){sub.group(2)}" if sub else "")
                target_law = f"{amends_law.group(2)}-{amends_law.group(3)}"
                # The provision changed may be the instruction itself, or a sibling that dates it ("(B) Effective
                # date"): try the exact label first, then its parent.
                for label in (target_label, re.sub(r"\([^)]+\)$", "", target_label)):
                    hits = [r for r in records if r["law"] == target_law and r["instruction"] and label in r["instruction"]["label"]]
                    for r in hits:
                        r.setdefault("changed_by", []).append({"law": law.pl, "label": i.label, "text": i.text[-300:]})
                        _redate(r, i.text, law.pl)
                    if hits:
                        break
            elif i.effective and i.effective > editions[-1].current_through:
                entry["reason"] = "takes effect after the last version covered"
            elif i.unparsed:
                entry["reason"] = "wording not read automatically"
            else:
                entry["reason"] = "not shown in any version covered"
                # The publisher's effective-date note usually says why (for example, a condition that never happened).
                for e in reversed(editions):
                    s = e.sections.get(i.section)
                    if not s:
                        continue
                    for d in parse_date_notes(s.notes):
                        if any(l.congress == law.congress and l.number == law.number for l in d.laws):
                            entry["note"] = {"heading": d.heading, "text": d.text[:1200], "edition": e.key, "edition_label": e.label}
                            break
                    if entry["note"]:
                        break
                if entry["note"] and re.search(r"(?:take effect|effective) on the date on which", entry["note"]["text"]):
                    entry["reason"] = "depends on a condition the editions do not show as met"
            meta["not_shown"].append(entry)
    # A provision that dates a whole Act ("This Act and the amendments made by this Act shall take effect 180 days
    # after") covers every change the Act made, including new sections whose notes do not repeat it.
    from .applies import whole_act_dates
    whole = whole_act_dates([(r["law"], d) for r in records for d in r.get("date_notes") or []])
    for r in records:
        a = r.get("applies")
        if a and a["in_force"]["basis"] == "enactment" and r["law"] in whole:
            a["in_force"] = whole[r["law"]]
    # A later law that moved a change's date (see _redate) moves when it came into force.
    for r in records:
        if r.get("applies") and r["dates"].get("effective_set_by"):
            r["applies"]["in_force"].update(date=r["dates"]["effective"], basis="law", words=(r.get("instruction") or {}).get("timing") or "")
    _link_lifecycles(records, order)
    from .agent import propose_causes, rule_summary, summarise
    if summaries:
        propose_causes(records, laws)
        summarise(meta, records, previous=_previous(out))
    else:
        from .agent import law_rule_summary
        for r in records:
            r["summary"], r["summary_source"] = rule_summary(r), "rule"
        by_id = {r["id"]: r for r in records}
        for law in meta["laws"]:
            recs = [by_id[i] for i in law["records"] if i in by_id]
            if recs:
                law["summary"], law["summary_source"] = law_rule_summary(law, recs), "rule"
    _write(out, title, editions, meta, records, replays)
    return meta


_PERIOD = r"(\d+|one|two|three|four|five|six) (year|month|day)s?"


def _redate(r: dict, text: str, by: str) -> None:
    """A later law that changes the period in the provision dating a record ("by striking '1 year' and inserting
    '2 years'") moves the record's date; keep the date as first enacted beside it."""
    m = re.search(rf"striking [“\"]{_PERIOD}[”\"] and inserting [“\"]{_PERIOD}[”\"]", text)
    timing = (r.get("instruction") or {}).get("timing") or ""
    enacted = r["dates"].get("enacted")
    if not m or not enacted or not re.search(rf"\b{m.group(1)} {m.group(2)}s?\b", timing):
        return
    n = int(m.group(3)) if m.group(3).isdigit() else _NUMBER_WORDS[m.group(3)]
    r["dates"]["effective_as_enacted"] = r["dates"].get("effective")
    r["dates"]["effective"] = _add(enacted, n, m.group(4))
    r["dates"]["effective_set_by"] = by


def _heading_record(rec_id: str, title: int, number: str, sa: Section, sb: Section, a: Edition, b: Edition,
                    law: Optional[Law], instr: Optional[Instruction], years: set[int], status: str) -> dict:
    """A change to a section's heading, recorded like any other change with part "heading"."""
    notes = _notes_for(sb, law, "", years) if law else []
    return {
        "id": rec_id,
        "title": title,
        "section": number,
        "heading": sb.heading,
        "path": "",
        "part": "heading",
        "kind": "amended",
        "edition_from": a.key,
        "edition_to": b.key,
        "law": law.pl if law else None,
        "instruction": {"id": instr.identifier, "label": instr.label, "text": instr.text, "ops": [{"kind": o.kind, **{k: v for k, v in o.args.items() if k not in ("lines", "sections")}} for o in instr.ops], "effective": instr.effective, "timing": instr.timing} if instr else None,
        "status": status,
        "ops": [],
        "mismatch": [] if status == "replayed" else ["heading"],
        "before": sa.heading,
        "after": sb.heading,
        "in_edition": sb.heading,
        "diff": words_diff(sa.heading, sb.heading),
        "fingerprints": {"before": fingerprint(norm(sa.heading)), "after": fingerprint(norm(sb.heading)), "edition_from": a.sha256, "edition_to": b.sha256, **({"law": law.sha256} if law else {})},
        "dates": {"enacted": law.approved if law else None, "effective": instr.effective if instr else None, "edition_current_through": b.current_through, "edition_year": b.year, "edition": b.key, "recorded": datetime.now(timezone.utc).date().isoformat()},
        "publisher_notes": [{"year": e.year, "location": e.location, "text": e.text} for e in notes],
        "date_notes": [],
        "applies": applies(law.pl, instr.identifier, [d for d in parse_date_notes(sb.notes) if any(l.congress == law.congress and l.number == law.number for l in d.laws)],
                           law.approved, instr.effective, instr.timing) if law and instr else None,
    }


def _previous(out: Path) -> Optional[dict]:
    """The last build's records and laws, so unchanged summaries are not written again."""
    try:
        return {"records": json.loads((out / "records.json").read_text(encoding="utf-8")),
                "laws": json.loads((out / "meta.json").read_text(encoding="utf-8"))["laws"]}
    except (OSError, ValueError, KeyError):
        return None


def _link_lifecycles(records: list[dict], order: dict[str, int]) -> None:
    """A dated instruction that undoes an earlier change by the same law (a sunset) is linked both ways, so a reader
    of the first change sees when it ended and why."""
    for r in records:
        ins = r.get("instruction") or {}
        if not ins.get("effective"):
            continue
        for earlier in records:
            if earlier is r or earlier["law"] != r["law"] or earlier["section"] != r["section"]:
                continue
            if (earlier.get("instruction") or {}).get("effective"):
                continue
            if order[earlier["edition_to"]] > order[r["edition_to"]]:
                continue
            a, b = earlier["path"], r["path"]
            if a == b or a.startswith(b) or b.startswith(a):
                earlier.setdefault("ended_by", []).append(r["id"])
                r.setdefault("ends", []).append(earlier["id"])
                r["kind"] = "sunset" if r["kind"] != "restored" else r["kind"]


def _prior_text(editions: list[Edition], number: str, approved: str) -> Optional[list[Line]]:
    """The section as it read the day before a law was enacted: the last edition current before that date."""
    best = None
    for e in editions:
        if e.current_through < approved and number in e.sections:
            best = e
    return _lines_of(best.sections[number]) if best else None


def _kind(before: list, after: list, instr: Optional[Instruction]) -> str:
    if not before and after:
        return "added"
    if before and not after:
        return "removed"
    if instr and any(o.kind == "revert" for o in instr.ops):
        return "restored"
    if instr and any(o.kind in ("replace_block", "replace_provision") for o in instr.ops):
        return "rewritten"
    if instr and any(o.kind == "redesignate" for o in instr.ops):
        return "redesignated"
    return "amended"


def _meta(title: int, editions: list[Edition], laws: dict[str, Law], transitions: list[dict], records: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    used = {r["law"] for r in records if r["law"]}
    # The archive lookups are independent and cached; ask for them several at a time before they are read below.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(wayback, [e.url for e in editions] + [l.page for l in laws.values() if l.pl in used]))
    return {
        "title": title,
        "title_name": editions[-1].title_name or f"Title {title}",
        "method_version": METHOD_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "editions": [{
            "key": e.key, "label": e.label, "kind": e.kind, "year": e.year, "current_through": e.current_through,
            "through_law": f"{e.through_law[0]}-{e.through_law[1]}" if e.through_law else None, "url": e.url, "page": e.page,
            "sha256": e.sha256, "fetched_at": e.fetched_at, "sections": len(e.sections), "wayback": wayback(e.url),
        } for e in editions],
        "transitions": transitions,
        "laws": [{
            "pl": l.pl, "congress": l.congress, "number": l.number, "title": l.title, "short_title": l.short_title,
            "approved": l.approved, "bill": l.bill, "history": l.history, "affected": l.affected_sections.get(title, []),
            "url": l.url, "page": l.page, "sha256": l.sha256, "fetched_at": l.fetched_at, "wayback": wayback(l.page),
            "instructions": len(l.instructions), "unparsed": sum(1 for i in l.instructions if i.unparsed),
            "records": [r["id"] for r in records if r["law"] == l.pl],
            "summary": None,
        } for k, l in sorted(laws.items(), key=lambda kv: kv[1].approved) if l.pl in used],
        "counts": {"records": len(records), "by_status": by_status, "sections_changed": len({(r["section"], r["edition_to"]) for r in records})},
    }


def _write(out: Path, title: int, editions: list[Edition], meta: dict, records: list[dict], replays: list[dict] = ()) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "records.json").write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
    sections_dir = out / "sections"
    sections_dir.mkdir(exist_ok=True)
    numbers = sorted({n for e in editions for n in e.sections}, key=lambda n: (int(re.match(r"\d+", n).group()), n))
    index = []
    for number in numbers:
        versions = []
        for e in editions:
            s = e.sections.get(number)
            text = "\n".join(p.text for p in s.provisions) if s else ""
            sha = fingerprint(norm(text)) if s else None
            if versions and versions[-1]["sha256"] == sha:
                versions[-1]["editions"].append(e.key)
                continue
            versions.append({"editions": [e.key], "sha256": sha, "heading": s.heading if s else None,
                             "lines": [{"path": p.path, "level": p.level, "text": p.text} for p in s.provisions] if s else []})
        recs = [r for r in records if r["section"] == number]
        latest = editions[-1].sections.get(number)
        blame = _blame(number, editions, records, {e.key: n for n, e in enumerate(editions)})
        # The Code prints the statutory dollar amounts; the Judicial Conference adjusts them every three years by
        # notice under section 104. Readers need both, so the notices are listed with the section.
        adjustments = [{
            "notice": n.id, "citation": n.citation, "dated": n.dated, "effective": n.effective, "url": n.url,
            "changes": [{"path": i.path, "text": i.text} for i in n.instructions],
        } for n in (notices_in(latest, title) if latest else [])]
        adjustments.sort(key=lambda x: x["effective"], reverse=True)
        (sections_dir / f"{number}.json").write_text(json.dumps({
            "section": number, "heading": latest.heading if latest else (versions[-1]["heading"] if versions else ""),
            "source_credit": latest.source_credit if latest else "", "versions": versions, "records": [r["id"] for r in recs], "blame": blame,
            "adjustments": adjustments,
            # Where one version's change took several instructions: the section before them and after each one.
            "replays": [{k: v for k, v in r.items() if k != "section"} for r in replays if r["section"] == number],
        }, ensure_ascii=False), encoding="utf-8")
        index.append({"section": number, "heading": latest.heading if latest else "", "changes": len(recs), "repealed": bool(latest and latest.repealed)})
    (out / "sections.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def _blame(number: str, editions: list[Edition], records: list[dict], order: dict[str, int]) -> list[dict]:
    """For each provision in the latest edition, the last record that changed it within the editions covered."""
    latest = editions[-1].sections.get(number)
    if not latest:
        return []
    recs = sorted((r for r in records if r["section"] == number), key=lambda r: (order[r["edition_to"]], r["dates"].get("enacted") or ""))
    out = []
    for p in latest.provisions:
        hit = None
        for r in recs:
            rp = r["path"]
            if rp == "" or p.path == rp or p.path.startswith(rp + "(") or p.path.startswith(rp + " ") or p.path in r.get("mismatch", []):
                hit = r
        out.append({"path": p.path, "record": hit["id"] if hit else None, "law": hit["law"] if hit else None, "edition": hit["edition_to"] if hit else None})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", type=int, default=11)
    parser.add_argument("--from", dest="first", type=int, default=2017)
    parser.add_argument("--to", dest="last", type=int, default=2024)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / ".us_code_history" / "out")
    parser.add_argument("--summaries", action="store_true", help="write plain-English summaries with the model")
    parser.add_argument("--no-release-points", dest="release_points", action="store_false", help="compare annual editions only")
    args = parser.parse_args()
    meta = build(args.title, args.first, args.last, args.out / f"title{args.title}", summaries=args.summaries, release_points=args.release_points)
    print(json.dumps(meta["counts"], indent=1))


if __name__ == "__main__":
    main()
