"""Draw the ISS ground track onto a scene's six faces (face<f>.bin), for the microSD scenes.

    uv run -q --no-project --with numpy --with sgp4 python -I scene_iss.py SRC_DIR OUT_DIR [--minutes 90]

Reads face0-5.bin (480x480 RGB565, from clouds.py or a scene), draws the
track of the last and next N minutes on every face it crosses (past orange,
future cyan, now a red mark with a black rim), and writes face0-5.bin to
OUT_DIR for send_scene.py. Positions: Celestrak TLE (cached 6 hours, as
iss_track.py, whose TLE and maths it uses) -> SGP4 -> latitude and longitude -> qsc.to_face_pixel.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # qsc.py and iss_track.py beside this file (python -I leaves it out)
import qsc  # noqa: E402
from iss_track import gmst_rad, latlon, load_tle, parse_tle  # noqa: E402,F401  (gmst_rad is re-exported)

N = 480
PAST, FUTURE, NOW, RIM = 0xFC00, 0x07FF, 0xF800, 0x0000


def satellite(path, max_age=6 * 3600):
    return parse_tle(load_tle(path, max_age))[1]


def dot(faces, f, x, y, r, colour):
    x0, x1, y0, y1 = max(int(x) - r, 0), min(int(x) + r + 1, N), max(int(y) - r, 0), min(int(y) + r + 1, N)
    faces[f][y0:y1, x0:x1] = colour


def read_faces(src):
    """face0-5.bin (480x480 RGB565, little endian) as six arrays. A missing or short file is an error."""
    return [np.fromfile(os.path.join(src, f"face{f}.bin"), dtype="<u2").reshape(N, N) for f in range(6)]


def write_faces(faces, out):
    os.makedirs(out, exist_ok=True)
    for k, face in enumerate(faces):
        face.astype("<u2").tofile(os.path.join(out, f"face{k}.bin"))


def draw_track(faces, sat, now, minutes, lon0, step=10):
    """Draw the past (orange) and future (cyan) dots every `step` seconds, then the current spot (red in a black rim),
    on whichever face each falls. Changes `faces` in place; returns (lat, lon, face, x, y) of now."""
    for s in range(-minutes * 60, minutes * 60 + 1, step):
        ll = latlon(sat, now + timedelta(seconds=s))
        if ll:
            f, x, y = qsc.to_face_pixel(ll[0], ll[1], lon0, N)
            dot(faces, f, x, y, 1, PAST if s < 0 else FUTURE)
    lat, lon = latlon(sat, now)
    f, x, y = qsc.to_face_pixel(lat, lon, lon0, N)
    dot(faces, f, x, y, 8, RIM)
    dot(faces, f, x, y, 6, NOW)
    return lat, lon, f, x, y


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--minutes", type=int, default=90, help="minutes before and after now")
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--tle", default=os.path.expanduser("~/tmp/iss.tle"))
    ap.add_argument("--max-age", type=float, default=6 * 3600, help="seconds the cached TLE is used")
    args = ap.parse_args(argv)
    faces = read_faces(args.src)
    sat = satellite(args.tle, args.max_age)
    now = datetime.now(timezone.utc)
    lat, lon, f, x, y = draw_track(faces, sat, now, args.minutes, args.lon0)
    write_faces(faces, args.out)
    print(f"{now:%Y-%m-%d %H:%M}Z: ISS at {lat:.1f}, {lon:.1f} on face {f} ({x:.0f}, {y:.0f}); wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
