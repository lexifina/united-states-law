"""How complete is lexifina/united-states-law? Figures and the README chart (data/effort-light.svg, -dark.svg).

    python completeness.py <repo clone> <ref> <out dir>

Reads only the repository: each title's record start (earliest In-force/Consolidated day of a commit touching it),
commits per year in force, section files, laws credited. Completeness of the history is measured in title-years: for each
title, the years its record covers over the years the title has existed in the Code since the first edition (the Code of
Laws of the United States of 1926, laws in force December 7, 1925), to the latest release point.
"""
from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import sys
from datetime import date

REPO, REF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
FIRST_CODE = date(1925, 12, 7)
EDITION_1994 = date(1995, 1, 4)
# When each title existed in the Code (start, end); titles 1-50 are in the 1926 Code.
WINDOWS = {t: [(FIRST_CODE, None)] for t in range(1, 51)}
WINDOWS[6] = [(FIRST_CODE, date(1982, 9, 13)), (date(2002, 11, 25), None)]   # Surety Bonds (repealed 1982); Domestic Security
WINDOWS[34] = [(FIRST_CODE, date(1956, 8, 10)), (date(2017, 9, 1), None)]    # Navy (repealed 1956); Crime Control
WINDOWS[51] = [(date(2010, 12, 18), None)]
WINDOWS[52] = [(date(2014, 9, 1), None)]
WINDOWS[54] = [(date(2014, 12, 19), None)]
LOC_EDITIONS = [1925, 1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982, 1988]


def git(*a) -> str:
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month - 1]} {d.day}, {d.year}"


def years(a: date, b: date) -> float:
    return max(0.0, (b - a).days / 365.25)


