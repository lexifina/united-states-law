"""Fetches and caches the official files: annual editions of a US Code title and public laws from GovInfo, and release
points from the Office of the Law Revision Counsel.

Files are cached on disk by URL, with the SHA-256 and the time each was fetched, so a build can be repeated
offline and every published fact points at the exact bytes it came from.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)"
CACHE_DIR = Path(os.environ.get("US_CODE_HISTORY_CACHE", Path(__file__).resolve().parents[2] / ".us_code_history" / "cache"))


@dataclass
class Fetched:
    url: str
    data: bytes
    sha256: str
    fetched_at: str
    from_cache: bool


def edition_url(year: int, title: int) -> str:
    return f"https://www.govinfo.gov/content/pkg/USCODE-{year}-title{title}/html/USCODE-{year}-title{title}.htm"


def edition_page(year: int, title: int) -> str:
    return f"https://www.govinfo.gov/app/details/USCODE-{year}-title{title}"


def law_url(congress: int, number: int) -> str:
    return f"https://www.govinfo.gov/content/pkg/PLAW-{congress}publ{number}/uslm/PLAW-{congress}publ{number}.xml"


def law_page(congress: int, number: int) -> str:
    return f"https://www.govinfo.gov/app/details/PLAW-{congress}publ{number}"


def _ensure_cache() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    marker = CACHE_DIR.parent / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n", encoding="utf-8")


def _cache_paths(url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{key}.bin", CACHE_DIR / f"{key}.json"


def fetch(url: str, *, refresh: bool = False, pause: float = 1.0) -> Optional[Fetched]:
    """Returns the file, from the cache unless refresh is set. None when the publisher has no such file."""
    _ensure_cache()
    body_path, meta_path = _cache_paths(url)
    if not refresh and body_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        data = body_path.read_bytes()
        return Fetched(url, data, meta["sha256"], meta["fetched_at"], True)
    for attempt in range(3):
        try:
            response = httpx.get(url, headers={"user-agent": USER_AGENT}, follow_redirects=True, timeout=120)
        except httpx.HTTPError:
            time.sleep(2 + attempt * 3)
            continue
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 + attempt * 10)
            continue
        response.raise_for_status()
        data = response.content
        # GovInfo answers a missing package with a 200 HTML error or "Page Not Found" page; a real file is XML, a zip or
        # the title's HTML.
        head = data[:8000].lower()
        if b"<title>error" in head or b"<title>page not found" in head or (url.endswith(".xml") and (not data.lstrip().startswith(b"<") or b"<html" in head)):
            return None
        fetched = Fetched(url, data, hashlib.sha256(data).hexdigest(), datetime.now(timezone.utc).isoformat(timespec="seconds"), False)
        body_path.write_bytes(data)
        meta_path.write_text(json.dumps({"url": url, "sha256": fetched.sha256, "fetched_at": fetched.fetched_at}), encoding="utf-8")
        time.sleep(pause)
        return fetched
    raise RuntimeError(f"Could not fetch {url}")


def wayback(url: str) -> Optional[str]:
    """The Internet Archive's closest capture of an official page, as an independent copy. Read-only lookup. Answers
    are cached beside the fetched files, so a law cited by many titles is looked up once."""
    _ensure_cache()
    cached = CACHE_DIR / f"wayback-{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")).get("snapshot")
    try:
        response = httpx.get("https://archive.org/wayback/available", params={"url": url}, headers={"user-agent": USER_AGENT}, timeout=30)
        snapshot = response.json().get("archived_snapshots", {}).get("closest")
        found = snapshot["url"] if snapshot and snapshot.get("available") else None
    except Exception:  # noqa: BLE001 - an archive link is a convenience; a failed lookup is not cached
        return None
    cached.write_text(json.dumps({"url": url, "snapshot": found}), encoding="utf-8")
    return found
