"""The Earth right now on the cube, through #j: day and night for now, the newest hourly infrared clouds.

    uv run -q --no-project --with numpy --with pillow --with pyproj python -I live_sides.py OUT_DIR \\
        north=0:1,4:2,3:0 south=1:3,5:3,2:2 [--opacity 0.8] [--time 2026-11-03T10:00]

Each module is name=face:turn for boards A, B, C (the faces and turns lt7680_multi has, #f). Writes
<name>-side-a.jpg, -b, -c (480x480) already turned as the firmware would turn the face (rotate.h), since
#j draws the image on the panel as it is. Put them in the web directory and send #j to each module.
- Day and night: scene_compose.py (Blue Marble, Black Marble, the sun's position for --time, default now)
- Clouds: the newest hour of SSEC RealEarth's global infrared (clouds_hourly.py; "Source: SSEC RealEarth,
  UW-Madison"), stretched between its 40th and 97th percentile, white by day and dim grey by night.
  One global 1024x512 image, 0.35 degrees a pixel (a face is 0.19). Finer did not work: bounded images
  of 1024x2048 and the zoom-3 map tiles (0.18 degrees) both came back with "Size limit exceeded" written
  across them after a few requests (2026-11-03), so RealEarth limits how much one client asks for in a
  while, whatever the size. 721 hourly global images fetched 0.5 s apart had none
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I leaves this directory out
import clouds  # noqa: E402
import clouds_hourly  # noqa: E402
import equirect_scene  # noqa: E402
import scene_compose  # noqa: E402


def panel_view(face, r):
    """What the panel shows for a face image turned r quarter turns clockwise (rotate.h's rotatedIndex)."""
    return np.rot90(face, -r)


def parse_modules(specs):
    out = {}
    for s in specs:
        name, boards = s.split("=")
        out[name] = [tuple(int(v) for v in b.split(":")) for b in boards.split(",")]
    return out


def fill_caps(alpha, lat):
    """RealEarth stops at 85 degrees: give each cap the mean of its nearest ring (as clouds_hourly.py does),
    so the poles do not show a clear square inside the clouds."""
    out = alpha.copy()
    rows = lat[:, 0]
    for cap, ring in ((rows > 85, np.argmin(np.abs(rows - 84.9))), (rows < -85, np.argmin(np.abs(rows + 84.9)))):
        out[cap] = np.nanmean(alpha[ring])
    return out


def side_name(module, board):
    return f"{module}-side-{'abc'[board]}.jpg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("modules", nargs="+", help="name=face:turn,face:turn,face:turn (boards A, B, C)")
    ap.add_argument("--opacity", type=float, default=0.8)
    ap.add_argument("--time", help="UTC, ISO (default now)")
    ap.add_argument("--lon0", type=float, default=139.767)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    W, H = clouds_hourly.W, clouds_hourly.H
    t = dt.datetime.fromisoformat(args.time).replace(tzinfo=dt.timezone.utc) if args.time else dt.datetime.now(dt.timezone.utc)
    newest = clouds_hourly.times(1, None)[-1]
    ir = clouds_hourly.equirect(clouds_hourly.fetch(newest, os.path.expanduser("~/Workspaces/tmp/realearth-globalir")))
    v = ir[~np.isnan(ir)]
    lo, hi = np.percentile(v, 40), np.percentile(v, 97)
    lat = (90 - (np.arange(H) + 0.5) / H * 180)[:, None] * np.ones((1, W))
    alpha = np.nan_to_num(fill_caps(np.clip((ir - lo) / (hi - lo), 0, 1), lat))
    day = np.asarray(Image.open(clouds.BLUE_MARBLE).convert("RGB").resize((W, H), Image.BILINEAR), dtype=np.float32)
    night = np.asarray(Image.fromarray(scene_compose.fetch_night().astype(np.uint8)).resize((W, H), Image.BILINEAR), dtype=np.float32)
    lon = (-180 + (np.arange(W) + 0.5) / W * 360)[None, :] * np.ones((H, 1))
    slat, slon = scene_compose.subsolar(t)
    img = scene_compose.compose(day, night, alpha, scene_compose.daylight(lat, lon, slat, slon), args.opacity)
    clouds.W, clouds.H = W, H  # clouds.face samples with these sizes
    fs = equirect_scene.faces(img, args.lon0, 480)
    for name, boards in parse_modules(args.modules).items():
        for b, (f, r) in enumerate(boards):
            Image.fromarray(np.clip(panel_view(fs[f], r), 0, 255).astype(np.uint8)).save(os.path.join(args.out, side_name(name, b)), quality=90)
    print(f"{t:%Y-%m-%d %H:%M}Z, sun over {slat:.1f} {slon:.1f}, clouds {newest} (RealEarth, UTC): wrote {args.out}")


if __name__ == "__main__":
    main()
