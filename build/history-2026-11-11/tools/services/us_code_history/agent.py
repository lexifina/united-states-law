"""Plain-English summaries, and cause proposals for anything the replay cannot explain.

The model only describes what the evidence already shows. Every summary is checked before it is kept: each number,
dollar amount and quotation in it must appear in the record's before text, after text or the law's instruction, and
each record it cites must exist. A summary that fails the check is replaced by a sentence written from the replayed
operations, so nothing published depends on the model being right.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

STYLE = (
    "Write in plain English for lawyers and the public. Short, direct sentences. Describe only what changed and what "
    "the law did; never give advice, never speculate about reasons, and never use rhetorical questions. Use the "
    "provision references exactly as given, such as \"section 101(51D)(B)(i)\"."
)


# Model calls at a time while summarising one title.
PARALLEL = 4


def _client():
    from services.model_registry.catalog import SIZE_STANDARD
    from services.model_registry.secondary import secondary_sync_client

    return secondary_sync_client("us_code_history_summary", SIZE_STANDARD)


def _ask(prompt: str, max_tokens: int = 1200) -> Optional[str]:
    from services.ai_compute_metering import collect_ai_usage

    try:
        # A site build job, not a user's request: usage is collected under its own surface.
        with collect_ai_usage("us_code_history"):
            response = _client().chat.completions.create(
                messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.1, timeout=90
            )
        return (response.choices[0].message.content or "").strip()
    except Exception as error:  # noqa: BLE001 - the rule-written sentence stands in
        logger.warning("US Code history model call failed: %s", error)
        return None


def _json(text: Optional[str]):
    if not text:
        return None
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _ref(r: dict) -> str:
    return f"section {r['section']}{r['path']}" if r.get("path") else f"section {r['section']}"


def rule_summary(r: dict) -> str:
    """A sentence written from the replayed operations alone."""
    ops = (r.get("instruction") or {}).get("ops") or []
    where = _ref(r)
    kinds = {o["kind"] for o in ops}
    if r["kind"] == "added" and not r.get("before"):
        return f"Added {where}."
    if r["kind"] == "sunset":
        return f"Ended the temporary change to {where}, as the law had scheduled."
    if r["kind"] == "restored":
        return f"Restored {where} to its earlier wording, as the law had scheduled."
    for o in ops:
        if o["kind"] in ("replace", "replace_all"):
            return f"In {where}, replaced “{o['old']}” with “{o['new']}”{' each time it appears' if o['kind'] == 'replace_all' else ''}."
        if o["kind"] == "insert_after":
            return f"In {where}, inserted “{o['new']}” after “{o['anchor']}”."
        if o["kind"] in ("delete", "delete_all"):
            return f"In {where}, struck “{o['old']}”."
    if kinds & {"replace_block", "replace_provision"}:
        return f"Rewrote {where}."
    if "append_block" in kinds:
        return f"Added new provisions at the end of {where}."
    if kinds & {"insert_block_after", "insert_block_before"}:
        return f"Inserted new provisions in {where}."
    if "delete_provision" in kinds:
        return f"Struck provisions from {where}."
    if "redesignate" in kinds:
        return f"Renumbered provisions in {where}."
    return f"Amended {where}."


def _listing(numbers: list[str]) -> str:
    """"101, 103 and 1181 to 1195": runs of three or more consecutive section numbers are joined with "to"."""
    groups: list[list[str]] = []
    for n in numbers:
        if groups and n.isdigit() and groups[-1][-1].isdigit() and int(n) == int(groups[-1][-1]) + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    parts: list[str] = []
    for g in groups:
        parts.extend([f"{g[0]} to {g[-1]}"] if len(g) >= 3 else g)
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def law_rule_summary(law: dict, recs: list[dict]) -> str:
    """"Made 40 changes to title 11: added sections 1181 to 1195 and changed sections 101 and 103." from the records alone."""
    key = lambda s: (int(re.match(r"\d+", s).group()), s)
    added = sorted({r["section"] for r in recs if r["kind"] == "added" and not r.get("path")}, key=key)
    changed = sorted({r["section"] for r in recs} - set(added), key=key)
    ended = sum(1 for r in recs if r["kind"] in ("sunset", "restored"))
    parts = []
    if added:
        parts.append(f"added section{'s' if len(added) > 1 else ''} {_listing(added)}")
    if changed:
        parts.append(f"changed section{'s' if len(changed) > 1 else ''} {_listing(changed)}")
    title = recs[0].get("title", 11) if recs else 11
    text = f"Made {len(recs)} change{'s' if len(recs) != 1 else ''} to title {title}: {' and '.join(parts)}."
    if ended:
        text += f" {ended} of the changes ended temporary provisions on the dates the law set."
    return text


_ACT = re.compile(r"\b((?:[A-Z][A-Za-z.'’-]*\s+){1,10}Act(?:\s+of\s+\d{4})?)")


def _grounded(summary: str, evidence: str, cited: list[str], known: set[str], title: Optional[int] = None) -> bool:
    """Every figure, quotation and named Act in the summary must come from the evidence; a title it names must be the
    record's own title or one the evidence names; every cited record must exist."""
    if re.search(r"\bthis Act\b", summary):
        return False  # "this Act" is ambiguous outside the law's own text
    ev = evidence.replace("“", '"').replace("”", '"') + (f" title {title}" if title is not None else "")
    lower = ev.lower()
    for act in _ACT.findall(summary):
        name = re.sub(r"^(?:The|the|A|An)\s+", "", act.strip())
        if name.lower() not in lower:
            return False
    if title is not None:
        for n in re.findall(r"\btitle (\d+)\b", summary):
            if int(n) != title and f"title {n}" not in lower:
                return False
    for number in re.findall(r"\$?\d[\d,]*(?:\.\d+)?", summary):
        if number.strip("$") not in ev:
            return False
    for quote in re.findall(r"[“\"]([^”\"]{3,})[”\"]", summary):
        if quote not in ev:
            return False
    return all(c in known for c in cited)


