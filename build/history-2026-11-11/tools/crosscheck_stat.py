"""Cross-checks a random sample of the reversed entries against the Statutes at Large (GovInfo STATUTE): for a note
"substituted "X" for "Y"", the amending law's own text should strike Y and insert X ("by striking "Y" and inserting
"X""). Downloads each sampled law's STATUTE granule PDF (paced), reads it with pdftotext, deletes it.

    python crosscheck_stat.py [sample size]
"""
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from build_block import Laws  # noqa: E402

UA = "Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)"
size = int(sys.argv[1]) if len(sys.argv) > 1 else 30
summary = json.loads((ROOT / "data" / "reverse1986-summary.json").read_text())
lawdb = Laws()
pool = [(n, a) for n, v in summary.items() if v["status"] == "full" for a in v["applied"]
        if a["kind"] == "substituted" and lawdb.db.get(a["law"], {}).get("stat") and len(a["old"]) + len(a["new"]) >= 4]
random.seed(1986)
sample = random.sample(pool, min(size, len(pool)))
work = ROOT / "probe" / "stat"
work.mkdir(parents=True, exist_ok=True)
vol_mods, texts = {}, {}


def get(url):
    for i in range(3):
        try:
            r = httpx.get(url, headers={"user-agent": UA}, timeout=180, follow_redirects=True)
            time.sleep(1.5)
            r.raise_for_status()
            return r.content
        except httpx.HTTPError:
            time.sleep(10)
    raise RuntimeError(url)


def law_text(pl):
    if pl in texts:
        return texts[pl]
    vol, page = (int(x) for x in lawdb.db[pl]["stat"].split(" Stat. "))
    if vol not in vol_mods:
        vol_mods[vol] = get(f"https://www.govinfo.gov/metadata/pkg/STATUTE-{vol}/mods.xml").decode("utf-8", "replace")
    gran = None
    for m in re.finditer(r'ID="id-(STATUTE-\d+-Pg(\d+))".*?<start>(\d+)</start>\s*<end>(\d+)</end>', vol_mods[vol], re.S):
        if int(m.group(3)) <= page <= int(m.group(4)):
            gran = m.group(1)
            break
    if not gran:
        texts[pl] = ""
        return ""
    cache = work / f"{gran}.txt"
    if cache.exists():
        txt = cache.read_text(encoding="utf-8")
    else:
        pdf = work / f"{gran}.pdf"
        pdf.write_bytes(get(f"https://www.govinfo.gov/content/pkg/STATUTE-{vol}/pdf/{gran}.pdf"))
        txt = subprocess.run(["pdftotext", "-q", str(pdf), "-"], capture_output=True).stdout.decode("utf-8", "replace")
        pdf.unlink()
        cache.write_text(txt, encoding="utf-8")
    t = re.sub(r"-\s*\n\s*", "", txt)
    t = t.replace("“", '"').replace("”", '"').replace("``", '"').replace("''", '"').replace("’", "'")
    texts[pl] = (gran, re.sub(r"\s+", " ", t))
    return texts[pl]


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


rows = []
for n, a in sample:
    got = law_text(a["law"])
    if not got:
        rows.append((n, a["law"], "law not found in STATUTE", a))
        continue
    gran, t = got
    old, new = norm(a["old"]), norm(a["new"])
    pat = re.escape(f'"{old}"') + r'.{0,60}?' + re.escape(f'"{new}"')
    loose = re.sub(r"[^a-z0-9]", "", t.lower())
    lo, ln = re.sub(r"[^a-z0-9]", "", old.lower()), re.sub(r"[^a-z0-9]", "", new.lower())
    near = any(loose.find(ln, i + len(lo), i + len(lo) + 400) >= 0 for i in [m.start() for m in re.finditer(re.escape(lo), loose)][:200]) if lo and ln else False
    if re.search(pat, t) or near:
        verdict = "confirmed: law strikes the old words and inserts the new"
    elif f'"{old}"' in t and f'"{new}"' in t:
        verdict = "both quoted in the law, not side by side"
    elif f'"{new}"' in t:
        verdict = "new words quoted in the law; old words not found as quoted"
    else:
        verdict = "not found in the law's text"
    rows.append((n, a["law"], verdict, a))
from collections import Counter
print(Counter(r[2] for r in rows))
for n, law, v, a in rows:
    print(f"26 USC {n} | Pub. L. {law} | {v} | old={a['old'][:40]!r} new={a['new'][:40]!r}")
(ROOT / "data" / "crosscheck-stat.json").write_text(json.dumps([{"section": n, "law": l, "verdict": v, "old": a["old"], "new": a["new"]} for n, l, v, a in rows], indent=1))
