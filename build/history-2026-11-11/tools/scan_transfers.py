"""How many sections the pre-2017 blocks credit as "Added" by a law when the edition says the section was moved in
editorially ("formerly classified to section ... of title ..."): scans the blocks' law commits."""
import gzip
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMER = re.compile(r"(formerly classified to|was classified to|transferred to this|editorially reclassified|transferred from)", re.I)
per_title = Counter()
lines_total = Counter()
examples = []
for f in sorted((ROOT / "blocks").glob("title*.json.gz"), key=lambda p: int(re.search(r"\d+", p.name).group())):
    t = int(re.search(r"\d+", f.name).group())
    commits = json.load(gzip.open(f, "rt", encoding="utf-8"))
    eds = {}
    for c in commits:
        if not c["email"].startswith("pl-"):
            continue
        year = int(re.search(r"Printed-in: (\d{4})", c["message"]).group(1))
        if year not in eds:
            p = ROOT / "data" / f"title{t}" / f"{year}.json.gz"
            eds[year] = json.load(gzip.open(p, "rt", encoding="utf-8"))["sections"] if p.exists() else {}
        for m in re.finditer(rf"^{t} U\.S\.C\. §(\S+)\. Added\.", c["message"], re.M):
            n = m.group(1)
            sec = eds[year].get(n, {})
            notes = " ".join(" ".join(v) for v in sec.get("notes", {}).values())
            if FORMER.search(notes):
                per_title[t] += 1
                text = c["files"].get(f"title-{t}/{n}.md") or ""
                lines_total[t] += text.count("\n")
                if len(examples) < 5:
                    examples.append((t, n, c["author"], c["date"]))
print("sections credited as Added by a law although the edition says they were moved in:", sum(per_title.values()))
print("lines in them:", sum(lines_total.values()))
print(dict(sorted(per_title.items())))
for e in examples:
    print(" ", e)
