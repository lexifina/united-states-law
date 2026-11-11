"""Cleans one OCR'd edition of a title against the clean edition after it, and writes it in fetch_parse.py's shape.

    python clean.py <title> <year> <next year>

Inputs: parsed/<Y>/title<T>.json.gz (parse_ocr.py: Tesseract and LuraTech readings) and the clean next edition,
data/title<T>/<NEXT>.json.gz (GovInfo for 1994, else this script's own output). Output: data/title<T>/<Y>.json.gz.

Rule, per section with a newer counterpart: the OCR words are aligned with the newer edition's words. Where they
agree, allowing for OCR confusions (a letter or two), the newer edition's words, punctuation and line structure are
taken: they are the same words, printed cleanly. Where they differ, the difference is kept only when both OCR
engines show it (each read the scan independently); a difference only one engine shows is a misreading and the
newer words are kept. So the older edition differs from the newer one only where both readings of the scan say so.
A section with no newer counterpart (repealed, renumbered, or dropped before the next edition) keeps the Tesseract
reading, with words corrected where LuraTech agrees with a dictionary of the title's clean words.
"""
from __future__ import annotations

import difflib
import gzip
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

CONFUSE = str.maketrans({"0": "o", "1": "l", "|": "l", "!": "l", "I": "l", "i": "l", "5": "s", "$": "s", "§": "s",
                         "8": "s", "6": "b", "€": "e", "é": "e", "c": "e", "v": "y", "f": "t", "h": "b", "n": "u",
                         "Q": "o", "q": "o", "D": "o", "a": "o", "O": "o"})


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return (s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("—", "—")
            .replace("–", "-").replace("­", ""))


def tokens(s: str) -> list[str]:
    return norm_text(s).split()


def skel(tok: str) -> str:
    t = re.sub(r"[^\w§$|!€é]", "", tok)
    t = t.replace("rn", "m").replace("cl", "d").replace("li", "h").replace("ii", "u").replace("vv", "w")
    return t.translate(CONFUSE).lower()


def lev1(a: str, b: str, k: int) -> bool:
    """edit distance <= k (small k, short strings)"""
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > k:
            return False
        prev = cur
    return prev[-1] <= k


def same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    sa, sb = skel(a), skel(b)
    if sa == sb:
        return True
    n = max(len(sa), len(sb))
    if n <= 2:
        return False
    return lev1(sa, sb, 1 if n <= 6 else 2)


