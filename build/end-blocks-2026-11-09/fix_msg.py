import subprocess
import sys

repo, a, b = sys.argv[1:4]
names = subprocess.run(["git", "diff", "--name-only", a, b], cwd=repo, capture_output=True, text=True, check=True).stdout.split()
text = open("fix-msg.txt", encoding="utf-8").read()
body, _, trailers = text.rpartition("\n\nKind: correction")
files = "\n".join(f"- {n}" for n in names)
out = f"{body}\n\nFiles restated ({len(names)}):\n\n{files}\n\nKind: correction{trailers}"
open("fix-msg-full.txt", "w", encoding="utf-8", newline="\n").write(out)
print(len(names))
