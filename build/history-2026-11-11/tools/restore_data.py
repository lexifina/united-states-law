"""For each printed version main's history from 2017 uses (annual editions 2017-2024, OLRC release points), the lines
main's parser drops (paragraphs GovInfo prints with a style attribute) and where they go.

    python restore_data.py <title> [<title> ...]

Writes ../restore/title<T>.json: [{key, date, files: {"title-T/N.md": [[before, after, [lines]], ...]}}], where before/after
are up to three lines on each side of the insertion in main's render. Only pure insertions are kept; any other
difference between the two renders is counted in "skipped" and left alone.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from oldp.uch.editions import parse_edition as parse_old  # noqa: E402
from render import render_lines  # noqa: E402
from services.us_code_history.editions import parse_edition as parse_new  # noqa: E402

CACHE = Path(r"C:/Users/alany/Documents/lexifina/src/backend/.us_code_history/cache")
STYLE = re.compile(rb'<p class="statutory-body[^"]*" style=')


def cached(url: str) -> bytes | None:
    p = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")
    return p.read_bytes() if p.exists() else None


def versions(t: int):
    for y in range(2017, 2025):
        raw = cached(f"https://www.govinfo.gov/content/pkg/USCODE-{y}-title{t}/html/USCODE-{y}-title{t}.htm")
        if raw:
            through = re.search(rb"AUTHORITIES-LAWS-ENACTED-THROUGH-DATE:(\d{8})", raw[:20000]).group(1).decode()
            yield str(y), f"{through[:4]}-{through[4:6]}-{through[6:]}", raw
    keys = set()
    for m in CACHE.glob("*.json"):
        u = json.loads(m.read_text(encoding="utf-8")).get("url", "")
        hit = re.search(rf"/htm_usc{t:02d}@(119-\d+)\.zip$", u)
        if hit:
            keys.add((hit.group(1), u))
    for key, u in sorted(keys, key=lambda k: int(k[0].split("-")[1])):
        z = zipfile.ZipFile(io.BytesIO(cached(u)))
        name = next(n for n in z.namelist() if n.endswith(".htm"))
        raw = z.read(name)
        dates = sorted(set(re.findall(rb"currentthrough:(\d{8})", raw)))
        d = dates[-1].decode() if dates else "00000000"
        yield f"pl{key}", f"{d[:4]}-{d[4:6]}-{d[6:]}", raw


def main() -> None:
    out_dir = ROOT / "restore"
    out_dir.mkdir(exist_ok=True)
    for t in map(int, sys.argv[1:]):
        out = []
        skipped = 0
        for key, day, raw in versions(t):
            if not STYLE.search(raw):
                out.append({"key": key, "date": day, "files": {}})
                continue
            a = parse_old(raw, title=t, year=int(day[:4]), sha256="", url="", fetched_at="")
            b = parse_new(raw, title=t, year=int(day[:4]), sha256="", url="", fetched_at="")
            files = {}
            for n, sb in b.sections.items():
                sa = a.sections.get(n)
                if sa is None:
                    continue
                style = "v2" if (t == 17 and n in ("104A", "106A", "121A")) else None
                ra = render_lines(t, n, sa.heading, [(p.path, p.text, p.level) for p in sa.provisions], style)
                rb = render_lines(t, n, sb.heading, [(p.path, p.text, p.level) for p in sb.provisions], style)
                if ra == rb or ra is None or rb is None:
                    continue
                la, lb = ra.split("\n"), rb.split("\n")
                ops = difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes()
                if any(o[0] in ("replace", "delete") for o in ops):
                    skipped += 1
                    continue
                ins = [[la[max(0, i1 - 3):i1], la[i1:i1 + 3], lb[j1:j2]] for tag, i1, i2, j1, j2 in ops if tag == "insert"]
                files[f"title-{t}/{n}.md"] = ins
            out.append({"key": key, "date": day, "files": files})
            print(f"title {t} {key} {day}: {len(files)} files", flush=True)
        (out_dir / f"title{t}.json").write_text(json.dumps({"title": t, "skipped": skipped, "versions": out}, ensure_ascii=False), encoding="utf-8")
        print(f"title {t}: done, skipped {skipped}", flush=True)


if __name__ == "__main__":
    main()
