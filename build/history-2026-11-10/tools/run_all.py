"""Builds every title's pre-2017 block as its data arrives, and every 15 minutes (when there is something new)
reassembles history-full (title 26 first, then the others by number) and pushes it with --force-with-lease. Main is
never touched. Create STOP-RUN beside this file to stop after the current step.

    python run_all.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLONE = ROOT / "clone"
TITLES = [26] + [t for t in range(1, 55) if t not in (26, 53)]
PUSH_EVERY = 15 * 60


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def log(msg: str) -> None:
    with open(ROOT / "logs" / "run_all.log", "a", encoding="utf-8") as f:
        f.write(f"{now()} {msg}\n")


def status(phase: str, done: list[int], nxt: str) -> None:
    with open(ROOT / "STATUS.txt", "a", encoding="utf-8") as f:
        f.write(f"{now()} | phase: {phase} | earliest: 1995-01-04 (1994 edition) for every title built | titles done: "
                f"{len(done)} ({', '.join(map(str, done))}) | next: {nxt}\n")


def ready(t: int) -> bool:
    d = ROOT / "data" / f"title{t}"
    return (d / "2017.json.gz").exists()


def built(t: int) -> bool:
    return (ROOT / "blocks" / f"title{t}.json.gz").exists()


def pushed_sha() -> str:
    out = subprocess.run(["git", "ls-remote", "origin", "refs/heads/history-full"], cwd=CLONE, capture_output=True, text=True).stdout
    return out.split()[0] if out.strip() else ""


def main() -> None:
    failed: set[int] = set()
    last_push = 0.0
    pushed: list[int] = [26] if built(26) else []
    while True:
        if (HERE / "STOP-RUN").exists():
            log("STOP")
            return
        todo = [t for t in TITLES if not built(t) and t not in failed]
        for t in todo:
            if not ready(t):
                continue
            log(f"build title {t}")
            with open(ROOT / "logs" / f"build{t}.log", "w", encoding="utf-8") as out:
                rc = subprocess.call([sys.executable, "-X", "utf8", str(HERE / "build_block.py"), str(t)], cwd=HERE, stdout=out, stderr=subprocess.STDOUT)
            if rc != 0:
                failed.add(t)
                log(f"title {t} FAILED rc={rc} (logs/build{t}.log)")
            else:
                rep = json.loads((ROOT / "blocks" / f"title{t}.report.json").read_text(encoding="utf-8"))
                log(f"title {t} built: {rep['commits']} commits, law {rep.get('law', 0)}, edition {rep.get('edition', 0)}")
            if (HERE / "STOP-RUN").exists():
                break
        done = [t for t in TITLES if built(t)]
        remaining = [t for t in TITLES if not built(t) and t not in failed]
        due = time.time() - last_push > PUSH_EVERY or not remaining
        if done != pushed and due:
            log(f"assemble {done}")
            with open(ROOT / "logs" / "assemble.log", "a", encoding="utf-8") as out:
                rc = subprocess.call([sys.executable, "-X", "utf8", str(HERE / "assemble.py"), *map(str, done)], cwd=HERE, stdout=out, stderr=subprocess.STDOUT)
            if rc != 0:
                log("assemble FAILED (logs/assemble.log); not pushed")
                status("assemble failed, not pushed", pushed, "look at logs/assemble.log")
                return
            lease = pushed_sha()
            p = subprocess.run(["git", "push", f"--force-with-lease=refs/heads/history-full:{lease}", "origin",
                                "refs/heads/history-full:refs/heads/history-full"], cwd=CLONE, capture_output=True, text=True)
            log(f"push rc={p.returncode} {p.stderr.strip()[-200:]}")
            if p.returncode == 0:
                pushed = done
                last_push = time.time()
                sha = pushed_sha()[:9]
                status(f"pushed history-full {sha} (tree == main)", done,
                       "remaining " + (", ".join(map(str, remaining)) or "none") + (f"; failed {sorted(failed)}" if failed else ""))
        if not remaining and done == pushed:
            log(f"all done; failed {sorted(failed)}")
            status("all titles built and pushed", done, f"final report; failed {sorted(failed)}" if failed else "final report")
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
