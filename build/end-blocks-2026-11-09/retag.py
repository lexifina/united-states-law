"""Move the local-only law tags that point into a generated block onto the matching commits of its re-parented copy
(same order, same trees). Tags already on the remote are never touched.

    python retag.py <repo> <generated first> <generated tip> <fixed first (the correction)> <fixed tip> <remote tags file>
"""
import subprocess
import sys

repo, g1, gtip, f1, ftip, remote_file = sys.argv[1:7]
run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True).stdout  # noqa: E731
gen = [g1] + run("rev-list", "--reverse", f"{g1}..{gtip}").split()
fixed = [f1] + run("rev-list", "--reverse", f"{f1}..{ftip}").split()
assert len(gen) == len(fixed), (len(gen), len(fixed))
for a, b in zip(gen, fixed):
    assert run("rev-parse", f"{a}^{{tree}}") == run("rev-parse", f"{b}^{{tree}}"), (a, b)
where = {run("rev-parse", a).strip(): b for a, b in zip(gen, fixed)}
remote = set(open(remote_file, encoding="utf-8").read().split())
moved = 0
for line in run("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/tags/").splitlines():
    name, sha = line.split()
    if name in remote or sha not in where:
        continue
    run("tag", "-f", name, where[sha])
    moved += 1
print(f"{moved} tags moved onto the re-parented block")
