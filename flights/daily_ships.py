"""Every day: turn yesterday's (UTC) hourly AIS windows (collect_ais.py) into the cube's ships.bin.

The 24 windows become one snapshot file with a key every hour (an hour with no window stays
empty, so the keys stay evenly spaced as flight_track.h expects), then pack_flights.py picks
at most CAP ships per face and writes the same CEF1 file the planes use.

Usage: python -I daily_ships.py [--day 2026-11-04] [--cap 30]
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path("/sata_hdd_24tb/ais")
SNAPS = ROOT / "snapshots"
WEB = pathlib.Path("/sata_hdd_24tb/www/html/static/tmp/cubic-earth")
LOG = pathlib.Path.home() / "logs" / "ais-daily.log"


def day_before(now):
    return (now.astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()


def day_snapshots(root, day):
    """-> ({str(t0 + 3600 h): rows} for all 24 hours, number of windows found)."""
    t0 = int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    snaps, seen = {}, 0
    for h in range(24):
        f = pathlib.Path(root) / day / f"{h:02d}.json"
        rows = []
        if f.exists():
            rows = json.loads(f.read_text())["rows"]
            seen += 1
        snaps[str(t0 + 3600 * h)] = rows
    return snaps, seen


def log(msg):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=day_before(dt.datetime.now(dt.timezone.utc)))
    ap.add_argument("--cap", type=int, default=30)
    a = ap.parse_args()
    day = a.day
    dated = WEB / f"ships-{day}.bin"
    if dated.exists():
        log(f"{day}: already done")
        return 0
    snaps, seen = day_snapshots(ROOT, day)
    if seen < 12:
        log(f"{day}: only {seen} of 24 windows, not publishing")
        return 1
    snap = SNAPS / f"{day}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(snaps, separators=(",", ":")))
    p = subprocess.run([sys.executable, "-I", str(HERE / "pack_flights.py"), str(snap), str(dated), "--cap", str(a.cap)],
                       capture_output=True, text=True)
    if p.returncode:
        log(f"{day}: pack_flights failed: {p.stderr.strip()[-300:]}")
        return 1
    tmp = WEB / ".ships.bin.new"
    shutil.copyfile(dated, tmp)
    os.replace(tmp, WEB / "ships.bin")
    log(f"{day}: {seen} of 24 windows, {p.stdout.strip()}, published ships.bin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
