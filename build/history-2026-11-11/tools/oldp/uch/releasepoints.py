"""Release points: the Office of the Law Revision Counsel's updates of the Code between annual editions.

Each release point is current through a named public law ("Public Law 119-83 (April 13, 2026), affecting titles 1, 2,
... 11, ..."), so the change between two consecutive release points can only have been made by the laws numbered
between them, or by an earlier law's amendment that took effect in that time. That narrows each change to a handful of
laws, which is what lets a change be pinned to one law the way a commit is. The release-point files are the same
HTML the annual editions are printed from, so they are parsed the same way.

The OLRC serves only recent release points; older ones are not available for download, so the record covers annual
editions up to the last one and release points from the first one still served.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Optional

from .editions import Edition, parse_edition
from .sources import fetch

PRIOR_URL = "https://uscode.house.gov/priorreleasepoints.html"
CURRENT_URL = "https://uscode.house.gov/download.html"

_ITEM = re.compile(
    r'href="download/(?P<key>\d+-\d+[a-z0-9]*)\.html">Public Law (?P=key) \((?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})\)'
    r"(?P<rest>[^<]*)</a>"
)
_CURRENT = re.compile(r"current through Public Law (?P<key>\d+-\d+) \((?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})\)")


@dataclass
class ReleasePoint:
    key: str            # "119-83"; a key such as "119-73not60" marks a release point that leaves a law out
    date: str           # ISO date of the law it is current through
    titles: list[str]   # titles it changed, as listed by the OLRC ("11", "11A", ...); empty when not listed
    current: bool = False

    @property
    def law(self) -> tuple[int, int]:
        congress, number = re.match(r"(\d+)-(\d+)", self.key).groups()
        return int(congress), int(number)

    @property
    def partial(self) -> bool:
        return not re.fullmatch(r"\d+-\d+", self.key)


def _iso(date: str) -> str:
    return datetime.strptime(date, "%B %d, %Y").date().isoformat()


def parse_lists(prior_html: str, current_html: str) -> list[ReleasePoint]:
    """Release points from the OLRC's prior-release-points page and its download page, oldest first."""
    points: dict[str, ReleasePoint] = {}
    for m in _ITEM.finditer(prior_html):
        titles = re.findall(r"\b(\d+[A-Z]?)\b", unescape(m.group("rest")).split("affecting", 1)[-1])
        points[m.group("key")] = ReleasePoint(m.group("key"), _iso(m.group("date")), titles)
    cur = _CURRENT.search(re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", current_html))))
    if cur:
        points[cur.group("key")] = ReleasePoint(cur.group("key"), _iso(cur.group("date")), points.get(cur.group("key"), ReleasePoint("", "", [])).titles, True)
    return sorted(points.values(), key=lambda p: (p.date, p.law))


def list_release_points() -> list[ReleasePoint]:
    prior = fetch(PRIOR_URL, refresh=True)
    current = fetch(CURRENT_URL, refresh=True)
    if prior is None or current is None:
        return []
    return parse_lists(prior.data.decode("utf-8", "replace"), current.data.decode("utf-8", "replace"))


def choose(points: list[ReleasePoint], title: int, after: str) -> list[ReleasePoint]:
    """The release points worth comparing for one title, after a date (the last annual edition's): the first one served,
    every one the OLRC lists as changing the title, and the current one. Partial release points are left out."""
    later = [p for p in points if p.date > after and not p.partial]
    if not later:
        return []
    keep = {later[0].key, later[-1].key} | {p.key for p in later if str(title) in p.titles}
    return [p for p in later if p.key in keep]


def zip_url(key: str, title: int) -> str:
    congress, number = key.split("-", 1)
    return f"https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{number}/htm_usc{title:02d}@{key}.zip"


def page_url(key: str) -> str:
    return f"https://uscode.house.gov/download/{key}.html"


def load_release_point(point: ReleasePoint, title: int) -> Optional[Edition]:
    got = fetch(zip_url(point.key, title))
    if got is None:
        return None
    archive = zipfile.ZipFile(io.BytesIO(got.data))
    name = next((n for n in archive.namelist() if n.lower().endswith(".htm")), None)
    if name is None:
        return None
    return parse_edition(
        archive.read(name), title=title, year=int(point.date[:4]), sha256=got.sha256, url=got.url, fetched_at=got.fetched_at,
        key=f"pl{point.key}", label=f"Release point {point.key}", kind="release_point", through_law=point.law,
        page=page_url(point.key),
    )
