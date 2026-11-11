"""Puts the pre-1994 blocks in front of united-states-law's published history, on branch history-pre1994 of ./clone.

    python assemble_pre.py <title> [<title> ...]

1. The blocks (blocks/title<T>.json.gz, in the order given) as new commits.
2. Every commit of origin/main replayed on top with the same author, committer, dates, message and blobs, except:
   - a title's "start of this record" edition commit (1994/1995) when that title has a block: the block already ends
     at exactly that text, so the commit would change nothing;
   - for title 26 (when it has a block): the Internal Revenue Code of 1986 reconstruction (its start commit and the
     per-law commits marked "Reconstructed-from: 1994"), which the printed 1982 and 1988 editions now replace.
   A skipped commit's changes are checked to be already in the tree; any path that is not is replayed anyway.
3. Tags: every tag is moved to the replayed commit; a tag on a skipped commit goes to the block commit of the same
   law when there is one, else to the replayed commit before it. New law tags for the block's laws.
Checks: the final tree equals origin/main's tree.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLONE = os.path.join(ROOT, "clone")
REF = "refs/heads/history-pre1994"
COMMITTER = "Lexifina <us-code-history@lexifina.com>"


def git(*args, input=None) -> bytes:
    return subprocess.run(["git", *args], cwd=CLONE, input=input, capture_output=True, check=True).stdout


_PRE70 = [0]


def epoch(day: str) -> int:
    """Noon UTC on the day. Git cannot store dates before 1970: those are clamped to 1 January 1970, one second
    apart in commit order (the convention of every global-law corpus); the In-force trailer keeps the real day."""
    t = int(datetime.fromisoformat(day + "T12:00:00+00:00").timestamp())
    if t < 0:
        _PRE70[0] += 1
        return _PRE70[0]
    return t


def quote(path: str) -> str:
    if any(c in path for c in '"\n\\') or path.startswith('"') or " " in path:
        return '"' + path.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return path


def blob_sha(text: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(text) + text).hexdigest()


def main() -> None:
    titles = [int(t) for t in sys.argv[1:]]
    rows = [r.split() for r in git("rev-list", "--reverse", "--topo-order", "--parents", "origin/main").decode().split("\n") if r.strip()]
    assert all(len(r) <= 2 for r in rows), "merges in main"
    stream = os.path.join(ROOT, "scratch", "pre1994.fi")
    marks = os.path.join(ROOT, "scratch", "pre1994.marks")
    os.makedirs(os.path.dirname(stream), exist_ok=True)
    state: dict[str, str] = {}  # path -> blob sha (what the tree holds as the stream is written)
    mark = 0
    block_marks: dict[str, int] = {}     # law email -> last block commit mark
    block_law_dates: list[tuple[str, str, int]] = []
    replay_mark: dict[str, int] = {}     # main sha -> mark
    skipped: list[str] = []
    titles_with_block = set(titles)
    with open(stream, "wb") as f:
        w = f.write
        w(f"reset {REF}\n".encode())
        for t in titles:
            with gzip.open(os.path.join(ROOT, "blocks", f"title{t}.json.gz"), "rt", encoding="utf-8") as g:
                commits = json.load(g)
            for c in commits:
                mark += 1
                msg = c["message"].encode("utf-8")
                w(f"commit {REF}\nmark :{mark}\n".encode())
                ts = epoch(c["date"])
                w(f"author {c['author']} <{c['email']}> {ts} +0000\n".encode("utf-8"))
                w(f"committer {COMMITTER} {ts} +0000\n".encode())
                w(f"data {len(msg)}\n".encode() + msg + b"\n")
                for path, text in sorted(c["files"].items()):
                    if text is None:
                        w(f"D {quote(path)}\n".encode("utf-8"))
                        state.pop(path, None)
                    else:
                        b = text.encode("utf-8")
                        w(f"M 100644 inline {quote(path)}\n".encode("utf-8"))
                        w(f"data {len(b)}\n".encode() + b + b"\n")
                        state[path] = blob_sha(b)
                w(b"\n")
                block_marks[c["email"]] = mark
                block_law_dates.append((c["email"], c["date"], mark))
        # all of main's diffs in one pass, and the raw commits through one cat-file stream
        raw_log = git("log", "--reverse", "--topo-order", "--raw", "-r", "--root", "--no-renames", "-z",
                      "--no-abbrev", "--format=%x01%H", "origin/main")
        diffs: dict[str, list] = {}
        for chunk in raw_log.split(b"\x01")[1:]:
            sha_b, _, rest = chunk.partition(b"\0") if b"\0" in chunk[:41] else chunk.partition(b"\n")
            sha_ = sha_b.strip().decode()
            parts = rest.lstrip(b"\n").split(b"\0")
            ch = []
            k = 0
            while k < len(parts) - 1:
                meta = parts[k].decode().strip()
                if not meta.startswith(":"):
                    k += 1
                    continue
                path = parts[k + 1].decode("utf-8")
                k += 2
                _, newmode, _, newsha, status = meta.lstrip(":").split()
                ch.append((status, newmode, newsha, path))
            diffs[sha_] = ch
        cat = subprocess.Popen(["git", "cat-file", "--batch"], cwd=CLONE, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        def raw_commit(s: str) -> bytes:
            cat.stdin.write(s.encode() + b"\n"); cat.stdin.flush()
            hdr = cat.stdout.readline().split()
            n = int(hdr[2])
            data = cat.stdout.read(n)
            cat.stdout.read(1)
            return data

        for r in rows:
            sha = r[0]
            raw = raw_commit(sha)
            header, _, message = raw.partition(b"\n\n")
            author = committer = None
            for line in header.split(b"\n"):
                if line.startswith(b"author "):
                    author = line[7:]
                elif line.startswith(b"committer "):
                    committer = line[10:]
            subject = message.split(b"\n", 1)[0].decode("utf-8", "replace")
            email = re.search(rb"<([^>]*)>", author).group(1).decode()
            changes = diffs[sha]
            tnums = {int(m.group(1)) for _, _, _, p in changes for m in [re.match(r"title-(\d+)/", p)] if m}
            skip = False
            if tnums and tnums <= titles_with_block:
                if re.search(r"the start of this record", subject) and re.match(r"(1994|1995)@uscode-version", email):
                    skip = True
                if 26 in titles_with_block and tnums == {26} and (
                        email == "irc-1986@uscode-version.invalid" or b"\nReconstructed-from: 1994" in message):
                    skip = True
            if skip:
                # its changes must already be in the tree; anything that is not gets replayed in the next commit
                left = [(s, m, b, p) for s, m, b, p in changes if (s == "D" and p in state) or (s != "D" and state.get(p) != b)]
                skipped.append(sha)
                if not left:
                    continue
                message = (message.rstrip(b"\n") + b"\n\nReplayed in part: the record before 1994 already holds "
                           b"the rest of this commit's text.\n")
                changes = left
            mark += 1
            replay_mark[sha] = mark
            w(f"commit {REF}\nmark :{mark}\n".encode())
            w(b"author " + author + b"\n")
            w(b"committer " + committer + b"\n")
            w(f"data {len(message)}\n".encode() + message + b"\n")
            for status, newmode, newsha, path in changes:
                if status == "D":
                    w(f"D {quote(path)}\n".encode("utf-8"))
                    state.pop(path, None)
                else:
                    w(f"M {newmode} {newsha} {quote(path)}\n".encode("utf-8"))
                    state[path] = newsha
            w(b"\n")
    subprocess.run(["git", "fast-import", "--quiet", "--force", f"--export-marks={marks}"], cwd=CLONE,
                   stdin=open(stream, "rb"), check=True)
    os.unlink(stream)
    m2sha = {}
    for line in open(marks, encoding="utf-8"):
        mk, s = line.split()
        m2sha[int(mk[1:])] = s
    old_to_new = {old: m2sha[mk] for old, mk in replay_mark.items()}
    # tags
    tag_moves = []
    order = [r[0] for r in rows]
    for line in git("for-each-ref", "--format=%(refname) %(objectname) %(objecttype) %(*objectname)", "refs/tags").decode().splitlines():
        ref, obj, typ, peeled = (line.split() + [""])[:4]
        target = peeled or obj
        if target in old_to_new:
            new = old_to_new[target]
        elif target in skipped:
            email = re.search(r"<([^>]*)>", git("log", "-1", "--format=%an <%ae>", target).decode()).group(1)
            if email in block_marks:
                new = m2sha[block_marks[email]]
            else:
                i = order.index(target)
                prev = next((old_to_new[o] for o in reversed(order[:i]) if o in old_to_new), None)
                new = prev
        else:
            continue  # a tag outside main (archive branches): left as it is
        if new:
            tag_moves.append((ref, new))
    for ref, new in tag_moves:
        git("update-ref", ref, new)
    # law tags for the block's laws (not already tagged)
    have = set(git("tag").decode().split())
    latest: dict[str, tuple[str, int]] = {}
    for email, day, mk in block_law_dates:
        m = re.match(r"(pl-(\d+-\d+)|act-[\d\-]+(?:-ch\d+)?|reorg-\d+-\d+)@public-law\.invalid", email)
        if not m:
            continue
        name = m.group(2) or m.group(1)
        tag = f"law/{name}@{day}"
        if tag not in have:
            git("tag", tag, m2sha[mk]); have.add(tag)
        if name not in latest or day >= latest[name][0]:
            latest[name] = (day, mk)
    for name, (day, mk) in latest.items():
        if f"law/{name}" not in have:
            git("tag", f"law/{name}", m2sha[mk])
    with open(os.path.join(ROOT, "scratch", "old-to-new.tsv"), "w", encoding="utf-8") as f:
        for old in order:
            f.write(f"{old}\t{old_to_new.get(old, '(folded into the record before 1994)')}\n")
    a = git("rev-parse", "origin/main^{tree}").strip().decode()
    b = git("rev-parse", "history-pre1994^{tree}").strip().decode()
    n = git("rev-list", "--count", "history-pre1994").strip().decode()
    print(f"history-pre1994: {n} commits; {len(skipped)} main commits folded; tree {b}; main tree {a}; "
          f"{'SAME TREE' if a == b else 'TREES DIFFER'}")
    if a != b:
        print(git("diff", "--stat", "origin/main", "history-pre1994").decode()[-3000:])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