def evidence_key(r: dict) -> str:
    """Fingerprint of what a record's summary is written from; a summary is reused only while this is unchanged."""
    return hashlib.sha256(json.dumps([r.get("title"), r["kind"], _ref(r), r["before"], r["in_edition"], r.get("law")], ensure_ascii=False).encode()).hexdigest()


def law_key(law: dict, recs: list[dict]) -> str:
    return hashlib.sha256(json.dumps([law["pl"], recs[0].get("title") if recs else None, [(r["id"], r["summary"]) for r in recs]], ensure_ascii=False).encode()).hexdigest()


def summarise(meta: dict, records: list[dict], batch: int = 8, previous: Optional[dict] = None) -> None:
    """Write summaries, reusing checked ones from ``previous`` ({"records": [...], "laws": [...]}) whose evidence is unchanged."""
    by_id = {r["id"]: r for r in records}
    names = {l["pl"]: l.get("short_title") or l.get("title") or "" for l in meta["laws"]}
    title = meta.get("title")
    prev_records = {p["id"]: p for p in (previous or {}).get("records", []) if p.get("summary_source") == "model, checked"}
    prev_laws = {p["pl"]: p for p in (previous or {}).get("laws", []) if p.get("summary_source") == "model, checked"}
    todo = []
    for r in records:
        r["summary_key"] = evidence_key(r)
        p = prev_records.get(r["id"])
        if p and p.get("summary_key") == r["summary_key"]:
            r["summary"], r["summary_source"] = p["summary"], p["summary_source"]
            continue
        r["summary"] = rule_summary(r)
        r["summary_source"] = "rule"
        todo.append(r)
    # The model calls are independent, so they run several at a time; answers are applied in order afterwards.
    def ask_chunk(chunk: list[dict]) -> Optional[str]:
        items = [{
            "id": r["id"], "where": f"{_ref(r)} of title {title}", "kind": r["kind"],
            "law": f"{names.get(r.get('law') or '', '')} (Public Law {r.get('law')})" if r.get("law") else None,
            "before": r["before"][:1500], "after": r["in_edition"][:1500],
            "instruction": ((r.get("instruction") or {}).get("text") or "")[:800],
        } for r in chunk]
        prompt = (
            f"{STYLE}\n\nFor each change below, write one sentence (at most 35 words) saying what changed. Start with a "
            "past-tense verb (Added, Inserted, Replaced, Rewrote, Struck, Renumbered, Raised, Ended) and name the "
            "provision, for example: \"Inserted 'under this title' after 'affiliated debtors' in section 101(51D)(B)(i).\" "
            "For kind \"sunset\", say the temporary change ended as the law had scheduled. For kind \"restored\", say the earlier text was restored and give the date. Never write \"this Act\". Name no law other than the one given for the change, and no title other than the one given. Quote words only if they "
            "appear in the before or after text. Return JSON: [{\"id\": ..., \"summary\": ...}].\n\n"
            + json.dumps(items, ensure_ascii=False)
        )
        return _ask(prompt)

    chunks = [todo[start: start + batch] for start in range(0, len(todo), batch)]
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        replies = list(pool.map(ask_chunk, chunks))
    for reply in replies:
        answer = _json(reply)
        # The model can return a list of something other than objects, or an id it was not given; skip those.
        for item in answer if isinstance(answer, list) else []:
            r = by_id.get(item.get("id") if isinstance(item, dict) else None)
            text = (item.get("summary") or "").strip() if isinstance(item, dict) and isinstance(item.get("summary"), str) else ""
            if not r or not text:
                continue
            evidence = " ".join([r["before"], r["in_edition"], (r.get("instruction") or {}).get("text") or "", names.get(r.get("law") or "", "")])
            if r and text and _grounded(text, evidence, [], set(), title):
                r["summary"], r["summary_source"] = text, "model, checked"
    known = set(by_id)
    asks: list[tuple[dict, list[dict], str]] = []
    for law in meta["laws"]:
        recs = [by_id[i] for i in law["records"] if i in by_id]
        if not recs:
            continue
        law["summary_key"] = law_key(law, recs)
        p = prev_laws.get(law["pl"])
        if p and p.get("summary_key") == law["summary_key"]:
            law["summary"], law["summary_source"] = p["summary"], p["summary_source"]
            continue
        law["summary"], law["summary_source"] = law_rule_summary(law, recs), "rule"
        items = [{"id": r["id"], "where": _ref(r), "kind": r["kind"], "summary": r["summary"]} for r in recs[:60]]
        asks.append((law, recs, (
            f"{STYLE}\n\n{law['short_title'] or law['title']} (Public Law {law['pl']}, enacted {law['approved']}) made the "
            f"changes below to title {title} of the US Code. Write two or three sentences saying what the law did to title {title}, "
            "citing the changes you mention by id in square brackets, like [2022-117-151-101-4]. Return JSON: "
            '{"summary": ...}.\n\n' + json.dumps(items, ensure_ascii=False)
        )))
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        law_replies = list(pool.map(lambda a: _ask(a[2], 600), asks))
    for (law, recs, _), reply in zip(asks, law_replies):
        answer = _json(reply)
        text = (answer or {}).get("summary") if isinstance(answer, dict) else None
        if text:
            cited = re.findall(r"\[([0-9a-z\-]+)\]", text)
            evidence = " ".join(r["before"] + " " + r["in_edition"] + " " + r["summary"] for r in recs) + f" {law['pl']} {law['approved']} {law['short_title'] or ''} {law['title']}"
            if cited and _grounded(re.sub(r"\[[^\]]+\]", "", text), evidence, cited, known, title):
                law["summary"] = text
                law["summary_source"] = "model, checked"


