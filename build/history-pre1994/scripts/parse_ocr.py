"""Parses the OCR text of one LoC US Code edition into sections, per title.

    python parse_ocr.py <year> [<title> ...]

Reads text/<Y>/<id>.{tess,lura}.txt and the PDFs' metadata (subject: edition, title, chapter, sections); writes
parsed/<Y>/title<T>.json.gz: {"year", "title", "files": [{id, subject, pages}], "appendix_files": [...],
"sections": {num: sec}, "lura": {num: sec}} with sec = {"num", "heading", "paras", "credit", "notes": [[HEAD,
[paras]]], "status", "file", "page"}.

Section starts:
  1934-1988: a paragraph "§ <num>. <Heading>" (§ may be read as S, $, §§ for ranges).
  1925 (the 1926 Code): "Section <num>, <Heading>.—<text>" for a chapter's first section, then "<num>. <Heading>.—<text>".
Running heads (Page N, TITLE N—NAME, a lone "§ 25b") are dropped; a paragraph split by a page or column break is
joined again. Section numbers rise through a file: a lower number is a cross-reference or a misread one. Neighbouring
chapter PDFs share their boundary page, so a section can be read twice: the longer reading is kept.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NUM = r"((?:\d|[lI](?=[\dlI]))(?:[\dlIO]{0,3})[a-zA-Z]{0,4}(?:[-–][\dlI]+[a-zA-Z]?)?(?:\s*(?:to|and)\s*\d{1,4}[a-zA-Z\-\d]*)*)"
SEC = re.compile(r"""^(?:§§?|SS?|\$\$?|§ ?§|8\s(?=[\dlI]))\s*""" + NUM + r"""\s*[.,]\s*([A-Z“"'\[(].*|)$""")
SEC1925 = re.compile(r"""^(?:Section|Sec\.|Secrion|SECTION)?\s*""" + NUM + r"""[.,]\s+([A-Z“"'\[(][^—]{1,300}?)(?:[.,;:]?\s*[—–]+|\.\s*-{1,2})\s*(.*)$""")
RUNNING = [re.compile(p) for p in (
    r"^Page\s+\d+$", r"^\d{1,5}$", r"^TITLE\s+\d+\s*[\-—–.]+.*$", r"^§§?\s*\d+[a-zA-Z\-\d]*(\s+(to|-)\s*\d+[a-zA-Z\-\d]*)?\s*$",
    r"^Page\s+\d+\s+TITLE.*$", r"^TITLE\s+\d+.*Page\s+\d+$", r"^\d+\s+TITLE\s+\d+.*$", r"^TITLE\s+\d+.*\s\d+$",
)]
STATUS = re.compile(r"^(Repealed|Omitted|Transferred|Renumbered|Reserved|Vacant|Expired|Terminated)\b", re.I)
CHAPTER = re.compile(r"^(CHAPTER|Chapter|SUBCHAPTER|Subchapter|PART|Part)\s+[\dIVXLC]+[A-Z]?\b")
CREDIT_START = r"\((?:R\.\s*S\.|[A-Z][a-z]{2,4}\.?\s+\d{1,2},\s+\d{4}|Pub\.\s*L\.|As amended)"
TRAILING_CREDIT = re.compile(r"\s*(" + CREDIT_START + r"[^()]*(?:\([^()]*\)[^()]*)*\.?\s*\))\s*$")
NOTE_HEAD = re.compile(r"^([A-Z][A-Z0-9 ,;:'’&\-—–.()]{3,80}[A-Z)])\s+(?=[A-Z“\"(][a-z0-9])")


def subject_of(year: int, stem: str) -> tuple[str, int]:
    import pymupdf
    p = os.path.join(ROOT, "cache", str(year), stem + ".pdf")
    try:
        d = pymupdf.open(p)
        s, n = (d.metadata or {}).get("subject") or "", d.page_count
        d.close()
        return s, n
    except Exception:
        return "", 0


def is_heading_note(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 90 or (s.endswith((".", ",", ";", ":")) and not s.endswith("ETC.")):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.7


def paragraphs(text: str, starts) -> list[tuple[int, str]]:
    """(page, paragraph): page breaks, running heads removed, paragraphs cut by a page or column break joined,
    hyphenated line ends joined. `starts` matches a line that must begin a paragraph (a section start)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[list] = []
    for pno, page in enumerate(text.split("\f")):
        lines_all = page.split("\n")
        block: list[str] = []
        for raw in lines_all + [""]:
            l = raw.strip()
            if l and any(r.match(l) for r in RUNNING):
                continue
            if not l or (starts(l) and block):
                if block:
                    out.append([pno, block])
                block = [l] if l else []
                continue
            block.append(l)
    merged: list[list] = []
    for pno, lines in out:
        if merged:
            prev = merged[-1][1]
            last, first = prev[-1], lines[0]
            if (last.endswith("-") or not re.search(r"[.;:—)\]\"”]$", last)) and first[:1].islower() and not starts(first):
                prev.extend(lines)
                continue
            # a parenthesis left open ("(R. S." ... "§ 7.)"): the same paragraph, cut by the layout
            joined = " ".join(prev)
            if joined.count("(") > joined.count(")") and ")" in first[:40] and not starts(first):
                prev.extend(lines)
                continue
        merged.append([pno, lines])
    res = []
    for pno, lines in merged:
        s = ""
        for l in lines:
            if s.endswith("-") and l[:1].islower():
                s = s[:-1] + l
            elif not s or s.endswith(("—", "–")):
                s = s + l
            else:
                s = s + " " + l
        res.append((pno, s))
    return res


def norm_num(num: str) -> str:
    """OCR reads 1 as l or I and 0 as O inside section numbers ("lla" for 11a, "1O1" for 101)."""
    m = re.match(r"([\dlIO]+)(.*)$", num)
    if not m:
        return num
    head = m.group(1).replace("l", "1").replace("I", "1").replace("O", "0")
    tail = re.sub(r"(?<=[-–])[lI]", "1", m.group(2))
    return head + tail


def lis(keys: list) -> set[int]:
    """Indexes of a longest strictly increasing subsequence."""
    import bisect
    tails, tails_i, prev = [], [], [-1] * len(keys)
    for i, k in enumerate(keys):
        j = bisect.bisect_left(tails, k)
        if j == len(tails):
            tails.append(k); tails_i.append(i)
        else:
            tails[j] = k; tails_i[j] = i
        prev[i] = tails_i[j - 1] if j > 0 else -1
    out, i = set(), (tails_i[-1] if tails_i else -1)
    while i >= 0:
        out.add(i); i = prev[i]
    return out


def sec_order(num: str):
    m = re.match(r"(\d+)([a-zA-Z]*)(?:-(\d+))?", num)
    if not m:
        return (0, "", 0)
    return (int(m.group(1)), m.group(2).lower(), int(m.group(3) or 0))


def parse_text(text: str, file_id: str, year: int) -> dict:
    secs: dict[str, dict] = {}
    cur = None
    last, rejects = (0, "", 0), 0
    if year == 1925:
        starts = lambda l: bool(SEC1925.match(l))
    else:
        starts = lambda l: bool(SEC.match(l))
    paras = paragraphs(text, starts)
    cands = []
    for idx, (pno, para) in enumerate(paras):
        m = SEC1925.match(para) if year == 1925 else SEC.match(para)
        if m:
            cands.append((idx, sec_order(norm_num(m.group(1).split(" ")[0]))))
    # section numbers rise through a file: keep the longest rising run of candidates (a misread or a
    # cross-reference drops out without taking its neighbours with it)
    keep_idx = {cands[i][0] for i in lis([c[1] for c in cands])}
    for idx, (pno, para) in enumerate(paras):
        m = (SEC1925.match(para) if year == 1925 else SEC.match(para)) if idx in keep_idx else None
        if m:
            num = norm_num(re.sub(r"\s+", " ", m.group(1)).replace("–", "-"))
            if year == 1925:
                heading, body = m.group(2).strip(), m.group(3).strip()
            else:
                rest = m.group(2).strip()
                hm = re.match(r"(.+?[^A-Z]\.)\s+(?=[A-Z(“\"])(.*)$", rest)
                heading, body = (hm.group(1), hm.group(2)) if hm else (rest, "")
            heading = heading.rstrip(".,").strip()
            sm = STATUS.match(heading)
            key = num.split(" ")[0]
            cur = {"num": num, "heading": heading, "paras": [], "credit": "", "notes": [],
                   "status": sm.group(1).lower() if sm else "", "file": file_id, "page": pno}
            if key in secs:
                key = key + "#dup"
            secs[key] = cur
            if body:
                add_para(cur, body)
            continue
        if cur is None:
            continue
        if CHAPTER.match(para) or para in ("Sec.", "Sec", "See,", "Sec,"):
            cur = None  # a chapter heading and its table of contents
            continue
        if is_heading_note(para):
            cur["notes"].append([para.strip(), []])
            continue
        nh = NOTE_HEAD.match(para)
        if nh and is_heading_note(nh.group(1)) and len(nh.group(1)) >= 6:
            cur["notes"].append([nh.group(1).strip(), [para[nh.end():].strip()]])
            continue
        if cur["notes"]:
            cur["notes"][-1][1].append(para)
            continue
        add_para(cur, para)
    return secs


INLINE_NOTE = re.compile(r"^(.*?)\s*(" + CREDIT_START + r"[^()]*(?:\([^()]*\)[^()]*)*\.?\s*\))\s+"
                         r"([A-Z][A-Z ,;'’&\-]{3,60}[A-Z])\s+(\S.*)$")


def add_para(cur: dict, para: str) -> None:
    """A text paragraph, or a source credit (alone, or closing the paragraph), or text + credit + a note run in."""
    m = INLINE_NOTE.match(para)
    if m and re.search(r"Stat|R\.\s*S", m.group(2)) and is_heading_note(m.group(3)):
        if m.group(1).strip():
            cur["paras"].append(m.group(1).strip())
        cur["credit"] = (cur["credit"] + " " + m.group(2)).strip()
        cur["notes"].append([m.group(3).strip(), [m.group(4).strip()]])
        return
    if re.match(CREDIT_START, para) and re.search(r"Stat|R\.\s*S", para):
        cur["credit"] = (cur["credit"] + " " + para).strip()
        return
    tc = TRAILING_CREDIT.search(para)
    if tc and re.search(r"Stat|R\.\s*S", tc.group(1)):
        body = para[: tc.start()].strip()
        if body:
            cur["paras"].append(body)
        cur["credit"] = (cur["credit"] + " " + tc.group(1)).strip()
        return
    cur["paras"].append(para)


def size(sec: dict) -> int:
    return sum(len(p) for p in sec["paras"]) + len(sec["credit"]) + sum(len(x) for _, ps in sec["notes"] for x in ps)


def merge_into(store: dict, got: dict) -> None:
    """Sections read twice (shared boundary pages, or printed twice): keep the longer reading."""
    for k, v in got.items():
        base = k.split("#")[0]
        if base in store:
            if size(v) > size(store[base]):
                store[base] = v
        else:
            store[base] = v


def main() -> None:
    year = int(sys.argv[1])
    want = {int(t) for t in sys.argv[2:]} or None
    tdir = os.path.join(ROOT, "text", str(year))
    by_title: dict[int, list[str]] = {}
    for name in sorted(os.listdir(tdir)):
        if name.endswith(".tess.txt"):
            stem = name[:-9]
        elif name.endswith(".doctr.txt") and not os.path.exists(os.path.join(tdir, name[:-10] + ".tess.txt")):
            stem = name[:-10]
        else:
            continue
        t = int(stem.split("-")[1][3:6])
        if want and t not in want:
            continue
        by_title.setdefault(t, []).append(stem)
    for t, stems in sorted(by_title.items()):
        stems.sort(key=lambda s: (int(s.split("-")[1][:3]), int(s.split("-")[1][6:9])))
        files, appendix = [], []
        stores = {"tess": {}, "lura": {}, "doctr": {}}
        for stem in stems:
            subj, pages = subject_of(year, stem)
            rec = {"id": stem, "subject": subj, "pages": pages}
            if re.search(r"Appendix", subj, re.I):
                appendix.append(rec)
                continue
            files.append(rec)
            for kind in ("tess", "lura", "doctr"):
                p = os.path.join(tdir, f"{stem}.{kind}.txt")
                if kind == "tess" and not os.path.exists(p):
                    p = os.path.join(tdir, f"{stem}.doctr.txt")  # the GPU reading stands in for Tesseract
                elif kind == "doctr" and not os.path.exists(os.path.join(tdir, f"{stem}.tess.txt")):
                    continue  # already used as the main reading
                if os.path.exists(p):
                    merge_into(stores[kind], parse_text(open(p, encoding="utf-8").read(), stem, year))
        out_dir = os.path.join(ROOT, "parsed", str(year))
        os.makedirs(out_dir, exist_ok=True)
        data = {"year": year, "title": t, "files": files, "appendix_files": appendix,
                "sections": stores["tess"], "lura": stores["lura"], "doctr": stores["doctr"]}
        with gzip.open(os.path.join(out_dir, f"title{t}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(year, t, len(files), "files", len(stores["tess"]), "sections (tess)", len(stores["lura"]), "(lura)", flush=True)


if __name__ == "__main__":
    main()
