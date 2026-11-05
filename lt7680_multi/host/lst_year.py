"""A year of daytime land surface temperature on the cube: 24 half-months, each a scene of six faces.

    uv run -q --no-project --with numpy --with pillow --with pyproj --with tifffile python -I lst_year.py [--out DIR]

Source: the half-monthly normal (2012-2021 mean) of Aqua MODIS daytime land surface temperature
(MYD11C1 v061, about 13:30 local time), as JAXA Earth's STAC hosts it: one cloud-optimised GeoTIFF per
half-month for each of the western and eastern hemispheres, 900x900 at 0.2 degrees (cog level 0; a face
pixel is 0.19 degrees), uint16, kelvin = dn x 0.02, 0 where there is no value (the sea). Credit: "MODIS
LST (NASA), via JAXA Earth API". JAXA's terms ask for the source on anything made public.

Land takes a fixed colour scale from T_MIN to T_MAX (the same for all 24, so the frames compare), the sea
and land without a value keep the Blue Marble, dimmed. Each of the four side faces has
sea somewhere, so each carries a small window (the half-month, the scale, the credit) where no
half-month of the year has land (spot), as near a chosen corner as that allows (CORNERS), the same
place in all 24. Writes <OUT>/<k>/face0-5.bin for k = 1..24 (January
first half = 1, as #s scenes go after them), <OUT>/<k>/faces.png, and <OUT>/sheet.png (all 24, face 1).
The GeoTIFFs are kept in <OUT>/src and not fetched again.
"""
import argparse
import os
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I leaves this directory out
import clouds  # noqa: E402  face, rgb565, the Blue Marble path

BASE = ("https://s3.ap-northeast-1.wasabisys.com/je-pds/cog/v1/"
        "NASA.EOSDIS_Aqua.MODIS_MYD11C1-LST.daytime.v061_global_half-monthly-normal")
T_MIN, T_MAX = -40.0, 60.0
STOPS = [(-40, (70, 20, 140)), (-20, (30, 80, 220)), (0, (60, 190, 240)), (10, (80, 200, 120)),
         (20, (240, 230, 60)), (30, (250, 150, 30)), (45, (220, 40, 20)), (60, (110, 0, 20))]
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SEA_DIM = 0.7
WIN_W, WIN_H = 168, 94  # the information window, at 480 px a face
CORNERS = [(1, 0), (1, 1), (1, 1), (1, 1)]  # per side face, the corner its window leans to: Japan's top right, the rest bottom right


