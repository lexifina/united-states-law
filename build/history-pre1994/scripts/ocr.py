"""OCR every downloaded LoC US Code PDF with Tesseract 5 (LSTM, eng), page by page, at the scan's own resolution.

The PDFs carry a 2008 LuraTech text layer; Tesseract 5 reads the same scans markedly better (section signs, digits,
small capitals). Both are kept: text/<year>/<id>.tess.txt (ours) and text/<year>/<id>.lura.txt (the PDF's layer),
pages separated by form feeds, so the parser can use either and the checks can compare them.

Runs alongside fetch.py: picks up PDFs as they land; exits when every fetch lane has logged DONE and nothing is left.

usage: python ocr.py [workers]
"""
import os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
TEXT = os.path.join(ROOT, "text")
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
YEARS = [1988, 1982, 1976, 1970, 1964, 1958, 1952, 1946, 1940, 1934, 1925]  # newest first: cleaning runs backward from 1994
NOWIN = 0x08000000  # CREATE_NO_WINDOW
BELOW_NORMAL = 0x00000040  # IDLE_PRIORITY_CLASS (machine shared with Lean builds)
CPU_CAP = 85.0  # start a page only while system CPU is under this (user: stay under 90%)
import threading
_gate = threading.Lock()


def wait_cpu():
    import psutil
    while True:
        with _gate:
            u = psutil.cpu_percent(interval=0.5)
        if u < CPU_CAP:
            return
        time.sleep(1.0 + (u - CPU_CAP) / 10)


def log(msg):
    with open(os.path.join(ROOT, "logs", "ocr.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def one(args):
    try:
        return _one(args)
    except Exception as e:
        log(f"{args} failed: {e!r}")
        return 0


def _one(args):
    year, name = args
    import pymupdf
    src = os.path.join(CACHE, str(year), name)
    out_dir = os.path.join(TEXT, str(year))
    stem = name[:-4]
    tess_out = os.path.join(out_dir, stem + ".tess.txt")
    if os.path.exists(tess_out):
        return 0
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        doc = pymupdf.open(src)
    except Exception as e:
        log(f"{name} open failed {e!r}")
        return 0
    lura, tess = [], []
    with tempfile.TemporaryDirectory() as td:
        for i, page in enumerate(doc):
            lura.append(page.get_text())
            imgs = page.get_images(full=True)
            dpi = 300
            if imgs:
                w = imgs[0][2]
                dpi = max(200, min(600, round(w / (page.rect.width / 72))))
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            png = os.path.join(td, f"p{i}.png")
            pix.save(png)
            # tesseract's stdout on Windows is not UTF-8 (Â§ and quotes are lost): read its own .txt file
            base = os.path.join(td, f"o{i}")
            wait_cpu()
            subprocess.run([TESS, png, base, "-l", "eng", "--psm", "3", "--dpi", str(dpi), "quiet"],
                           capture_output=True, env=env, creationflags=NOWIN | BELOW_NORMAL)
            with open(base + ".txt", encoding="utf-8", errors="replace") as f:
                tess.append(f.read())
    n = doc.page_count
    doc.close()
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, stem + ".lura.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\f".join(lura))
    tmp = tess_out + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\f".join(tess))
    os.replace(tmp, tess_out)
    return n


def pending():
    todo = []
    for y in YEARS:
        d = os.path.join(CACHE, str(y))
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if (name.endswith(".pdf") and not os.path.exists(os.path.join(TEXT, str(y), name[:-4] + ".tess.txt"))
                    and not os.path.exists(os.path.join(TEXT, str(y), name[:-4] + ".doctr.txt"))):
                todo.append((y, name))
    return todo


def fetch_done():
    p = os.path.join(ROOT, "logs", "fetch.log")
    if not os.path.exists(p):
        return False
    txt = open(p, encoding="utf-8").read()
    return all(f"{y} DONE" in txt for y in YEARS)


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 18
    pages = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        while True:
            done_flag = fetch_done()
            todo = pending()
            if not todo:
                if done_flag:
                    break
                time.sleep(60)
                continue
            for n in ex.map(one, todo, chunksize=1):
                pages += n
            log(f"batch of {len(todo)} files; {pages} pages total; {pages / max(1, time.time() - t0):.2f} pages/s")
    log(f"DONE {pages} pages")


if __name__ == "__main__":
    main()
