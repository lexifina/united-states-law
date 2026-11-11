"""Starts a job hidden (CREATE_NO_WINDOW), at below-normal priority, outside this session's job object; appends its pid
to ../jobs.txt. stdout/stderr go to ../logs/<name>.out.

    pythonw launch.py <name> <program> [args...]
"""
import os
import subprocess
import sys
import time
from pathlib import Path

CREATE_NO_WINDOW, BELOW_NORMAL, NEW_GROUP, BREAKAWAY = 0x08000000, 0x00004000, 0x00000200, 0x01000000
root = Path(__file__).resolve().parent.parent
(root / "logs").mkdir(exist_ok=True)
name, argv = sys.argv[1], sys.argv[2:]
out = open(root / "logs" / f"{name}.out", "ab")
flags = CREATE_NO_WINDOW | BELOW_NORMAL | NEW_GROUP
try:
    p = subprocess.Popen(argv, cwd=os.getcwd(), creationflags=flags | BREAKAWAY, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
except OSError:
    p = subprocess.Popen(argv, cwd=os.getcwd(), creationflags=flags, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
with open(root / "jobs.txt", "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {p.pid} {name} {' '.join(argv)}\n")
