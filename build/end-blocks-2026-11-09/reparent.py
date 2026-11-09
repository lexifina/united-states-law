"""Put a generated end block onto the published history when its first commit differs from the one already pushed:
one correction commit restating the starting text (tree = the generated first commit's tree, parent = the pushed
one), then every later generated commit re-created with the same tree, author, committer, dates and message on the
new parent. Writes refs/heads/append-fixed; nothing is pushed.

    python reparent.py <repo> <pushed first commit> <generated first commit> <generated tip> <message file>
"""
import os
import subprocess
import sys

repo, pushed, gen_first, gen_tip, msg_file = sys.argv[1:6]


def git(*a, env=None, input=None):
    r = subprocess.run(["git", *a], cwd=repo, capture_output=True, env=env, input=input)
    if r.returncode:
        raise SystemExit(f"git {' '.join(a[:3])} failed: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout


def header(commit):
    raw = git("cat-file", "commit", commit)
    head, _, message = raw.partition(b"\n\n")
    fields = {}
    for line in head.split(b"\n"):
        k, _, v = line.partition(b" ")
        fields.setdefault(k.decode(), v.decode("utf-8"))
    return fields, message


def ident(v):
    name, _, rest = v.partition(" <")
    email, _, when = rest.partition("> ")
    return name, email, when


def make(tree, parent, author, committer, message):
    an, ae, ad = ident(author)
    cn, ce, cd = ident(committer)
    env = {**os.environ, "GIT_AUTHOR_NAME": an, "GIT_AUTHOR_EMAIL": ae, "GIT_AUTHOR_DATE": ad,
           "GIT_COMMITTER_NAME": cn, "GIT_COMMITTER_EMAIL": ce, "GIT_COMMITTER_DATE": cd}
    return git("commit-tree", tree, "-p", parent, "-F", "-", env=env, input=message).decode().strip()


f, _ = header(gen_first)
pf, _ = header(pushed)
first_tree = git("rev-parse", f"{gen_first}^{{tree}}").decode().strip()
message = open(msg_file, "rb").read()
author = os.environ["FIX_AUTHOR"] + " " + pf["author"].rpartition("> ")[2]
fix = make(first_tree, pushed, author, pf["committer"], message)
parent = fix
for c in git("rev-list", "--reverse", f"{gen_first}..{gen_tip}").decode().split():
    h, m = header(c)
    tree = git("rev-parse", f"{c}^{{tree}}").decode().strip()
    parent = make(tree, parent, h["author"], h["committer"], m)
git("update-ref", "refs/heads/append-fixed", parent)
print(fix, parent)
