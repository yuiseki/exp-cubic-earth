"""Every day: fetch yesterday's adsb.lol globe_history (ODbL) and publish the cube's flight file.

1. one GitHub API call to find the day's release (prod, or staging when prod is missing or much smaller)
2. download its parts (about 3.5 GB) from GitHub's release storage, resuming a part once if it breaks
3. extract, sample airliners every 15 min with ocean gaps bridged (globe_snapshots.py --fill)
4. pack 60 per face (pack_flights.py) to WEB/flights-<day>.bin and replace WEB/flights.bin (#J reads it)
5. keep the snapshots (about 16 MB), delete that day's work directory (archive and extract)

The downloads come from GitHub, not adsb.lol's own servers. The only rate limit is the API's
(60 an hour without a token, shown in x-ratelimit-* headers); when it is short or refused, this
run stops and the next one tries again. A finished day is skipped, so reruns are cheap.

Usage: python -I daily_adsblol.py [--day 2026-11-03]
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path("/sata_hdd_24tb/adsblol")
WORK, SNAPS = ROOT / "work", ROOT / "snapshots"
WEB = pathlib.Path("/sata_hdd_24tb/www/html/static/tmp/cubic-earth")
LOG = pathlib.Path.home() / "logs" / "adsblol-daily.log"
CAP = 60


def day_before(now):
    return (now.astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()


def pick_release(day, releases):
    """-> (tag, part urls in order) for the day, or None. Prod unless staging is over 1.3x its size."""
    stem = "v" + day.replace("-", ".") + "-planes-readsb-"
    found = {}
    for r in releases:
        for kind in ("prod", "staging"):
            if r["tag_name"].startswith(stem + kind + "-") and r["assets"]:
                found.setdefault(kind, r)
    if not found:
        return None
    size = {k: sum(a["size"] for a in r["assets"]) for k, r in found.items()}
    kind = "staging" if "prod" not in found or size.get("staging", 0) > 1.3 * size["prod"] else "prod"
    r = found[kind]
    return r["tag_name"], [a["browser_download_url"] for a in sorted(r["assets"], key=lambda a: a["name"])]


def rate_wait(status, headers, now):
    """Seconds until the GitHub API may be asked again; 0 means go ahead."""
    h = {k.lower(): v for k, v in headers.items()}
    if "retry-after" in h:
        return int(h["retry-after"])
    remaining, reset = h.get("x-ratelimit-remaining"), h.get("x-ratelimit-reset")
    if remaining is not None and int(remaining) <= 1 and reset:
        return max(int(reset) - now, 0)
    if status in (403, 429):
        return 3600
    return 0


def log(msg):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def releases(year):
    url = f"https://api.github.com/repos/adsblol/globe_history_{year}/releases?per_page=20"
    req = urllib.request.Request(url, headers={"User-Agent": "exp-cubic-earth-daily", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), None


def download(url, dest):
    for attempt in (1, 2):  # the second try resumes the part where it broke
        r = subprocess.run(["curl", "-sSfL", "-C", "-", "-o", str(dest), url])
        if r.returncode == 0:
            return True
        log(f"download {dest.name} failed (curl {r.returncode}, try {attempt})")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=day_before(dt.datetime.now(dt.timezone.utc)))
    a = ap.parse_args()
    day = a.day
    snap, dated = SNAPS / f"{day}.json", WEB / f"flights-{day}.bin"
    if snap.exists() and dated.exists():
        log(f"{day}: already done")
        return 0
    status, headers, rs = releases(day[:4])
    wait = rate_wait(status, headers, int(time.time()))
    if wait or status != 200:
        log(f"{day}: GitHub API {status}, wait {wait} s; next run will try again")
        return 0
    pick = pick_release(day, rs)
    if not pick:
        log(f"{day}: not published yet")
        return 0
    tag, urls = pick
    work = WORK / day
    (work / "x").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    parts = [work / u.rsplit("/", 1)[1] for u in urls]
    for u, p in zip(urls, parts):
        if not download(u, p):
            log(f"{day}: giving up on {tag} for this run (partial parts kept to resume)")
            return 1
    log(f"{day}: {tag} {sum(p.stat().st_size for p in parts) >> 20} MB in {time.time() - t0:.0f} s")
    cat = subprocess.Popen(["cat", *map(str, parts)], stdout=subprocess.PIPE)
    tar = subprocess.run(["tar", "-xf", "-", "-C", str(work / "x")], stdin=cat.stdout)
    cat.stdout.close()
    if cat.wait() or tar.returncode:
        log(f"{day}: extract failed")
        return 1
    SNAPS.mkdir(parents=True, exist_ok=True)
    py = [sys.executable, "-I"]
    s = subprocess.run(py + [str(HERE / "globe_snapshots.py"), str(work / "x"), day, str(snap), "--every", "15", "--fill"],
                       capture_output=True, text=True)
    if s.returncode:
        log(f"{day}: globe_snapshots failed: {s.stderr.strip()[-300:]}")
        return 1
    log(f"{day}: {s.stdout.strip()}")
    p = subprocess.run(py + [str(HERE / "pack_flights.py"), str(snap), str(dated), "--cap", str(CAP)], capture_output=True, text=True)
    if p.returncode:
        log(f"{day}: pack_flights failed: {p.stderr.strip()[-300:]}")
        return 1
    log(f"{day}: {p.stdout.strip()}")
    latest = WEB / "flights.bin"
    tmp = WEB / ".flights.bin.new"
    shutil.copyfile(dated, tmp)
    os.replace(tmp, latest)  # #J never sees a half-written file
    shutil.rmtree(work)
    log(f"{day}: published {latest} ({dated.name}), work deleted, {time.time() - t0:.0f} s in all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
