"""How much of title 26 (1994 edition) could be taken back to the 1986 Code by reversing the amendment notes.

Counts, per section, the amendment-note entries for laws enacted after Pub. L. 99-514 (October 22, 1986) and before
the 1994 edition's cutoff, and classifies each by whether its words give what reversing it needs:
  reversible  substituted "X" for "Y" / inserted "X" (after/before "Y") / struck out "X" / redesignated / added X with
              the new text in the current edition (reverse = remove) / amended ... generally with the prior text quoted
  lossy       struck out (or amended generally / substituted for) a provision without quoting what it said
A section is "full" when all its entries are reversible, "partial" when some are, "none" when it has entries and none
is, "unamended" when no law after 99-514 amended it (its 1994 text is its 1986 text, as far as the notes say).
"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_block import Laws, amend_entries, straight  # noqa: E402

ROOT = HERE.parent
ed = json.load(gzip.open(ROOT / "data" / "title26" / "1994.json.gz", "rt", encoding="utf-8"))
lawdb = Laws()
for s in ed["sections"].values():
    lawdb.note_credit(s.get("source_credit", ""))

Q = r'"[^"]+"'
REV = [
    re.compile(rf"\bsubstituted {Q} for {Q}", re.I),
    re.compile(rf"\binserted {Q}", re.I),
    re.compile(rf"\bstruck out {Q}", re.I),
    re.compile(r"\bredesignated\b", re.I),
    re.compile(r"\badded (?:subsecs?|pars?|subpars?|cls?|subcls?|items?)\b", re.I),
    re.compile(r"\badded (?:at the end|after)\b", re.I),
]
LOSSY = re.compile(r"\b(struck out|amended .* generally|substituted .* for (?:former|subsec|par|subpar|cl|provisions))", re.I)
PRIOR = re.compile(r"(read as follows|Prior to amendment)", re.I)


def after_1986(pl: str) -> bool:
    c, n = (int(x) for x in pl.split("-"))
    if c > 99:
        return True
    if c < 99:
        return False
    d = lawdb.enacted(pl)
    return bool(d and d > "1986-10-22")


def kind(text: str) -> str:
    t = straight(text)
    if PRIOR.search(t):
        return "reversible"            # the prior text is quoted in the note
    if any(r.search(t) for r in REV) and not re.search(r"\bstruck out (?:subsecs?|pars?|subpars?|cls?|subcls?|items?)\b", t, re.I):
        return "reversible"
    if LOSSY.search(t):
        return "lossy"
    return "unclear"


per_section = Counter()
entries = Counter()
examples = {}
for n, s in ed["sections"].items():
    if not s["lines"]:
        continue
    ks = []
    for e in amend_entries(s):
        if not e.laws or not after_1986(e.laws[0].pl):
            continue
        k = kind(e.text)
        ks.append(k)
        entries[k] += 1
        examples.setdefault(k, []).append(e.text[:200]) if len(examples.get(k, [])) < 4 else None
    if not ks:
        per_section["unamended since 99-514"] += 1
    elif all(k == "reversible" for k in ks):
        per_section["fully reversible"] += 1
    elif any(k == "reversible" for k in ks):
        per_section["partly"] += 1
    else:
        per_section["not reversible"] += 1
print("sections with text in the 1994 edition:", sum(per_section.values()))
for k, v in per_section.most_common():
    print(f"  {k:28} {v}")
print("entries after 99-514:", sum(entries.values()), dict(entries))
for k, xs in examples.items():
    print("--", k)
    for x in xs:
        print("   ", x)
