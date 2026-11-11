"""Single-lane, rate-limited fetch of the LoC US Code scans (replaces the 11-lane fetch.py, which tripped
tile.loc.gov's rate limit on 2026-11-11 18:07 and got a Cloudflare 429 challenge).

- one request every GAP seconds in total (no parallel lanes); a 429/403 or a Cloudflare challenge pauses 20 minutes;
  three challenges in a row stop the run (we never try to pass a challenge).
- waits at start until a test request is answered (one try every 15 minutes).
- newest edition first. Per title: tries chunk 1-3 in volumes v..v+2 to find the start; follows chunks with up to
  MISSES consecutive 404s (chapters can be skipped), and follows a title into the next volume.
- resumable: cache/<Y>/probes.jsonl (200/404 only) and the PDFs on disk.

usage: python fetch2.py [years...]
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = "https://tile.loc.gov/storage-services/service/ll/uscode"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
GAP = 2.0
MISSES = 6
UA = "lexifina-law-history/1.0 (US Code history research; one request at a time)"
YEARS = [1988, 1982, 1976, 1970, 1964, 1958, 1952, 1946, 1940, 1934, 1925]


def log(msg):
    with open(os.path.join(ROOT, "logs", "fetch.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


class Blocked(Exception):
    pass


class Fetch:
    def __init__(self):
        self.last = 0.0
        self.challenges = 0

    def get(self, u):
        """(status, body). Retries network errors; pauses on 429/403/challenge."""
        for attempt in range(8):
            d = time.time() - self.last
            if d < GAP:
                time.sleep(GAP - d)
            self.last = time.time()
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r:
                    body = r.read()
                    self.challenges = 0
                    return r.status, body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.challenges = 0
                    return 404, None
                if e.code in (429, 403) or e.headers.get("cf-mitigated"):
                    self.challenges += 1
                    log(f"rate limited ({e.code}, cf-mitigated={e.headers.get('cf-mitigated')}); pausing 20 min [{self.challenges}]")
                    if self.challenges >= 3:
                        raise Blocked()
                    time.sleep(1200)
                    continue
                time.sleep(15 * (attempt + 1))
            except Exception as e:
                log(f"network error {e!r} on {u}")
                time.sleep(15 * (attempt + 1))
        return -1, None


F = Fetch()


class Year:
    def __init__(self, year):
        self.year = year
        self.dir = os.path.join(CACHE, str(year))
        os.makedirs(self.dir, exist_ok=True)
        self.pp = os.path.join(self.dir, "probes.jsonl")
        self.probes = {}
        if os.path.exists(self.pp):
            for line in open(self.pp, encoding="utf-8"):
                r = json.loads(line)
                if r["status"] in (200, 404):
                    self.probes[r["id"]] = r
        self.pf = open(self.pp, "a", encoding="utf-8")

    def has(self, vol, title, chunk):
        i = f"uscode{self.year}-{vol:03d}{title:03d}{chunk:03d}"
        p = os.path.join(self.dir, i + ".pdf")
        r = self.probes.get(i)
        if r and r["status"] == 404:
            return False
        if r and r["status"] == 200 and os.path.exists(p):
            return True
        u = f"{BASE}/{i[:16]}/{i}/{i}.pdf"
        st, body = F.get(u)
        if st == 200 and body:
            with open(p + ".part", "wb") as f:
                f.write(body)
            os.replace(p + ".part", p)
        if st in (200, 404):
            rec = {"id": i, "status": st, "len": len(body) if body else None, "vol": vol, "title": title, "chunk": chunk}
            self.probes[i] = rec
            self.pf.write(json.dumps(rec) + "\n"); self.pf.flush()
        return st == 200

    def run(self):
        vol, n = 1, 0
        for title in range(1, 55):
            start = None
            for v in range(vol, vol + 3):
                for c in (1, 2, 3):
                    if self.has(v, title, c):
                        start = (v, c); break
                if start:
                    break
            if not start:
                log(f"{self.year} title {title}: no start found in vols {vol}-{vol + 2}")
                continue
            vol, chunk = start
            misses, last = 0, chunk
            while misses < MISSES:
                if self.has(vol, title, chunk):
                    n += 1; misses = 0; last = chunk; chunk += 1; continue
                if self.has(vol + 1, title, chunk):
                    vol += 1; continue
                if self.has(vol + 1, title, 1) and not self.probes.get(f"uscode{self.year}-{vol + 1:03d}{title:03d}001", {}).get("seen"):
                    self.probes[f"uscode{self.year}-{vol + 1:03d}{title:03d}001"]["seen"] = True
                    vol += 1; chunk = 1; continue
                misses += 1; chunk += 1
            log(f"{self.year} title {title}: last chunk {last} in vol {vol}; {n} files this run")
        log(f"{self.year} DONE")


def main():
    years = [int(y) for y in sys.argv[1:]] or YEARS
    test = f"{BASE}/uscode1934-00100/uscode1934-001001001/uscode1934-001001001.pdf"
    while True:
        try:
            req = urllib.request.Request(test, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status == 200:
                    break
        except Exception as e:
            log(f"waiting for the rate limit to lift: {e!r}")
        time.sleep(3600)
    log("rate limit lifted; starting")
    try:
        for y in years:
            Year(y).run()
    except Blocked:
        log("STOPPED: challenged three times in a row; not retrying automatically")
        return
    log("ALL DONE")


if __name__ == "__main__":
    main()
