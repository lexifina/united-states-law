"""Fetches GovInfo's annual editions of US Code titles and keeps a compact parse of each (gzipped JSON); the raw HTML is
streamed to a scratch file, hashed, parsed and deleted, so disk use stays at one title-edition at a time.

    python fetch_parse.py <first year> <last year> <title> [<title> ...]

Output: ../data/title<T>/<Y>.json.gz with the URL, SHA-256, size and fetch time of the bytes parsed, the edition's
laws-enacted-through date, and per section: heading, lines (path, text), repealed, source credit and the notes this
history reads (amendment and effective-date notes). Paced at one request per 1.5 s; create STOP-FETCH beside this file to stop.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from services.us_code_history.editions import clean, parse_edition  # noqa: E402

UA = "Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)"
SHARED_CACHE = Path(r"C:/Users/alany/Documents/lexifina/src/backend/.us_code_history/cache")
KEEP_NOTES = ("amendment-note", "effectivedate-amendment-note", "effectivedate-terminationdate-amendment-note",
              "terminationdate-amendment-note", "futureamendment-note", "transfer-note", "repeal-note", "codification-note")


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    print(line, flush=True)
    with open(ROOT / "logs" / "fetch.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def url_of(year: int, title: int) -> str:
    return f"https://www.govinfo.gov/content/pkg/USCODE-{year}-title{title}/html/USCODE-{year}-title{title}.htm"


def fetch(url: str, dest: Path) -> tuple[str, int, str] | None:
    """Streams url to dest. Returns (sha256, bytes, fetched_at), or None when GovInfo has no such file."""
    for attempt in range(4):
        try:
            h = hashlib.sha256()
            n = 0
            with httpx.stream("GET", url, headers={"user-agent": UA}, follow_redirects=True, timeout=300) as r:
                if r.status_code == 404:
                    return None
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
                        h.update(chunk)
                        n += len(chunk)
            time.sleep(1.5)
            head = dest.read_bytes()[:8000].lower()
            if b"<title>error" in head or b"<title>page not found" in head:
                return None
            return h.hexdigest(), n, datetime.now(timezone.utc).isoformat(timespec="seconds")
        except (httpx.HTTPError, OSError) as e:
            log(f"retry {url}: {e!r}")
            time.sleep(10 + attempt * 20)
    raise RuntimeError(f"could not fetch {url}")


def compact(raw: bytes, title: int, year: int, url: str, sha: str, size: int, fetched_at: str) -> dict:
    page = raw[:20000].decode("utf-8", errors="replace")
    through = re.search(r"AUTHORITIES-LAWS-ENACTED-THROUGH-DATE:(\d{8})", page)
    pubname = re.search(r"AUTHORITIES-PUBLICATION-NAME:([^-\n]+?)\s*-->", page)
    ed = parse_edition(raw, title=title, year=year, sha256=sha, url=url, fetched_at=fetched_at)
    sections = {}
    for n, s in ed.sections.items():
        sections[n] = {
            "heading": s.heading,
            "lines": [[p.path, p.text, p.level] for p in s.provisions],
            "repealed": s.repealed,
            "source_credit": s.source_credit,
            "current_through": s.current_through,
            "notes": {k: v for k, v in s.notes.items() if k in KEEP_NOTES},
        }
    t = through.group(1) if through else ed.current_through.replace("-", "")
    # Bracketed placeholders the parser leaves out: "[§54AA. Repealed. Pub. L. 115–97, ...]", "[§§54 to 54F. ...]".
    # They say which law took a section out of the Code.
    text = raw.decode("utf-8", errors="replace")
    placeholders = []
    for m in _PLACEHOLDER.finditer(text):
        head = _HEAD.search(text, m.end(), m.end() + 4000)
        if head:
            placeholders.append(clean(head.group(1)))
    return {"title": title, "year": year, "url": url, "sha256": sha, "bytes": size, "fetched_at": fetched_at,
            "through": f"{t[:4]}-{t[4:6]}-{t[6:]}", "publication": pubname.group(1).strip() if pubname else "",
            "title_name": ed.title_name, "sections": sections, "placeholders": placeholders}


_PLACEHOLDER = re.compile(r"<!-- documentid:\d+[A-Za-z]?_\[")
_HEAD = re.compile(r'<h3 class="section-head">(.*?)</h3>', re.S)


def main() -> None:
    first, last = int(sys.argv[1]), int(sys.argv[2])
    titles = [int(t) for t in sys.argv[3:]]
    (ROOT / "logs").mkdir(exist_ok=True)
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    for title in titles:
        for year in range(first, last + 1):
            if (HERE / "STOP-FETCH").exists():
                log("STOP")
                return
            out = ROOT / "data" / f"title{title}" / f"{year}.json.gz"
            if out.exists():
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            url = url_of(year, title)
            cached = SHARED_CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")
            meta = cached.with_suffix(".json")
            if cached.exists() and meta.exists():
                raw = cached.read_bytes()
                m = json.loads(meta.read_text(encoding="utf-8"))
                got = (m["sha256"], len(raw), m["fetched_at"])
                tmp = None
            else:
                tmp = scratch / f"t{title}-{year}.htm"
                got = fetch(url, tmp)
                if got is None:
                    log(f"title {title} {year}: not published")
                    out.with_suffix("").with_suffix(".missing").write_text(url, encoding="utf-8")
                    if tmp.exists():
                        tmp.unlink()
                    continue
                raw = tmp.read_bytes()
            data = compact(raw, title, year, url, *got)
            part = out.with_suffix(".part")
            with gzip.open(part, "wt", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(part, out)
            if tmp is not None:
                tmp.unlink()
            log(f"title {title} {year}: {len(data['sections'])} sections, {got[1]} bytes, through {data['through']}")


if __name__ == "__main__":
    main()
