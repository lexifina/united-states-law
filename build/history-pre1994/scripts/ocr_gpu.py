"""GPU OCR (OnnxTR: docTR detection + recognition models on onnxruntime CUDA) for the LoC US Code scans.

Runs beside ocr.py (Tesseract on CPU). Takes PDFs newest edition first, from the end of the queue (Tesseract works
from the start), writes text/<Y>/<id>.doctr.txt (pages separated by form feeds, blocks by blank lines, in docTR's
reading order). parse_ocr.py uses a doctr reading where Tesseract's is missing, and clean.py counts it as one more
independent reading. Keeps GPU use under ~90% by batching pages and pausing when utilisation is above the cap.

usage: .venv-gpu/Scripts/python ocr_gpu.py
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
TEXT = os.path.join(ROOT, "text")
YEARS = [1988, 1982, 1976, 1970, 1964, 1958, 1952, 1946, 1940, 1934, 1925]
GPU_CAP = 88


def log(msg):
    with open(os.path.join(ROOT, "logs", "ocr_gpu.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def gpu_util():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, creationflags=0x08000000)
        return int(r.stdout.strip().split("\n")[0])
    except Exception:
        return 0


def pending():
    todo = []
    for y in YEARS:
        d = os.path.join(CACHE, str(y))
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d), reverse=True):
            stem = name[:-4]
            if not name.endswith(".pdf"):
                continue
            t = os.path.join(TEXT, str(y), stem)
            if not os.path.exists(t + ".doctr.txt"):
                # first the PDFs no engine has read; then the rest, as a third reading
                todo.append((0 if not os.path.exists(t + ".tess.txt") else 1, y, name))
    return [(y, name) for _, y, name in sorted(todo, key=lambda x: x[0])]


def render(result) -> str:
    pages = []
    for page in result.pages:
        blocks = []
        for b in page.blocks:
            lines = [" ".join(w.value for w in ln.words) for ln in b.lines]
            blocks.append("\n".join(lines))
        pages.append("\n\n".join(blocks))
    return "\f".join(pages)


def main():
    import onnxruntime as ort
    ort.preload_dlls()
    from onnxtr.io import DocumentFile
    from onnxtr.models import ocr_predictor, EngineConfig
    cfg = EngineConfig(providers=[("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"])
    pred = ocr_predictor(det_arch="db_resnet50", reco_arch="parseq", det_engine_cfg=cfg, reco_engine_cfg=cfg,
                         clf_engine_cfg=cfg, assume_straight_pages=True, straighten_pages=False,
                         detect_orientation=False, resolve_blocks=True, det_bs=2, reco_bs=256)
    log("GPU OCR ready")
    pages_done = 0
    t0 = time.time()
    idle_logged = False
    while True:
        todo = pending()
        if not todo:
            if not idle_logged:
                log("queue empty; waiting"); idle_logged = True
            time.sleep(60)
            continue
        idle_logged = False
        y, name = todo[0]
        while gpu_util() > GPU_CAP:
            time.sleep(2)
        src = os.path.join(CACHE, str(y), name)
        try:
            doc = DocumentFile.from_pdf(src, scale=4)  # ~288 dpi
            res = pred(doc)
            out = os.path.join(TEXT, str(y), name[:-4] + ".doctr.txt")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out + ".part", "w", encoding="utf-8", newline="\n") as f:
                f.write(render(res))
            os.replace(out + ".part", out)
            import pymupdf
            d = pymupdf.open(src)
            with open(os.path.join(TEXT, str(y), name[:-4] + ".lura.txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write("\f".join(pg.get_text() for pg in d))
            d.close()
            pages_done += len(doc)
            if pages_done % 200 < len(doc):
                log(f"{pages_done} pages; {pages_done / (time.time() - t0):.2f} pages/s")
        except Exception as e:
            log(f"{name} failed: {e!r}")
            open(os.path.join(TEXT, str(y), name[:-4] + ".doctr.txt"), "w").close()


if __name__ == "__main__":
    main()
