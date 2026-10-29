"""Earth faces for the microSD scenes: Blue Marble by day, Black Marble by night, clouds see-through on top.

    uv run -q --no-project --with numpy --with pillow --with pyproj python -I scene_compose.py OUT_DIR \
        [--clouds 2026-10-27] [--opacity 0.6] [--time now|none|2026-10-28T12:00] [--night-only]
        [--layers population,rivers,rail,airports]

- Day: the cloudless Blue Marble (lt7680_earth/blue_marble_2002.jpg).
- Night: NASA Black Marble 2016 (GIBS layer VIIRS_Black_Marble, cached in
  ~/tmp/cubic-night/), city lights from VIIRS.
- Clouds: from the GIBS true colour of a day (clouds.py fetches and caches
  it): the cloud's alpha is how much brighter the mosaic is than the
  cloudless ground, so bright deserts and snow that the Blue Marble already
  has do not count. The clouds are drawn white by day and dim grey by night,
  with --opacity, so the ground and the city lights show through.
- --time: the sun's position for the day/night line (soft over about 6
  degrees); "none" draws day everywhere, --night-only night everywhere.
- --layers: overlays from layers.py (railways and rivers from tile.yuiseki.net,
  airports, population), each in its own colour over the clouds.
Writes face0-5.bin (as clouds.py) and faces.png.
"""
import argparse
import datetime as dt
import math
import os
import sys
import urllib.request

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # clouds.py beside this file (python -I leaves it out)
import clouds  # noqa: E402
import equirect_scene  # noqa: E402
import layers  # noqa: E402

# layer: colour, strength (scales its alpha)
LAYER_STYLE = {
    "population": ((255, 170, 70), 0.95),
    "rivers": ((120, 200, 255), 0.7),
    "rail": ((255, 205, 120), 1.0),
    "airports": ((90, 255, 230), 1.0),
}

NIGHT_LAYER = "VIIRS_Black_Marble"
NIGHT_CACHE = os.path.expanduser("~/tmp/cubic-night")
TWILIGHT = 6.0  # degrees over which day fades into night


def cloud_alpha(sat, ground):
    """0..1 cloud cover from the day's mosaic (sat) and the cloudless ground (both H x W x 3, 0..255)."""
    lum = lambda im: im.mean(2)
    a = (lum(sat) - lum(ground) - 10) / np.maximum(235 - lum(ground), 20)
    a = np.clip(a, 0, 1)
    a[sat.sum(2) < 45] = 0  # no data in the mosaic (polar night, gaps)
    return a


def subsolar(when):
    """Latitude and longitude (degrees) of the point with the sun overhead (NOAA's low-precision formulas)."""
    when = when.astimezone(dt.timezone.utc)
    n = (when - dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)).total_seconds() / 86400
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    gmst = math.radians((280.46061837 + 360.98564736629 * n) % 360)
    lon = math.degrees(ra - gmst)
    return math.degrees(dec), (lon + 180) % 360 - 180


def daylight(lat, lon, slat, slon):
    """1 in day, 0 in night, a linear fade over TWILIGHT degrees of the sun's elevation round the line."""
    la, lo, sla, slo = map(np.radians, (lat, lon, slat, slon))
    elev = np.degrees(np.arcsin(np.sin(la) * np.sin(sla) + np.cos(la) * np.cos(sla) * np.cos(lo - slo)))
    return np.clip(elev / TWILIGHT + 0.5, 0, 1)


def compose(day, night, alpha, light, opacity):
    """Ground by day or night, then clouds: white by day, dim grey by night, `opacity` at full cover."""
    a = (alpha * opacity)[..., None]
    l = light[..., None]
    ground = day * l + night * (1 - l)
    cloud = 235 * l + 40 * (1 - l)
    return ground * (1 - a) + cloud * a


def fetch_night():
    path = os.path.join(NIGHT_CACHE, f"{NIGHT_LAYER}.jpg")
    if not os.path.exists(path):
        os.makedirs(NIGHT_CACHE, exist_ok=True)
        url = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
               f"&LAYERS={NIGHT_LAYER}&STYLES=&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH={clouds.W}&HEIGHT={clouds.H}&FORMAT=image/jpeg")
        open(path, "wb").write(urllib.request.urlopen(url, timeout=60).read())
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--clouds", help="UTC day of the GIBS true colour for the clouds (none: no clouds)")
    ap.add_argument("--opacity", type=float, default=0.6)
    ap.add_argument("--time", default="now", help="now, none (day everywhere) or an ISO time in UTC")
    ap.add_argument("--night-only", action="store_true")
    ap.add_argument("--dim", type=float, default=1.0, help="scale the ground and clouds (0.5: half as bright) so the layers stand out")
    ap.add_argument("--layers", default="", help="comma separated, drawn in this order: population, rivers, rail, airports")
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--size", type=int, default=480)
    args = ap.parse_args()
    W, H = clouds.W, clouds.H
    day = np.asarray(Image.open(clouds.BLUE_MARBLE).convert("RGB").resize((W, H), Image.BILINEAR), dtype=np.float32)
    night = fetch_night()
    alpha = np.zeros((H, W), dtype=np.float32)
    if args.clouds:
        src = os.path.join(os.path.expanduser("~/tmp/cubic-clouds-" + args.clouds.replace("-", "")),
                           f"gibs-{clouds.LAYER}-{args.clouds}.jpg")
        os.makedirs(os.path.dirname(src), exist_ok=True)
        clouds.fetch(args.clouds, src)
        alpha = cloud_alpha(np.asarray(Image.open(src).convert("RGB"), dtype=np.float32), day)
    lat = (90 - (np.arange(H) + 0.5) / H * 180)[:, None] * np.ones((1, W))
    lon = (-180 + (np.arange(W) + 0.5) / W * 360)[None, :] * np.ones((H, 1))
    if args.night_only:
        light, when = np.zeros((H, W)), "night"
    elif args.time == "none":
        light, when = np.ones((H, W)), "day"
    else:
        t = dt.datetime.now(dt.timezone.utc) if args.time == "now" else dt.datetime.fromisoformat(args.time).replace(tzinfo=dt.timezone.utc)
        slat, slon = subsolar(t)
        light, when = daylight(lat, lon, slat, slon), f"{t:%Y-%m-%d %H:%M}Z (sun over {slat:.1f}, {slon:.1f})"
    img = compose(day, night, alpha, light, args.opacity) * args.dim
    notes = []
    for name in [n for n in args.layers.split(",") if n]:
        if name == "rail":
            a = layers.vector_lines("railways", "railways_low", W, H, width=2)
        elif name == "rivers":
            a = layers.vector_lines("rivers", "rivers_low", W, H, width=1)
        elif name == "airports":
            a, count = layers.airports(W, H)
            notes.append(f"{count} airports")
        elif name == "population":
            g, people = layers.population(W, H)
            a = np.clip((g - 0.45) / 0.5, 0, 1) ** 1.2  # the lower half of the log scale (sparse country) stays dark
            notes.append(f"{people:,} people")
        else:
            raise SystemExit(f"unknown layer {name}")
        colour, strength = LAYER_STYLE[name]
        a = (a * strength)[..., None]
        img = img * (1 - a) + np.array(colour, dtype=np.float32) * a
    equirect_scene.write(equirect_scene.faces(img, args.lon0, args.size), args.out)
    print(f"{when}, clouds {args.clouds or 'none'} at {args.opacity}, layers {args.layers or 'none'} {', '.join(notes)}: wrote {args.out}")


if __name__ == "__main__":
    main()