def half_months():
    return [f"{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 16)]


def label(mmdd):
    m, d = (int(v) for v in mmdd.split("-"))
    return f"{m}月{'前半' if d == 1 else '後半'}"


def tif_urls(mmdd):
    return (f"{BASE}/{mmdd}/0/W180.00-E000.00/W180.00-S90.00-E000.00-N90.00-LST_2012_2021.tif",
            f"{BASE}/{mmdd}/0/E000.00-E180.00/E000.00-S90.00-E180.00-N90.00-LST_2012_2021.tif")


def celsius(dn):
    c = dn.astype(np.float32) * np.float32(0.02) - np.float32(273.15)
    return np.where(dn == 0, np.float32(np.nan), c)


def join(west, east):
    return np.concatenate([west, east], axis=1)


def colours(t):
    t = np.clip(np.asarray(t, dtype=np.float32), T_MIN, T_MAX)
    xs = [s for s, _ in STOPS]
    return np.stack([np.interp(t, xs, [c[i] for _, c in STOPS]) for i in range(3)], axis=-1).astype(np.float32)


def picture(lst, base):
    """Land in colour, everything without a value from base."""
    land = ~np.isnan(lst)
    out = base.copy()
    out[land] = colours(lst[land])
    return out


def fetch(url, path):
    if not os.path.exists(path):
        data = urllib.request.urlopen(url, timeout=120).read()
        if not data.startswith((b"II*\x00", b"MM\x00*")):
            raise SystemExit(f"not a TIFF: {url}")
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    import tifffile  # only the fetching side needs it
    return tifffile.imread(path, key=0)


def spot(land, w, h, margin=8, step=4, toward=None):
    """Top-left (x, y) of the w x h box, inside the margin, that covers the least land; among equals, the
    one nearest the corner toward = (right 0/1, bottom 0/1). Every step pixels, then pixel by pixel."""
    n_y, n_x = land.shape
    c = np.pad(land.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)  # summed-area table
    xs, ys = range(margin, n_x - margin - w + 1), range(margin, n_y - margin - h + 1)
    gx = None if toward is None else (xs[-1] if toward[0] else xs[0])
    gy = None if toward is None else (ys[-1] if toward[1] else ys[0])

    def best_of(cands):
        def key(p):
            x, y = p
            covered = c[y + h, x + w] - c[y, x + w] - c[y + h, x] + c[y, x]
            return (covered, 0 if gx is None else (x - gx) ** 2 + (y - gy) ** 2)
        return min(cands, key=key)

    bx, by = best_of([(x, y) for y in ys[::step] for x in xs[::step]])
    return best_of([(x, y) for y in ys if abs(y - by) < step for x in xs if abs(x - bx) < step])


def window(face_img, text, x, y, n):
    """A small box at (x, y) (WIN_W x WIN_H at 480 px): the half-month, the colour scale, the credit."""
    im = Image.fromarray(np.clip(face_img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    s = n / 480 * WIN_W / 200  # laid out for a 200 px window
    f = lambda px: ImageFont.truetype(FONT, max(8, int(px * s)))
    w, h = int(200 * s), int(112 * s)
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=(0, 0, 0), outline=(110, 110, 110))
    d.text((x + w // 2, y + int(2 * s)), text, font=f(30), fill=(255, 255, 255), anchor="ma")
    d.text((x + w // 2, y + int(40 * s)), "昼の地表の温度 (℃)", font=f(13), fill=(255, 255, 255), anchor="ma")
    x0, x1, by = x + int(12 * s), x + w - int(12 * s), y + int(60 * s)
    bar = colours(np.linspace(T_MIN, T_MAX, x1 - x0)).astype(np.uint8)
    for i, c in enumerate(bar):
        d.line([x0 + i, by, x0 + i, by + int(12 * s)], fill=tuple(int(v) for v in c))
    for t in (-40, -20, 0, 20, 40, 60):
        tx = x0 + (t - T_MIN) / (T_MAX - T_MIN) * (x1 - x0 - 1)
        d.text((tx, by + int(14 * s)), f"{t}", font=f(12), fill=(255, 255, 255), anchor="ma")
    d.text((x + w // 2, y + h - int(15 * s)), "MODIS LST (NASA), JAXA Earth", font=f(10), fill=(170, 170, 170), anchor="ma")
    return np.asarray(im, dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/Workspaces/tmp/cubic-lst-year"))
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--size", type=int, default=480)
    args = ap.parse_args()
    src = os.path.join(args.out, "src")
    os.makedirs(src, exist_ok=True)
    n = args.size
    centres = [(args.lon0 + 90 * i, 0) for i in range(4)] + [(args.lon0, 90), (args.lon0, -90)]
    hms = half_months()
    lsts = []
    for mmdd in hms:
        w, e = (fetch(u, os.path.join(src, f"{mmdd}-{u.rsplit('/', 1)[1]}")) for u in tif_urls(mmdd))
        lsts.append(celsius(join(w, e)))
    # land anywhere in the year, on each side face: the windows sit where none of the 24 has land
    ever = np.zeros(lsts[0].shape, dtype=np.float32)
    for lst in lsts:
        ever = np.maximum(ever, (~np.isnan(lst)).astype(np.float32))
    ws = int(WIN_W * n / 480), int(WIN_H * n / 480)
    spots = [spot(clouds.face(np.repeat(ever[..., None], 3, 2), lo, la, n)[..., 0] > 0.01, *ws, margin=n // 40, toward=t)
             for (lo, la), t in zip(centres[:4], CORNERS)]
    h, wd = lsts[0].shape
    bm = Image.open(clouds.BLUE_MARBLE).convert("RGB").resize((wd, h), Image.BILINEAR)
    base = np.asarray(bm, dtype=np.float32) * SEA_DIM
    sheet = Image.new("RGB", (6 * n // 2, 4 * n // 2))
    for k, (mmdd, lst) in enumerate(zip(hms, lsts), start=1):
        img = picture(lst, base)
        faces = [clouds.face(img, lo, la, n) for lo, la in centres]
        for i, (x, y) in enumerate(spots):
            faces[i] = window(faces[i], label(mmdd), x, y, n)
        out = os.path.join(args.out, str(k))
        os.makedirs(out, exist_ok=True)
        for i, f in enumerate(faces):
            clouds.rgb565(f).astype("<u2").tofile(os.path.join(out, f"face{i}.bin"))
        cross = Image.new("RGB", (4 * n, 3 * n))
        for i, (cx, cy) in {0: (0, 1), 1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (0, 0), 5: (0, 2)}.items():
            cross.paste(Image.fromarray(np.clip(faces[i], 0, 255).astype(np.uint8)), (cx * n, cy * n))
        cross.save(os.path.join(out, "faces.png"))
        tile = Image.fromarray(np.clip(faces[1], 0, 255).astype(np.uint8)).resize((n // 2, n // 2))
        sheet.paste(tile, ((k - 1) % 6 * n // 2, (k - 1) // 6 * n // 2))
        print(f"{k:2d} {mmdd} {label(mmdd)}: land {np.nanmin(lst):.0f} to {np.nanmax(lst):.0f} C", flush=True)
    print("windows (x, y) on faces 0-3:", spots)
    sheet.save(os.path.join(args.out, "sheet.png"))


if __name__ == "__main__":
    main()