def propose_causes(records: list[dict], laws: dict) -> None:
    """For changes the replay could not explain: ask the model which candidate law most likely made the change, quoting
    the instruction. The proposal is published as a proposal, never as a confirmed cause."""
    for r in records:
        if r["status"] not in ("unexplained", "publisher's note only"):
            continue
        candidates = []
        for pl in r.get("candidate_laws") or []:
            law = laws.get(pl)
            if not law:
                continue
            for i in law.instructions:
                if i.section == r["section"]:
                    candidates.append({"law": pl, "label": i.label, "text": i.text[:600]})
        if not candidates:
            continue
        prompt = (
            f"{STYLE}\n\nThis change to section {r['section']}{r['path']} of title {r.get('title', 11)} could not be reproduced automatically.\n"
            f"Before: {r['before'][:1500]}\nAfter: {r['in_edition'][:1500]}\nPublisher's notes: {json.dumps(r['publisher_notes'])[:1500]}\n"
            f"Candidate instructions: {json.dumps(candidates[:20], ensure_ascii=False)}\n"
            'Which instruction most likely made this change? Return JSON {"law": ..., "label": ..., "reason": one sentence}.'
        )
        answer = _json(_ask(prompt, 300))
        if isinstance(answer, dict) and any(c["law"] == answer.get("law") and c["label"] == answer.get("label") for c in candidates):
            r["proposed_cause"] = {**answer, "source": "model, unverified"}
