"""Where every scheduled airliner was, every N minutes, for one day.

Input is one day of adsb.lol globe_history (ODbL), extracted:
  cat v2026.11.03-planes-readsb-prod-0.tar.a? | tar -xf - -C DIR
DIR/traces/??/trace_full_<hex>.json are gzip JSON, format:
https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons

Usage: python -I globe_snapshots.py DIR 2026-11-03 OUT.json [--every 15]
OUT is {"<unix time>": [[lat, lon, track, callsign, type], ...], ...}.
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import pathlib
import re

AIRLINE = re.compile(r"^[A-Z]{3}[0-9][0-9A-Z]{0,3}$")  # ICAO airline code + flight number
LARGE = {"A3", "A4", "A5"}  # emitter categories for 34 t and up, heavy, B757


def is_airliner(callsign, category):
    if not callsign or not AIRLINE.match(callsign.strip()):
        return False
    return category is None or category in LARGE


def times_of_day(day, every_min):
    b = int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    return list(range(b, b + 86400, every_min * 60))


def samples(trace, base, times, tol=120):
    """Yield (time, lat, lon, track, callsign, category) for each time with a fresh airborne point within tol s."""
    flight, cat, known = None, None, []
    for p in trace:
        d = p[8] if len(p) > 8 else None
        if d:
            flight = (d.get("flight") or "").strip() or flight
            cat = d.get("category", cat)
        known.append((base + p[0], p, flight, cat))
    ts = [k[0] for k in known]
    for t in times:
        i = bisect.bisect_left(ts, t)
        near = [j for j in (i - 1, i) if 0 <= j < len(known)]
        if not near:
            continue
        j = min(near, key=lambda j: abs(ts[j] - t))
        _, p, f, c = known[j]
        if abs(ts[j] - t) > tol or p[3] == "ground" or p[3] is None or p[6] & 1:
            continue
        yield (t, p[1], p[2], p[5], f, c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("day")
    ap.add_argument("out")
    ap.add_argument("--every", type=int, default=15)
    a = ap.parse_args()
    times = times_of_day(a.day, a.every)
    out = {str(t): [] for t in times}
    n = kept = 0
    for f in sorted(pathlib.Path(a.dir, "traces").glob("*/trace_full_*.json")):
        n += 1
        try:
            j = json.loads(gzip.decompress(f.read_bytes()))
        except (OSError, ValueError):
            j = json.loads(f.read_bytes())
        hit = False
        for t, lat, lon, trk, fl, cat in samples(j["trace"], j["timestamp"], times):
            if is_airliner(fl, cat):
                out[str(t)].append([round(lat, 3), round(lon, 3), trk, fl, j.get("t")])
                hit = True
        kept += hit
    pathlib.Path(a.out).write_text(json.dumps(out, separators=(",", ":")))
    sizes = [len(v) for v in out.values()]
    print(f"traces {n}, airliners {kept}, per snapshot min {min(sizes)} max {max(sizes)}")


if __name__ == "__main__":
    main()