def main() -> None:
    log = git("log", REF, "--format=%x01%ae%x02%at%x02%B%x03", "--name-only")
    first: dict[int, date] = {}
    per_year = collections.Counter()
    laws = set()
    commits = 0
    for chunk in log.split("\x01")[1:]:
        ae, _, rest = chunk.partition("\x02")
        at, _, rest = rest.partition("\x02")
        body, _, names = rest.partition("\x03")
        commits += 1
        m = re.search(r"^(?:In-force|Consolidated): (\d{4}-\d{2}-\d{2})", body, re.M)
        if m:
            d = date.fromisoformat(m.group(1))
        elif int(at) > 86400:
            d = date.fromtimestamp(int(at))
        else:
            continue
        if ae.endswith("@lexifina.com"):
            continue  # documentation
        per_year[d.year] += 1
        if ae.endswith("public-law.invalid"):
            laws.add(ae)
        for p in names.split():
            t = re.match(r"title-(\d+)/", p)
            if t:
                T = int(t.group(1))
                if T not in first or d < first[T]:
                    first[T] = d
    files = sum(1 for p in git("ls-tree", "-r", "--name-only", REF).split("\n") if p.startswith("title-"))
    readme = git("show", f"{REF}:README.md")
    end = date.today()
    rps = re.findall(r"release point (\d+)-(\d+) \(current through (\d{4}-\d{2}-\d{2})\)", git("show", f"{REF}:corpus.json"))
    rp = max(rps, key=lambda r: (int(r[0]), int(r[1]))) if rps else None
    # title 26: 1,161 of 1,710 sections from 1986, the rest from the 1994 edition
    t26 = 1161 / 1710

    def covered(T: int, lo: date | None = None, hi: date | None = None) -> tuple[float, float]:
        have = want = 0.0
        for a, b in WINDOWS.get(T, []):
            b = b or end
            a2, b2 = max(a, lo or a), min(b, hi or b)
            if b2 <= a2:
                continue
            want += years(a2, b2)
            s = first.get(T, end)
            if T == 26:
                have += t26 * years(max(a2, s), b2) + (1 - t26) * years(max(a2, EDITION_1994), b2)
            else:
                have += years(max(a2, s), b2)
        return have, want

    tot = [covered(T) for T in WINDOWS]
    pre = [covered(T, hi=EDITION_1994) for T in WINDOWS]
    post = [covered(T, lo=EDITION_1994) for T in WINDOWS]
    pct = lambda xs: 100 * sum(h for h, _ in xs) / sum(w for _, w in xs)  # noqa: E731
    title_editions = sum(1 for y in LOC_EDITIONS for T, ws in WINDOWS.items()
                         if any(a <= date(y, 12, 31) and (b is None or b >= date(y, 12, 31)) for a, b in ws))
    built_te = sum(1 for T in WINDOWS for y in LOC_EDITIONS if first.get(T, end) <= date(y, 12, 31) < EDITION_1994
                   and first[T] < EDITION_1994 and T != 26)
    stats = {
        "ref": git("rev-parse", "--short=7", REF).strip(), "titles": len(WINDOWS), "commits": commits,
        "files": files, "laws": len(laws), "first_record": min(first.values()).isoformat(),
        "history_all": round(pct(tot), 1), "history_before_1995": round(pct(pre), 1),
        "history_since_1995": round(pct(post), 1), "title_editions_pre1994": title_editions,
        "title_editions_built": built_te, "per_year": dict(sorted(per_year.items())),
        "first": {T: d.isoformat() for T, d in sorted(first.items())}, "current_through": short_date(rp[2]) if rp else "",
        "release_point": f"{rp[0]}-{rp[1]}" if rp else "",
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(stats, open(os.path.join(OUT, "completeness.json"), "w"), indent=1)
    for mode in ("light", "dark"):
        open(os.path.join(OUT, f"effort-{mode}.svg"), "w", encoding="utf-8", newline="\n").write(svg(stats, mode))
    print(json.dumps({k: v for k, v in stats.items() if k not in ("per_year", "first")}, indent=1))


PAL = {
    "light": dict(bg="#ffffff", border="#d1d9e0", fg="#1f2328", muted="#59636e", tile="#f6f8fa", bar="#3b6fb6",
                  bar_pre="#9db6dc", done="#2f7d4f", part="#a8d5b5", track="#f6f8fa"),
    "dark": dict(bg="#0d1117", border="#3d444d", fg="#f0f6fc", muted="#9198a1", tile="#151b23", bar="#4493f8",
                 bar_pre="#2a4a7f", done="#3fb950", part="#1f4d2b", track="#151b23"),
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(st: dict, mode: str) -> str:
    c = PAL[mode]
    W, H = 880, 560
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" rx="10" fill="{c["bg"]}" stroke="{c["border"]}"/>',
         f'<text x="24" y="38" font-size="20" font-weight="600" fill="{c["fg"]}">The US Code as a git history</text>',
         f'<text x="856" y="38" font-size="12" text-anchor="end" fill="{c["muted"]}">at {st["ref"]} · built {date.today().isoformat()}</text>']
    tiles = [(f'{st["titles"]}', "titles (all of the Code)"), (f'{st["commits"]:,}', "changes, as commits"),
             (f'{st["files"]:,}', "section files"), (f'{st["laws"]:,}', "laws credited as authors"),
             (st["current_through"] or st["release_point"], "current through"),
             (f'{st["history_all"]:.0f}%', "of the history since 1926")]
    for i, (big, small) in enumerate(tiles):
        x = 24 + i * 142
        o.append(f'<rect x="{x}" y="58" width="134" height="64" rx="8" fill="{c["tile"]}" stroke="{c["border"]}"/>')
        o.append(f'<text x="{x + 12}" y="88" font-size="{19 if len(big) < 11 else 15}" font-weight="600" fill="{c["fg"]}">{esc(big)}</text>')
        o.append(f'<text x="{x + 12}" y="108" font-size="11.5" fill="{c["muted"]}">{esc(small)}</text>')
    # changes by year in force
    o.append(f'<text x="24" y="150" font-size="13" font-weight="600" fill="{c["fg"]}">Changes by the year they took effect</text>')
    py = {int(k): v for k, v in st["per_year"].items()}
    y0, y1 = 1925, date.today().year
    top = max(py.values())
    step = 500 if top > 1500 else 200
    ymax = ((top // step) + 1) * step
    base, h = 296.0, 130.0
    for k in range(0, ymax + 1, step):
        yy = base - h * k / ymax
        o.append(f'<line x1="54" y1="{yy:.1f}" x2="856" y2="{yy:.1f}" stroke="{c["border"]}" stroke-width="{1 if k == 0 else 0.6}"'
                 + ('' if k == 0 else ' stroke-dasharray="2 3"') + '/>')
        o.append(f'<text x="48" y="{yy + 3.5:.1f}" font-size="9.5" text-anchor="end" fill="{c["muted"]}">{k:,}</text>')
    n = y1 - y0 + 1
    bw = (856 - 54) / n
    for i, y in enumerate(range(y0, y1 + 1)):
        v = py.get(y, 0)
        x = 54 + i * bw
        if v:
            bh = max(1.0, h * v / ymax)
            o.append(f'<rect x="{x + 0.4:.1f}" y="{base - bh:.1f}" width="{bw - 0.8:.1f}" height="{bh:.1f}" rx="1" '
                     f'fill="{c["bar_pre"] if y < 1995 else c["bar"]}"><title>{y}: {v:,}</title></rect>')
        if y % 10 == 0:
            o.append(f'<text x="{x + bw / 2:.1f}" y="310" font-size="10" text-anchor="middle" fill="{c["muted"]}">{y}</text>')
    o.append(f'<text x="856" y="326" font-size="10.5" text-anchor="end" fill="{c["muted"]}">lighter: the record before the '
             f'1994 edition, read from the printed editions (so far title 1 from 1926, title 26 from 1986)</text>')
    # completeness by part
    o.append(f'<text x="24" y="356" font-size="13" font-weight="600" fill="{c["fg"]}">Completeness, by part</text>')
    rows = [
        ("Titles in the record", 100.0, None, f'{st["titles"]} of {st["titles"]}'),
        ("Current text (latest release point)", 100.0, None, st["release_point"] and f'release point {st["release_point"]}'),
        ("History since the 1994 edition", st["history_since_1995"], None, "title-years covered"),
        ("History 1926 to 1994", st["history_before_1995"], None, "title-years covered"),
        ("Printed editions 1926-1988 read", 100 * st["title_editions_built"] / st["title_editions_pre1994"], None,
         f'{st["title_editions_built"]} of {st["title_editions_pre1994"]} title-editions'),
        ("Whole history since 1926", st["history_all"], None, "title-years covered"),
    ]
    for i, (label, v, collected, note) in enumerate(rows):
        y = 378 + i * 26
        o.append(f'<text x="24" y="{y + 9}" font-size="12" fill="{c["fg"]}">{esc(label)}</text>')
        o.append(f'<rect x="300" y="{y}" width="392" height="10" rx="5" fill="{c["track"]}" stroke="{c["border"]}" stroke-width="0.5"/>')
        if v > 0:
            o.append(f'<rect x="300" y="{y}" width="{max(4.0, 392 * v / 100):.1f}" height="10" rx="5" fill="{c["done"]}"/>')
        o.append(f'<text x="702" y="{y + 9}" font-size="12" font-weight="600" fill="{c["fg"]}">{(f"{v:.1f}" if 99 < v < 99.95 else f"{v:.0f}")}%</text>')
        if note:
            o.append(f'<text x="748" y="{y + 9}" font-size="10" fill="{c["muted"]}">{esc(note)}</text>')
    o.append(f'<text x="24" y="{H - 14}" font-size="10.5" fill="{c["muted"]}">Title-years: for each title, the years its '
             f'record covers over the years it has been in the Code since the 1926 Code (laws in force December 7, 1925).</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    main()
