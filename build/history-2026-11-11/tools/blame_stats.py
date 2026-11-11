"""Who git blame credits for a title's lines at a ref: an Act (pl-*), the start-of-record edition, a later edition.

    python blame_stats.py <ref> <title> [sample size]
"""
import collections
import random
import subprocess
import sys
from pathlib import Path

CLONE = Path(__file__).resolve().parent.parent / "clone"
ref, title = sys.argv[1], sys.argv[2]
size = int(sys.argv[3]) if len(sys.argv) > 3 else 200
files = subprocess.run(["git", "ls-tree", "--name-only", f"{ref}:title-{title}"], cwd=CLONE, capture_output=True, text=True).stdout.split()
random.seed(26)
sample = sorted(random.sample(files, min(size, len(files))))
count = collections.Counter()
for f in sample:
    out = subprocess.run(["git", "blame", "--line-porcelain", ref, "--", f"title-{title}/{f}"], cwd=CLONE, capture_output=True, text=True, encoding="utf-8").stdout
    for line in out.splitlines():
        if line.startswith("author-mail "):
            mail = line[13:-1]
        elif line.startswith("author-time "):
            year = int(line.split()[1]) // 31556952 + 1970
        elif line.startswith("\t"):
            if not line[1:].strip():
                continue
            if mail.startswith("pl-"):
                kind = "law, before 2018" if year < 2018 else "law, 2018 on"
            elif mail.startswith("1994@"):
                kind = "1994 edition (start of record)"
            elif mail.startswith("2017@"):
                kind = "2017 edition"
            else:
                kind = "other edition"
            count[kind] += 1
total = sum(count.values())
print(f"{ref} title {title}: {len(sample)} files, {total} lines")
for k, v in count.most_common():
    print(f"  {k:32} {v:7}  {100 * v / total:5.1f}%")