def diff_ranges(ocr: list[str], new: list[str]) -> list[tuple[int, int, int, int]]:
    """Ranges (i1, i2, j1, j2) where ocr[i1:i2] and new[j1:j2] really differ (not OCR confusions)."""
    sm = difflib.SequenceMatcher(None, [skel(t) for t in ocr], [skel(t) for t in new], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        a, b = ocr[i1:i2], new[j1:j2]
        if len(a) == len(b) and all(same_word(x, y) for x, y in zip(a, b)):
            continue
        # a word split or joined by the OCR ("con- tents" / "contents")
        if "".join(skel(x) for x in a) == "".join(skel(y) for y in b) or (
                a and b and same_word("".join(a), "".join(b))):
            continue
        out.append((i1, i2, j1, j2))
    return out


NOTEISH = re.compile(r"(referred to in|So in original|For complete classification|see Tables|Short Title|DERIVATION|"
                     r"\([RB]\.\s*S\.\s*§|"
                     r"Effective Date|Codification|Amendments|Cross References|Section Referred|"
                     r"Ex\. Ord\.|Reorg\. Plan|F\.R\.|Prior Provisions|Transfer of Functions)", re.I)
CITATION = re.compile(r"^\(?\s*(?:[RB]\.\s*S\.|Pub\.\s*L\.|[A-Z][a-z]{2,4}\.?\s+\d{1,2},\s+\d{4}|S\.\s*Res\.|H\.\s*Res\.)")


def similar(a: list[str], b: list[str]) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    sm = difflib.SequenceMatcher(None, [skel(x) for x in a], [skel(x) for x in b], autojunk=False)
    return sm.ratio() >= 0.5


def confirmed(t_ranges, l_ranges, t: list[str], l: list[str]) -> list[tuple[int, int, int, int]]:
    """Tesseract differences that LuraTech also shows over the same stretch of the newer text, reading similar
    old words there (both engines saw the same printed words, and they are not the newer edition's)."""
    keep = []
    for (i1, i2, j1, j2) in t_ranges:
        old_words = t[i1:i2]
        text = " ".join(old_words)
        cites = len(re.findall(r"\d+\s+Stat[.,]", text)) + len(re.findall(r"Pub\.\s*L\.\s*\d", text))
        if old_words and (NOTEISH.search(text) or (CITATION.match(text) and re.search(r"Stat\.|\d{4}", text))
                          or (cites and DATE.search(text))):
            continue  # a note, footnote or source credit the parser left in the text: not the section's words
        for (k1, k2, lj1, lj2) in l_ranges:
            if lj2 < j1 or lj1 > j2 or (lj1 == lj2 and not (j1 <= lj1 <= j2)):
                continue
            if similar(old_words, l[k1:k2]):
                keep.append((i1, i2, j1, j2))
                break
    return keep


def flatten_lines(lines: list) -> tuple[list[str], list[int]]:
    toks, owner = [], []
    for k, ln in enumerate(lines):
        for t in tokens(ln[1]):
            toks.append(t)
            owner.append(k)
    return toks, owner


def body_tokens(sec: dict | None) -> list[str]:
    if not sec:
        return []
    text = " ".join(sec.get("paras") or [])
    # a word broken at a line end ("evi- dence"): the OCR keeps the hyphen and a space
    text = re.sub(r"(\w)[-\u00ad]\s+([a-z])", r"\1\2", text)
    return tokens(text)


DESIG = re.compile(r"^\(([a-zA-Z0-9]{1,6})\)")


def lines_from_paras(paras: list[str]) -> list:
    """Lines for a section with no newer counterpart: one per paragraph, path from its leading designations."""
    out = []
    kinds: list[str] = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        path = ""
        m = DESIG.match(p)
        if m:
            d = m.group(1)
            kind = ("roman" if re.fullmatch(r"[ivxl]+", d) and kinds and kinds[-1] in ("upper", "roman")
                    else "lower" if d.islower() else "num" if d.isdigit() else "upper" if d.isupper() else "other")
            if kind in kinds:
                kinds = kinds[: kinds.index(kind) + 1]
            else:
                kinds.append(kind)
            path = "".join("(x)" for _ in kinds[:-1]) + f"({d})"
        out.append([path, p, max(0, len(kinds) - 1)])
    return out


def rebuild(new_lines: list, ocr: list[str], keep: list[tuple[int, int, int, int]]) -> list:
    """The older text: the newer lines, with each kept range replaced by the OCR words."""
    ntoks, owner = flatten_lines(new_lines)
    # per newer token: replacement words (list) or None (keep); insertions before index j
    repl: dict[int, list[str]] = {}
    drop: set[int] = set()
    for (i1, i2, j1, j2) in keep:
        words = list(ocr[i1:i2])
        # inside a changed run, words the OCR read as the newer edition's take its spelling and typography
        old_new = ntoks[j1:j2]
        if words and old_new:
            sm = difflib.SequenceMatcher(None, [skel(w) for w in words], [skel(w) for w in old_new], autojunk=False)
            for op, a1, a2, b1, b2 in sm.get_opcodes():
                if op == "equal" or (op == "replace" and a2 - a1 == b2 - b1):
                    for a, b in zip(range(a1, a2), range(b1, b2)):
                        if same_word(words[a], old_new[b]):
                            words[a] = old_new[b]
        if j2 > j1:
            for j in range(j1, j2):
                drop.add(j)
            repl.setdefault(j1, []).extend(words)
        else:
            repl.setdefault(j1, []).extend(words)  # inserted before newer token j1 (or at the end)
    per_line: list[list[str]] = [[] for _ in new_lines]
    for j in range(len(ntoks) + 1):
        if j in repl and repl[j]:
            k = owner[j] if j < len(ntoks) else (owner[-1] if owner else 0)
            if per_line:
                per_line[k].extend(repl[j])
        if j < len(ntoks) and j not in drop:
            per_line[owner[j]].append(ntoks[j])
    out = []
    for ln, words in zip(new_lines, per_line):
        if words:
            out.append([ln[0], " ".join(words), ln[2] if len(ln) > 2 else 0])
    return out


# Laws enacted through (each edition's cutoff); checked against the editions' own front matter in build_block.
CUTOFF = {1925: "1925-12-07", 1934: "1935-01-03", 1940: "1941-01-03", 1946: "1947-01-02", 1952: "1953-01-06",
          1958: "1959-01-06", 1964: "1965-01-03", 1970: "1971-01-20", 1976: "1977-01-03", 1982: "1983-01-14",
          1988: "1989-01-03", 1994: "1995-01-04", 1995: "1996-01-16"}
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "aug": 8,
       "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),\s+(\d{4})")
