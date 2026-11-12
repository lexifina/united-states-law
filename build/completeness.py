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
        if not ae.endswith("@lexifina.com"):
            commits += 1  # documentation commits by Lexifina are not changes
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


PAL = {  # GitHub Primer: light and dark
    "light": dict(bg="#ffffff", border="#d1d9e0", fg="#1f2328", muted="#59636e", track="#eff2f5", done="#1f883d",
                  g=["#eff2f5", "#aceebb", "#4ac26b", "#2da44e", "#116329"], gstroke="#1f2328"),
    "dark": dict(bg="#0d1117", border="#3d444d", fg="#f0f6fc", muted="#9198a1", track="#262c36", done="#2ea043",
                 g=["#151b23", "#033a16", "#196c2e", "#2ea043", "#56d364"], gstroke="#f0f6fc"),
}
FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans,Helvetica,Arial,sans-serif"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(v: float) -> str:
    return (f"{v:.1f}" if (99 < v < 99.95 or (v < 10 and v % 1)) else f"{v:.0f}") + "%"


def svg(st: dict, mode: str) -> str:
    """GitHub-native: Primer borders and label pills, a joined row of counters, the changes by the year they took effect
    as a bar chart (GovInfo's editions in green, the printed editions in light green), and Primer progress bars."""
    c = PAL[mode]
    W, H = 880, 586
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" fill="{c["bg"]}" stroke="{c["border"]}"/>']
    o.append(f'<text x="24" y="38" font-size="16" font-weight="600" fill="{c["fg"]}">The US Code as a git history</text>')
    x = 262
    for lab in (st["ref"], f'release point {st["release_point"]}', f'current through {st["current_through"]}'):
        w = 16 + 6.4 * len(lab)
        o.append(f'<rect x="{x:.1f}" y="24.5" width="{w:.0f}" height="20" rx="10" fill="none" stroke="{c["border"]}"/>')
        o.append(f'<text x="{x + w / 2:.1f}" y="38.5" font-size="11.5" font-weight="500" text-anchor="middle" fill="{c["muted"]}">{esc(lab)}</text>')
        x += w + 8
    tiles = [(f'{st["titles"]}', "titles, all of the Code"), (f'{st["commits"]:,}', "changes, as commits"), (f'{st["files"]:,}', "section files"),
             (f'{st["laws"]:,}', "laws credited as authors"), (pct(st["history_all"]), "of the history since 1926")]
    tw = (W - 48) / len(tiles)
    o.append(f'<rect x="24.5" y="60.5" width="{W - 49}" height="58" rx="6" fill="{c["bg"]}" stroke="{c["border"]}"/>')
    for i, (big, small) in enumerate(tiles):
        tx = 24 + i * tw
        if i:
            o.append(f'<line x1="{tx:.1f}" y1="61" x2="{tx:.1f}" y2="118" stroke="{c["border"]}"/>')
        o.append(f'<text x="{tx + 16:.1f}" y="87" font-size="20" font-weight="600" fill="{c["fg"]}">{esc(big)}</text>')
        o.append(f'<text x="{tx + 16:.1f}" y="106" font-size="12" fill="{c["muted"]}">{esc(small)}</text>')

    # box 1: bar chart of changes by the year they took effect
    bx, by, bw, bh = 24.5, 134.5, W - 49, 248
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="{c["bg"]}" stroke="{c["border"]}"/>')
    o.append(f'<text x="{bx + 16}" y="{by + 26}" font-size="14" font-weight="600" fill="{c["fg"]}">Changes by the year they took effect</text>')
    # legend: swatch, then label, left to right on the title line
    lx = bx + bw - 372
    for col, lab in ((c["g"][2], "printed editions, read by OCR"), (c["done"], "GovInfo\u2019s editions, 1994 on")):
        o.append(f'<rect x="{lx:.1f}" y="{by + 17}" width="10" height="10" rx="2" fill="{col}"/>')
        o.append(f'<text x="{lx + 15:.1f}" y="{by + 26}" font-size="11.5" fill="{c["muted"]}">{esc(lab)}</text>')
        lx += 15 + 6.0 * len(lab) + 18
    py = {int(k): v for k, v in st["per_year"].items()}
    y0, y1 = 1925, date.today().year
    top = max(py.values())
    step = 100
    ymax = ((top // step) + 1) * step
    gl, gr, gt, gb = bx + 52, bx + bw - 16, by + 46, by + bh - 52
    ih = gb - gt
    for k in range(0, ymax + 1, step):
        yy = gb - ih * k / ymax
        o.append(f'<line x1="{gl}" y1="{yy:.1f}" x2="{gr}" y2="{yy:.1f}" stroke="{c["border"]}" stroke-width="{1 if k == 0 else 0.6}"'
                 + ('' if k == 0 else ' stroke-dasharray="3 3"') + '/>')
        o.append(f'<text x="{gl - 8}" y="{yy + 4:.1f}" font-size="11" text-anchor="end" fill="{c["muted"]}">{k:,}</text>')
    n = y1 - y0 + 1
    bwid = (gr - gl) / n
    peak = max(py, key=lambda y: py[y])
    for i, yr in enumerate(range(y0, y1 + 1)):
        v = py.get(yr, 0)
        x0 = gl + i * bwid
        if v:
            h = max(1.5, ih * v / ymax)
            o.append(f'<rect x="{x0 + 0.6:.1f}" y="{gb - h:.1f}" width="{bwid - 1.2:.1f}" height="{h:.1f}" rx="1.5" '
                     f'fill="{c["g"][2] if yr < 1995 else c["done"]}"><title>{yr}: {v:,} change{"" if v == 1 else "s"} took effect</title></rect>')
        if yr % 10 == 0:
            o.append(f'<text x="{x0 + bwid / 2:.1f}" y="{gb + 16}" font-size="11" text-anchor="middle" fill="{c["muted"]}">{yr}</text>')
        if yr == peak:
            o.append(f'<text x="{x0 + bwid / 2:.1f}" y="{gb - ih * v / ymax - 6:.1f}" font-size="11" font-weight="600" text-anchor="middle" fill="{c["fg"]}">{v:,}</text>')
            o.append(f'<text x="{x0 + bwid + 4:.1f}" y="{gb - ih * v / ymax + 6:.1f}" font-size="11" fill="{c["muted"]}">in {yr}</text>')
    pre = sum(v for y, v in py.items() if y < 1995)
    o.append(f'<text x="{bx + 16}" y="{by + bh - 14}" font-size="11.5" fill="{c["muted"]}">Before 1995: {pre:,} changes, '
             f'from the printed editions read so far (title 1 from the 1926 Code; most of title 26 from 1986). '
             f'The other titles start with GovInfo\u2019s 1994 edition.</text>')

    # box 2: completeness, two columns of progress bars
    cy = by + bh + 14
    ch = 152
    o.append(f'<rect x="{bx}" y="{cy}" width="{bw}" height="{ch}" rx="6" fill="{c["bg"]}" stroke="{c["border"]}"/>')
    o.append(f'<text x="{bx + 16}" y="{cy + 26}" font-size="14" font-weight="600" fill="{c["fg"]}">Completeness</text>')
    rows = [
        ("Titles in the record", 100.0, f'{st["titles"]} of {st["titles"]}'),
        ("Current text", 100.0, f'release point {st["release_point"]}'),
        ("History since the 1994 edition", st["history_since_1995"], "title-years covered"),
        ("History 1926 to 1994", st["history_before_1995"], "title-years covered"),
        ("Printed editions 1926\u20131988 read", 100 * st["title_editions_built"] / st["title_editions_pre1994"],
         f'{st["title_editions_built"]} of {st["title_editions_pre1994"]} title-editions'),
        ("Whole history since 1926", st["history_all"], "title-years covered"),
    ]
    colw = (bw - 32 - 32) / 2
    for i, (label, v, note) in enumerate(rows):
        col, r = divmod(i, 3)
        x0 = bx + 16 + col * (colw + 32)
        ry = cy + 50 + r * 36
        o.append(f'<text x="{x0}" y="{ry}" font-size="13" fill="{c["fg"]}">{esc(label)}</text>')
        o.append(f'<text x="{x0}" y="{ry + 16}" font-size="11.5" fill="{c["muted"]}">{esc(note)}</text>')
        px, pw = x0 + 214, colw - 214 - 56
        o.append(f'<g><title>{esc(label)}: {pct(v)} ({esc(note)})</title>'
                 f'<rect x="{px:.1f}" y="{ry - 3}" width="{pw:.1f}" height="8" rx="4" fill="{c["track"]}"/>'
                 + (f'<rect x="{px:.1f}" y="{ry - 3}" width="{max(4.0, pw * v / 100):.1f}" height="8" rx="4" fill="{c["done"]}"/>' if v > 0 else "")
                 + "</g>")
        o.append(f'<text x="{x0 + colw:.1f}" y="{ry + 4}" font-size="13" font-weight="600" text-anchor="end" fill="{c["fg"]}">{pct(v)}</text>')
    o.append(f'<text x="24" y="{H - 16}" font-size="11.5" fill="{c["muted"]}">At {st["ref"]}, built {date.today().isoformat()}. '
             f'Title-years: for each title, the years its record covers over the years it has been in the Code since the '
             f'1926 Code (laws in force December 7, 1925).</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    main()
