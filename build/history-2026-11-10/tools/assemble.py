"""Assembles branch history-full in the clone: the pre-2017 blocks (blocks/title<T>.json.gz, in the order given), then
every commit of origin/main replayed on top with the same author, committer, dates, message and file blobs, so the
final tree is main's. Main itself is not touched.

    python assemble.py <title> [<title> ...]

Checks before returning: main is linear; history-full's tree equals origin/main's tree.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONE = ROOT / "clone"
REF = "refs/heads/history-full"
COMMITTER = "Lexifina <us-code-history@lexifina.com>"


def git(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=CLONE, input=input, capture_output=True, check=True).stdout


def epoch(day: str) -> int:
    return int(datetime.fromisoformat(day + "T12:00:00+00:00").timestamp())


def quote(path: str) -> str:
    if any(c in path for c in '"\n\\') or path.startswith('"') or " " in path:
        return '"' + path.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return path


def main() -> None:
    titles = sys.argv[1:]
    main_commits = git("rev-list", "--reverse", "--topo-order", "--parents", "origin/main").decode().split("\n")
    rows = [r.split() for r in main_commits if r.strip()]
    assert all(len(r) <= 2 for r in rows), "main has merges"
    for k, r in enumerate(rows[1:], 1):
        assert r[1] == rows[k - 1][0], "main is not one line"
    stream = ROOT / "scratch" / "history-full.fi"
    stream.parent.mkdir(exist_ok=True)
    count = 0
    with open(stream, "wb") as f:
        w = f.write
        w(f"reset {REF}\n".encode())
        first = True
        for t in titles:
            with gzip.open(ROOT / "blocks" / f"title{t}.json.gz", "rt", encoding="utf-8") as g:
                commits = json.load(g)
            for c in commits:
                msg = c["message"].encode("utf-8")
                w(f"commit {REF}\n".encode())
                w(f"author {c['author']} <{c['email']}> {epoch(c['date'])} +0000\n".encode("utf-8"))
                w(f"committer {COMMITTER} {epoch(c['date'])} +0000\n".encode())
                w(f"data {len(msg)}\n".encode() + msg + b"\n")
                for path, text in sorted(c["files"].items()):
                    if text is None:
                        w(f"D {quote(path)}\n".encode("utf-8"))
                    else:
                        b = text.encode("utf-8")
                        w(f"M 100644 inline {quote(path)}\n".encode("utf-8"))
                        w(f"data {len(b)}\n".encode() + b + b"\n")
                w(b"\n")
                count += 1
                first = False
        # Main, replayed: the same commit objects' metadata and blobs, on top of the blocks.
        for r in rows:
            sha = r[0]
            raw = git("cat-file", "commit", sha)
            header, _, message = raw.partition(b"\n\n")
            author = committer = None
            for line in header.split(b"\n"):
                if line.startswith(b"author "):
                    author = line[7:]
                elif line.startswith(b"committer "):
                    committer = line[10:]
                elif line.startswith((b"tree ", b"parent ")):
                    continue
                else:
                    raise SystemExit(f"unexpected header in {sha}: {line[:40]!r}")
            w(f"commit {REF}\n".encode())
            w(b"author " + author + b"\n")
            w(b"committer " + committer + b"\n")
            w(f"data {len(message)}\n".encode() + message + b"\n")
            diff = git("diff-tree", "-r", "--root", "--no-commit-id", "--no-renames", "-z", sha).split(b"\0")
            k = 0
            while k < len(diff) - 1:
                meta, path = diff[k].decode(), diff[k + 1].decode("utf-8")
                k += 2
                _, newmode, _, newsha, status = meta.lstrip(":").split()
                if status == "D":
                    w(f"D {quote(path)}\n".encode("utf-8"))
                else:
                    w(f"M {newmode} {newsha} {quote(path)}\n".encode("utf-8"))
            w(b"\n")
            count += 1
    with open(stream, "rb") as f:
        subprocess.run(["git", "fast-import", "--quiet", "--force"], cwd=CLONE, stdin=f, check=True)
    stream.unlink()
    a = git("rev-parse", "origin/main^{tree}").strip()
    b = git("rev-parse", "history-full^{tree}").strip()
    print(f"{count} commits; history-full tree {b.decode()} {'==' if a == b else '!='} main tree {a.decode()}")
    if a != b:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