NOTE_YEAR = re.compile(r"(?:^|>|\s)(\d{4})\s*(?:&mdash;|—|-{1,2})\s*(?:Pub\.|Act|Subsec|Par|Pars|Subsecs|Cl)")


def newer_law_after(new: dict, cutoff: str) -> bool:
    """Does the newer edition name, for this section, a law enacted after the older edition's cutoff?"""
    text = new.get("source_credit") or ""
    for m in DATE.finditer(text):
        d = f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
        if d > cutoff:
            return True
    notes = new.get("notes") or {}
    for k, v in notes.items():
        if "amendment" not in k and "ocr-notes" not in k:
            continue
        blob = " ".join(x if isinstance(x, str) else " ".join(map(str, x)) for x in v)
        for m in NOTE_YEAR.finditer(blob):
            if m.group(1) > cutoff[:4]:
                return True
        for m in DATE.finditer(blob):
            d = f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
            if d > cutoff:
                return True
    return False


def clean_section(new: dict | None, tess: dict | None, lura: dict | None, cutoff: str = "",
                  doctr: dict | None = None) -> tuple[dict, dict]:
    stats = {"kept_ranges": 0, "noise_ranges": 0}
    src = tess or lura
    if new is None:
        lines = lines_from_paras(src.get("paras") or [])
        return {"heading": src.get("heading", ""), "lines": lines, "repealed": bool(src.get("status")),
                "source_credit": src.get("credit", ""), "current_through": None,
                "notes": {"ocr-notes": [[h, ps] for h, ps in src.get("notes", [])]}, "ocr": "unanchored"}, stats
    ntoks, _ = flatten_lines(new["lines"])
    t = body_tokens(tess)
    l = body_tokens(lura)
    tr = diff_ranges(t, ntoks) if t else []
    lr = diff_ranges(l, ntoks) if l else []
    d = body_tokens(doctr)
    dr = diff_ranges(d, ntoks) if d else []
    # a difference stands when a second reading shows it too (Tesseract with the PDF's layer, or with docTR)
    keep = confirmed(tr, lr, t, l) if (t and l) else []
    if d:
        keep = sorted(set(keep) | set(confirmed(tr, dr, t, d)))
        if not t:
            keep = confirmed(dr, lr, d, l) if l else []
            t = d
    if keep and cutoff and not newer_law_after(new, cutoff):
        # no law changed this section between the editions: text added or dropped is the parse or the scan, not the
        # law; a short substitution both readings show is kept (an editorial change by the publisher)
        keep = [r for r in keep if (r[1] - r[0]) > 0 and (r[3] - r[2]) > 0 and (r[1] - r[0]) <= 6 and (r[3] - r[2]) <= 6]
    stats["kept_ranges"] = len(keep)
    stats["noise_ranges"] = len(tr) - len(keep)
    lines = rebuild(new["lines"], t, keep) if keep else [list(x) for x in new["lines"]]
    changed_words = sum(i2 - i1 for (i1, i2, _, _) in keep)
    if keep and t and changed_words > 0.25 * len(t):
        # most of the section reads differently from the newer edition: keep this edition's own paragraphs, not
        # the newer edition's line structure
        best = tess if tess and tess.get("paras") else (doctr or lura)
        paras = [re.sub(r"(\w)[-\u00ad]\s+([a-z])", r"\1\2", x) for x in (best.get("paras") or [])]
        lines = lines_from_paras(paras)
        stats["own_layout"] = 1
    heading = new["heading"]
    th = (tess or {}).get("heading", "")
    if th and not all(same_word(a, b) for a, b in zip(tokens(th), tokens(heading))) and len(tokens(th)) != len(tokens(heading)):
        lh = (lura or {}).get("heading", "")
        if lh and len(tokens(lh)) == len(tokens(th)):
            heading = th  # both readings give a different heading
    credit = max(((x or {}).get("credit", "") for x in (tess, lura, doctr)), key=len)  # the reading that kept it
    return {"heading": heading, "lines": lines, "repealed": bool(src.get("status")) and not lines,
            "source_credit": credit, "current_through": None,
            "notes": {"ocr-notes": [[h, ps] for h, ps in src.get("notes", [])]},
            "ocr": "anchored" if not keep else "anchored-changed"}, stats


