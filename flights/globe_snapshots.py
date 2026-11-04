"""Where every scheduled airliner was, every N minutes, for one day.

Input is one day of adsb.lol globe_history (ODbL), extracted:
  cat v2026.11.03-planes-readsb-prod-0.tar.a? | tar -xf - -C DIR
DIR/traces/??/trace_full_<hex>.json are gzip JSON, format:
https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons

Usage: python -I globe_snapshots.py DIR 2026-11-03 OUT.json [--every 15] [--fill]
OUT is {"<unix time>": [[lat, lon, track, callsign, type, filled], ...], ...}; filled is 1 for a
great-circle point bridging a gap.
Receivers are on land, so oceans are empty without --fill.
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
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


GAP_KT = (250, 650)   # implied ground speed for a gap to count as one cruise, not a stop
GAP_MAX_S = 16 * 3600


def gc_interp(lat1, lon1, lat2, lon2, f):
    """Point a fraction f of the way along the great circle."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = [math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1)]
    b = [math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2)]
    w = math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)))))
    if w < 1e-12:
        return lat1, lon1
    ka, kb = math.sin((1 - f) * w) / math.sin(w), math.sin(f * w) / math.sin(w)
    x, y, z = (ka * u + kb * v for u, v in zip(a, b))
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def gc_nm(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(h))


def airborne(p):
    return p[3] not in ("ground", None)


def bridge(t, ta, a, tb, b):
    """Great-circle position at t between two airborne fixes of one cruise (ocean, no receivers), else None."""
    if not (airborne(a) and airborne(b)) or b[6] & 2 or tb - ta > GAP_MAX_S:
        return None
    kt = gc_nm(a[1], a[2], b[1], b[2]) / ((tb - ta) / 3600)
    if not GAP_KT[0] <= kt <= GAP_KT[1]:
        return None
    return gc_interp(a[1], a[2], b[1], b[2], (t - ta) / (tb - ta))


def samples(trace, base, times, tol=120, fill=False):
    """Yield (time, lat, lon, track, callsign, category, filled) for each time with a fresh airborne point within tol s.

    With fill, a time inside a long gap of one cruise gets a great-circle position, track None and filled True."""
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
        if abs(ts[j] - t) <= tol:
            if airborne(p) and not p[6] & 1:
                yield (t, p[1], p[2], p[5], f, c, False)
            continue
        if fill and 0 < i < len(known):
            _, a, fa, ca = known[i - 1]
            pos = bridge(t, ts[i - 1], a, ts[i], known[i][1])
            if pos:
                yield (t, pos[0], pos[1], None, fa, ca, True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("day")
    ap.add_argument("out")
    ap.add_argument("--every", type=int, default=15)
    ap.add_argument("--fill", action="store_true", help="bridge ocean gaps along great circles")
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
        for t, lat, lon, trk, fl, cat, filled in samples(j["trace"], j["timestamp"], times, fill=a.fill):
            if is_airliner(fl, cat):
                out[str(t)].append([round(lat, 3), round(lon, 3), trk, fl, j.get("t"), int(filled)])
                hit = True
        kept += hit
    pathlib.Path(a.out).write_text(json.dumps(out, separators=(",", ":")))
    sizes = [len(v) for v in out.values()]
    print(f"traces {n}, airliners {kept}, per snapshot min {min(sizes)} max {max(sizes)}")


if __name__ == "__main__":
    main()
