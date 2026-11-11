"""Runs parse -> clean chain -> block for every title (or those given), several titles at once.

    python run_all.py [--jobs N] [titles...]

Per title: parse_ocr.py for each edition that has OCR text for the title, clean.py from the newest edition back
(anchored on 1994, or 1995 for titles 7, 28, 39), then build_pre.py. Logs to logs/run_all.log; a title's failure is
logged and the others go on. Waits while system CPU is above 85% before starting a title (user: stay under 90%).
"""
import os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
EDITIONS = [1988, 1982, 1976, 1970, 1964, 1958, 1952, 1946, 1940, 1934, 1925]
NOWIN = 0x08000000


def log(msg):
    with open(os.path.join(ROOT, "logs", "run_all.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def run(args):
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError(f"{' '.join(args)}: {r.stderr[-1500:]}")
    return r.stdout.strip()


def has_text(y, t):
    d = os.path.join(ROOT, "text", str(y))
    if not os.path.isdir(d):
        return False
    pre = f"uscode{y}-"
    return any(n.startswith(pre) and n[len(pre) + 3:len(pre) + 6] == f"{t:03d}" and n.endswith((".tess.txt", ".doctr.txt"))
               for n in os.listdir(d))


def title(t):
    import psutil
    while psutil.cpu_percent(interval=1) > 85:
        time.sleep(5)
    try:
        years = [y for y in EDITIONS if has_text(y, t)]
        for y in years:
            run(["scripts/parse_ocr.py", str(y), str(t)])
        prev = 1995 if t in (7, 28, 39) else 1994
        anchor = os.path.join(ROOT, "data", f"title{t}", f"{prev}.json.gz")
        if not os.path.exists(anchor):
            # a title gone before 1994: the newest edition is cleaned against nothing (kept as read)
            os.makedirs(os.path.dirname(anchor), exist_ok=True)
            import gzip, json
            with gzip.open(anchor, "wt", encoding="utf-8") as f:
                json.dump({"title": t, "year": prev, "sections": {}, "url": [], "through": None}, f)
        newer = []
        for y in years:
            run(["scripts/clean.py", str(t), str(y), str(prev), *[str(x) for x in newer]])
            newer.insert(0, prev)
            prev = y
        out = run(["scripts/build_pre.py", str(t)])
        log(f"title {t}: editions {years}; {out.splitlines()[-1] if out else ''}")
    except Exception as e:
        log(f"title {t} FAILED: {e}")


def main():
    args = sys.argv[1:]
    jobs = 8
    if args[:1] == ["--jobs"]:
        jobs, args = int(args[1]), args[2:]
    titles = [int(a) for a in args] or [t for t in range(1, 55) if t != 53]
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(title, titles))
    log("run done")


if __name__ == "__main__":
    main()