def main() -> None:
    T, Y, NY = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    later = [int(x) for x in sys.argv[4:]]  # editions after NY, newest last: anchors for sections NY did not read
    p = json.load(gzip.open(os.path.join(ROOT, "parsed", str(Y), f"title{T}.json.gz"), "rt", encoding="utf-8"))
    nxt = json.load(gzip.open(os.path.join(DATA, f"title{T}", f"{NY}.json.gz"), "rt", encoding="utf-8"))
    fallbacks = []
    for y in later:
        fp = os.path.join(DATA, f"title{T}", f"{y}.json.gz")
        if os.path.exists(fp):
            fallbacks.append(json.load(gzip.open(fp, "rt", encoding="utf-8"))["sections"])
    secs = {}
    tot = {"anchored": 0, "anchored-changed": 0, "unanchored": 0, "kept_ranges": 0, "noise_ranges": 0}
    # a section either reading found: the other reading may have run its start into the section before
    for n in list(p["sections"]) + [k for k in p["lura"] if k not in p["sections"]]:
        ts, ls = p["sections"].get(n), p["lura"].get(n)
        ds = (p.get("doctr") or {}).get(n)
        new = nxt["sections"].get(n)
        if new is None:
            # the next edition did not read this section (a missed start or a gap): the nearest later edition that did
            new = next((fb[n] for fb in fallbacks if n in fb and fb[n].get("lines")), None)
        sec, st = clean_section(new, ts, ls, CUTOFF.get(Y, ""), ds)
        secs[n] = sec
        tot[sec["ocr"]] += 1
        for k in ("kept_ranges", "noise_ranges"):
            tot[k] += st[k]
    out = {"title": T, "year": Y, "url": [f"https://tile.loc.gov/storage-services/service/ll/uscode/{f['id'][:16]}/{f['id']}/{f['id']}.pdf" for f in p["files"]],
           "through": None, "publication": f"{Y} Edition", "title_name": nxt.get("title_name", ""),
           "sections": secs, "placeholders": [], "ocr_stats": tot}
    os.makedirs(os.path.join(DATA, f"title{T}"), exist_ok=True)
    with gzip.open(os.path.join(DATA, f"title{T}", f"{Y}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(T, Y, "<-", NY, tot)


if __name__ == "__main__":
    main()
