"""Adds the documentation commit for the record before 1994 on top of branch history-pre1994 in ./clone.

    python docs_pre.py <title> [<title> ...]

Writes README.md (section "Before 1994"), CHANGES.md (entry), REPRODUCE.md (section), corpus.json (history_from,
record_note, history_rewritten) and build/history-pre1994/ (scripts, per-title reports, the LoC PDFs read with their
SHA-256, old-to-new.tsv), as one commit by Lexifina dated now. Uses a temporary index: nothing is checked out.
"""
from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLONE = os.path.join(ROOT, "clone")
BR = "history-pre1994"
WHO = "Lexifina <us-code-history@lexifina.com>"
TODAY = time.strftime("%Y-%m-%d")


def git(*a, input=None, env=None) -> bytes:
    return subprocess.run(["git", *a], cwd=CLONE, input=input, capture_output=True, check=True,
                          env={**os.environ, **(env or {})}).stdout


def show(path: str) -> str:
    return git("show", f"{BR}:{path}").decode("utf-8")


def titles_phrase(ts: list[int]) -> str:
    ts = sorted(ts)
    return f"title {ts[0]}" if len(ts) == 1 else "titles " + ", ".join(map(str, ts[:-1])) + f" and {ts[-1]}"


def main() -> None:
    titles = [int(t) for t in sys.argv[1:]]
    tp = titles_phrase(titles)
    reports = {t: json.load(open(os.path.join(ROOT, "blocks", f"title{t}.report.json"), encoding="utf-8")) for t in titles}
    ncommits = sum(len(json.load(gzip.open(os.path.join(ROOT, "blocks", f"title{t}.json.gz"), "rt", encoding="utf-8")))
                   for t in titles)
    law_changes = sum(p["law"] for r in reports.values() for p in r["pairs"])
    ed_changes = sum(p["edition"] for r in reports.values() for p in r["pairs"])
    old_head = git("rev-parse", "--short=7", "origin/main").decode().strip()
    files: dict[str, bytes] = {}

    # ---- README ----
    readme = show("README.md")
    section = f"""## Before 1994: the printed editions from 1926

Since {TODAY} the history of {tp} starts earlier still, with the first edition of the Code itself: **the Code of Laws of
the United States of 1926** (laws in force December 7, 1925), then every main edition the Library of Congress has
scanned (1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982 and 1988), up to the 1994 edition where GovInfo's record
begins. The other titles still start in 1994; they will be put in front the same way as their scans are read.

- **Source.** The Library of Congress's scans of the printed editions, one PDF per chapter
  (`https://tile.loc.gov/storage-services/service/ll/uscode/...`); `build/history-pre1994/sources.tsv` lists every PDF
  read, with its SHA-256.
- **The words are OCR, checked twice.** Each page is read by Tesseract 5, by docTR on a GPU where it ran, and the PDF's
  own text layer is the second, independent reading. Each edition is then compared with the next one, newest first,
  starting from GovInfo's clean 1994 text: where the readings agree with the next edition's words, allowing for
  misread letters, the next edition's clean words, punctuation and layout are used; a difference is kept only where two
  readings show it, and only short substitutions survive where the next edition names no new law for the section. So
  the text changes only where the scans say it did. A section no later edition prints (repealed or renumbered before
  1994) keeps its OCR reading and can contain misread words.
- **Credit and dates** follow the record from 1994: a change between two editions goes to the law the newer edition
  names for the section and the older did not (source credit or amendment notes), dated the day the law was enacted
  (the day after the older edition's cutoff if it was enacted before it); changes no law could be matched to are
  "Printed text differs" commits under the newer edition. Acts before public-law numbers (1957) are authors by date and
  chapter, "Act of July 30, 1947, ch. 388", with trailers `Law:`, `Enacted:`, `In-force:`, `Printed-in:` and
  `Statutes-at-Large:`, and tags `law/act-<date>-ch<n>`. Where a law re-enacted a title (title 1 by the Act of July 30,
  1947), the sections the old numbering had are credited as removed by it.
- **Dates before 1970.** Git cannot store them: those commits show 1 January 1970 (one second apart, in order) and the
  `In-force:` trailer has the real day, as in every Lexifina law repository. Read by that trailer (global-law's
  `tools/law.py` and its MCP server do), not by `git log --before`.
- **Coverage gaps.** A section printed in the editions on either side of one it is missing from, with no law removing
  it, is kept through that edition (the OCR missed its start). The 1926 Code prints no source-credit notes for many
  sections, so changes between 1926 and 1934 are credited less often.

Numbers for this addition: {ncommits} commits; {law_changes} section changes credited to a law, {ed_changes} to an
edition. Per title, per pair of editions: `build/history-pre1994/reports/`.

"""
    readme = readme.replace("## Before 2017: the annual editions from 1994", section + "## Before 2017: the annual editions from 1994", 1)
    files["README.md"] = readme.encode("utf-8")

    # ---- CHANGES ----
    ch = show("CHANGES.md")
    entry = f"""## {TODAY[8:].lstrip('0')} November 2026 (evening): {tp} from 1926

**The history was rewritten once more** (the owner's decision), to put the record before 1994 in front of {tp}: every
edition of the Code from the Code of Laws of the United States of 1926 to the 1988 edition, read from the Library of
Congress scans by OCR and checked against the next edition (README, "Before 1994"). Every commit hash changed; the
final text is unchanged (same tree). The previous main is the branch `archive/main-before-pre1994-{TODAY}`
(`{old_head}`); `build/history-pre1994/old-to-new.tsv` maps its commits to these. Tags moved with their commits; law
tags were added for the Acts before 1957 (`law/act-<date>-ch<n>`). Commits before 1970 show 1 January 1970: read the
`In-force:` trailer.

{ncommits} commits; {law_changes} section changes credited to a law, {ed_changes} to an edition. The other titles will be
put in front the same way as their scans are read (each time a rewrite, announced here).

"""
    ch = ch.replace("## 11 November 2026: corrections, and title 26 from 1986", entry + "## 11 November 2026: corrections, and title 26 from 1986", 1)
    files["CHANGES.md"] = ch.encode("utf-8")

    # ---- REPRODUCE ----
    rp = show("REPRODUCE.md")
    rp += f"""

## Record before 1994, added on {TODAY}: {tp}

- **Sources.** Library of Congress scans of the US Code main editions 1926 (laws in force December 7, 1925) to 1988,
  `https://tile.loc.gov/storage-services/service/ll/uscode/uscode<Y>-<VVVTT>/uscode<Y>-<VVVTTTCCC>/uscode<Y>-<VVVTTTCCC>.pdf`
  (volume, title, chunk), retrieved {TODAY}, one request at a time (www.loc.gov answers automated clients with a
  challenge and was not used). Every PDF read and its SHA-256: `build/history-pre1994/sources.tsv`. The 1994 (1995 for
  titles 7, 28 and 39) GovInfo editions as in "History before 2017".
- **Software.** Python 3.12, PyMuPDF, Tesseract 5.4.0 (eng, LSTM, page segmentation 3, at the scan's resolution),
  OnnxTR (docTR db_resnet50 + parseq) on onnxruntime-gpu; scripts in `build/history-pre1994/scripts/`.
- **Steps.** `fetch2.py` (download), `ocr.py` / `ocr_gpu.py` (OCR; the PDF's own text layer is kept too), `parse_ocr.py
  <year> <title>` (sections, source credits, notes), `clean.py <title> <year> <next> [later...]` (newest edition first,
  anchored on GovInfo's), `build_pre.py <title>` (commits; checks that the block ends at exactly the 1994 text),
  `assemble_pre.py <titles>` (the blocks, then the previous main replayed with the same authors, dates, messages and
  file blobs; each title's "1994 edition: the start of this record" commit, which the block makes empty, is folded;
  checks the final tree equals the previous main's), `docs_pre.py`. OCR output can differ slightly between Tesseract
  versions; the checksums of the inputs and the per-title reports pin what this history was built from.
- **AI.** These scripts were written by Claude Code (Claude Opus 5.5, `claude-opus-5-5`). No model wrote or edited any
  legal text or commit message: the OCR engines read the scans, and every word, date and law in the commits comes from
  the scans, GovInfo's 1994 edition, and rules in the scripts.
"""
    files["REPRODUCE.md"] = rp.encode("utf-8")

    # ---- corpus.json ----
    cj = json.loads(show("corpus.json"))
    cj["history_from"] = "1925-12-07"
    cj["record_note"] = (f"{tp[0].upper() + tp[1:]} from the Code of Laws of the United States of 1926 (laws in force December 7, 1925) "
                         f"through every main edition to 1988, read from the Library of Congress scans by OCR and checked against "
                         f"the next edition (added {TODAY}); commits before 1970 are dated 1970-01-01 in git, the In-force "
                         f"trailer has the day. " + cj["record_note"])
    old_to_new = {}
    for line in open(os.path.join(ROOT, "scratch", "old-to-new.tsv"), encoding="utf-8"):
        o, n = line.rstrip("\n").split("\t")
        old_to_new[o] = n
    for eb in cj.get("end_blocks", []):
        for k in ("first", "after"):
            full = next((o for o in old_to_new if o.startswith(eb[k])), None)
            if full and not old_to_new[full].startswith("("):
                eb[k] = old_to_new[full][:7]
    cj.setdefault("history_rewritten", []).append({
        "date": TODAY, "reason": f"the record before 1994 for {tp} put in front of the history (owner's decision)",
        "previous_head": old_head, "previous_branch": f"archive/main-before-pre1994-{TODAY}",
        "map": "build/history-pre1994/old-to-new.tsv", "tree_unchanged": git("rev-parse", "origin/main^{tree}").decode().strip()})
    files["corpus.json"] = (json.dumps(cj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    # ---- build/history-pre1994 ----
    base = "build/history-pre1994/"
    for f in ("fetch2.py", "ocr.py", "ocr_gpu.py", "parse_ocr.py", "clean.py", "build_pre.py", "assemble_pre.py",
              "run_all.py", "docs_pre.py"):
        files[base + "scripts/" + f] = open(os.path.join(ROOT, "scripts", f), "rb").read()
    for t in titles:
        files[base + f"reports/title{t}.report.json"] = open(os.path.join(ROOT, "blocks", f"title{t}.report.json"), "rb").read()
    rows = ["year\tpdf\turl\tsha256\tbytes"]
    for t in titles:
        for p in sorted(glob.glob(os.path.join(ROOT, "cache", "*", f"uscode*-???{t:03d}???.pdf"))):
            stem = os.path.basename(p)[:-4]
            y = stem[6:10]
            data = open(p, "rb").read()
            url = f"https://tile.loc.gov/storage-services/service/ll/uscode/{stem[:16]}/{stem}/{stem}.pdf"
            rows.append(f"{y}\t{stem}.pdf\t{url}\t{hashlib.sha256(data).hexdigest()}\t{len(data)}")
    files[base + "sources.tsv"] = ("\n".join(rows) + "\n").encode("utf-8")
    files[base + "old-to-new.tsv"] = open(os.path.join(ROOT, "scratch", "old-to-new.tsv"), "rb").read()

    # ---- commit with a temporary index ----
    idx = os.path.join(ROOT, "scratch", "docs.index")
    if os.path.exists(idx):
        os.remove(idx)
    env = {"GIT_INDEX_FILE": idx}
    git("read-tree", BR, env=env)
    for path, data in files.items():
        sha = git("hash-object", "-w", "--stdin", input=data).decode().strip()
        git("update-index", "--add", "--cacheinfo", f"100644,{sha},{path}", env=env)
    tree = git("write-tree", env=env).decode().strip()
    msg = f"README, CHANGES, REPRODUCE, corpus.json: {tp} from 1926\n"
    now = str(int(time.time())) + " +0000"
    commit = git("commit-tree", tree, "-p", BR, "-m", msg, env={
        "GIT_AUTHOR_NAME": "Lexifina", "GIT_AUTHOR_EMAIL": "us-code-history@lexifina.com", "GIT_AUTHOR_DATE": now,
        "GIT_COMMITTER_NAME": "Lexifina", "GIT_COMMITTER_EMAIL": "us-code-history@lexifina.com", "GIT_COMMITTER_DATE": now}).decode().strip()
    git("update-ref", f"refs/heads/{BR}", commit)
    print("docs commit", commit[:9], "files", len(files))


if __name__ == "__main__":
    main()
