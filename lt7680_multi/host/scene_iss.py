"""Draw the ISS ground track onto a scene's six faces (face<f>.bin), for the microSD scenes.

    uv run -q --no-project --with numpy --with sgp4 python -I scene_iss.py SRC_DIR OUT_DIR [--minutes 90]

Reads face0-5.bin (480x480 RGB565, from clouds.py or a scene), draws the
track of the last and next N minutes on every face it crosses (past orange,
future cyan, now a red mark with a black rim), and writes face0-5.bin to
OUT_DIR for send_scene.py. Positions: Celestrak TLE (cached 6 hours, as
iss_track.py) -> SGP4 -> latitude and longitude -> qsc.to_face_pixel.
"""
import argparse
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec, jday

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # qsc.py beside this file (python -I leaves it out)
import qsc  # noqa: E402

URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
N = 480
PAST, FUTURE, NOW, RIM = 0xFC00, 0x07FF, 0xF800, 0x0000


def satellite(path, max_age=6 * 3600):
    if not os.path.exists(path) or time.time() - os.path.getmtime(path) > max_age:
        data = urllib.request.urlopen(URL, timeout=30).read().decode()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(data)
    lines = [l.strip() for l in open(path) if l.strip()]
    return Satrec.twoline2rv(next(l for l in lines if l.startswith("1 ")), next(l for l in lines if l.startswith("2 ")))


def gmst_rad(jd):
    t = (jd - 2451545.0) / 36525.0
    g = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((g / 240.0) % 360.0)


def latlon(sat, when):
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second + when.microsecond / 1e6)
    e, r, _ = sat.sgp4(jd, fr)
    if e:
        return None
    x, y, z = r
    lon = (math.degrees(math.atan2(y, x) - gmst_rad(jd + fr)) + 180) % 360 - 180
    return math.degrees(math.atan2(z, math.hypot(x, y))), lon


def dot(faces, f, x, y, r, colour):
    x0, x1, y0, y1 = max(int(x) - r, 0), min(int(x) + r + 1, N), max(int(y) - r, 0), min(int(y) + r + 1, N)
    faces[f][y0:y1, x0:x1] = colour


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--minutes", type=int, default=90, help="minutes before and after now")
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--tle", default=os.path.expanduser("~/tmp/iss.tle"))
    args = ap.parse_args()
    faces = [np.fromfile(os.path.join(args.src, f"face{f}.bin"), dtype="<u2").reshape(N, N) for f in range(6)]
    sat = satellite(args.tle)
    now = datetime.now(timezone.utc)
    for s in range(-args.minutes * 60, args.minutes * 60 + 1, 10):
        ll = latlon(sat, now + timedelta(seconds=s))
        if ll:
            f, x, y = qsc.to_face_pixel(ll[0], ll[1], args.lon0, N)
            dot(faces, f, x, y, 1, PAST if s < 0 else FUTURE)
    lat, lon = latlon(sat, now)
    f, x, y = qsc.to_face_pixel(lat, lon, args.lon0, N)
    dot(faces, f, x, y, 8, RIM)
    dot(faces, f, x, y, 6, NOW)
    os.makedirs(args.out, exist_ok=True)
    for k, face in enumerate(faces):
        face.astype("<u2").tofile(os.path.join(args.out, f"face{k}.bin"))
    print(f"{now:%Y-%m-%d %H:%M}Z: ISS at {lat:.1f}, {lon:.1f} on face {f} ({x:.0f}, {y:.0f}); wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
