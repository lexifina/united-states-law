"""Builds the given titles' blocks one after another (title 26 with --from1986). python build_many.py <titles>"""
import subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
for t in sys.argv[1:]:
    with open(HERE.parent / "logs" / f"build{t}.log", "w", encoding="utf-8") as out:
        rc = subprocess.call([sys.executable, "-X", "utf8", str(HERE / "build_block.py"), t] + (["--from1986"] if t == "26" else []), cwd=HERE, stdout=out, stderr=subprocess.STDOUT)
    print(t, rc, flush=True)
