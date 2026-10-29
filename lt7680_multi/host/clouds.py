"""Today's clouds on the cube: NASA GIBS true colour (SSEC infrared at the poles), cut into the six QSC faces.

    uv run -q --no-project --with numpy --with pillow --with pyproj python -I clouds.py [--date YYYY-MM-DD] [--out DIR]

Fetches the daily VIIRS (NOAA-20) corrected-reflectance true-colour mosaic
from NASA GIBS (WMS, EPSG:4326, 4096x2048; one request, no login). Where
it has no data (the polar night, and the poles beyond the swaths), it puts
the clouds of SSEC RealEarth's hourly global infrared composite (product
globalir; "Source: SSEC RealEarth, UW-Madison"), white over the cloud-free
Blue Marble. RealEarth returns at most 1024 pixels wide without a "size
limit exceeded" watermark, in Web Mercator up to 85 degrees, so it is
fetched as two bands, 60-85 north and south, and the caps beyond 85
degrees take the mean colour of the 85-degree ring. In the polar night the
frozen sea is as cold as the clouds and shows as white too. It cuts the six faces of earth_qsc480x6.h (sides
centred on lon0 + 90k, then the north and south poles, joined to face 0),
480x480 each. Writes face<k>.bin (RGB565, little endian, row by row, the
face image as make_qsc_faces.py lays it out; the firmware turns it for
each board), faces.png (a contact sheet) and the source image.
"""
import argparse
import datetime as dt
import os
import urllib.request

import numpy as np
from PIL import Image
from pyproj import Proj

HERE = os.path.dirname(os.path.abspath(__file__))
BLUE_MARBLE = os.path.join(HERE, "..", "..", "lt7680_earth", "blue_marble_2002.jpg")
LAYER = "VIIRS_NOAA20_CorrectedReflectance_TrueColor"
SSEC = "https://realearth.ssec.wisc.edu/api/image?products=globalir&width=1024&height=512&bounds={s},-180,{n},180&time={date}+12:00"
R = 6378137.0
W, H = 4096, 2048


def fetch(date, path):
    if os.path.exists(path):
        return
    url = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
           f"&LAYERS={LAYER}&STYLES=&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH={W}&HEIGHT={H}&FORMAT=image/jpeg&TIME={date}")
    data = urllib.request.urlopen(url, timeout=120).read()
    if not data.startswith(b"\xff\xd8"):
        raise SystemExit(f"GIBS did not return a JPEG: {data[:200]!r}")
    open(path, "wb").write(data)


def fetch_ir(date, out):
    """SSEC global infrared, 60-85 degrees north and south, as an equirectangular grey image (W x H, NaN elsewhere)."""
    ir = np.full((H, W), np.nan, dtype=np.float32)
    for s, n in ((60, 85), (-85, -60)):
        path = os.path.join(out, f"ssec-globalir-{date}-{s}-{n}.png")
        if not os.path.exists(path):
            data = urllib.request.urlopen(SSEC.format(s=s, n=n, date=date), timeout=120).read()
            if not data.startswith(b"\x89PNG"):
                raise SystemExit(f"RealEarth did not return a PNG: {data[:200]!r}")
            open(path, "wb").write(data)
        band = np.asarray(Image.open(path).convert("L"), dtype=np.float32)  # Web Mercator rows, n at the top
        bh, bw = band.shape
        merc = lambda d: R * np.log(np.tan(np.pi / 4 + np.radians(d) / 2))
        ytop, ybot = merc(n), merc(s)
        rows = np.arange(H)
        lat = 90 - (rows + 0.5) / H * 180
        inside = (lat >= s) & (lat <= n)
        src_row = np.clip(((ytop - merc(lat[inside])) / (ytop - ybot) * bh).astype(int), 0, bh - 1)
        src_col = np.clip((np.arange(W) + 0.5) / W * bw, 0, bw - 1).astype(int)
        ir[rows[inside]] = band[src_row][:, src_col]
    return ir


def merged(date_path, ir):
    """The GIBS mosaic; where it has no data (near black), infrared clouds over the Blue Marble, blended softly."""
    sat = np.asarray(Image.open(date_path).convert("RGB"), dtype=np.float32)
    bm = np.asarray(Image.open(BLUE_MARBLE).convert("RGB").resize((W, H), Image.BILINEAR), dtype=np.float32)
    # 0 where there is no data (sum < 15), 1 from sum 45 up: JPEG leaves a dark fringe round the holes
    w = np.clip((sat.sum(2) - 15) / 30, 0, 1)[..., None]
    # infrared: brighter is colder. Stretch each pole's hole on its own, from its 30th percentile to its 97th:
    # the polar night is cold all over, so a stretch over both bands left it nearly cloudless
    a = np.zeros((H, W), dtype=np.float32)
    lat = 90 - (np.arange(H) + 0.5) / H * 180
    for half in (lat > 0, lat < 0):
        hole = half[:, None] & (w[..., 0] < 0.99) & ~np.isnan(ir)
        if hole.sum() < 100:
            continue
        lo, hi = np.percentile(ir[hole], 30), np.percentile(ir[hole], 97)
        a[half] = np.clip((ir[half] - lo) / max(hi - lo, 1), 0, 1)
    fill = bm * (1 - a[..., None]) + 235 * a[..., None]
    # the caps beyond 85 degrees: the mean colour of the nearest row that has infrared
    for cap, edge in ((lat > 85, np.argmin(np.abs(lat - 84.9))), (lat < -85, np.argmin(np.abs(lat + 84.9)))):
        fill[cap] = fill[edge].mean(0)
    fill = np.where(np.isnan(fill), bm, fill)
    return sat * w + fill * (1 - w)


def sample(img, lon, lat):
    """Bilinear sample of an equirectangular image at lon/lat (degrees), wrapping in longitude."""
    H, W = img.shape[:2]
    fx = ((lon / 360.0) + 0.5) % 1.0 * W - 0.5
    fy = (0.5 - lat / 180.0) * H - 0.5
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = (fx - x0)[..., None], (fy - y0)[..., None]
    def at(x, y):
        return img[np.clip(y, 0, H - 1), x % W]
    top = at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx
    bot = at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx
    return top * (1 - ty) + bot * ty


def face(img, lon0, lat0, n):
    """One face as make_qsc_faces.render_face lays it out (north up on the sides)."""
    p = Proj(f"+proj=qsc +R=1 +lat_0={lat0} +lon_0={lon0}")
    half, _ = Proj(f"+proj=qsc +R=1 +lat_0=0 +lon_0={lon0}")(lon0 + 45.0, 0.0)
    c = (np.arange(n) + 0.5) / n * 2 * half - half
    xs, ys = np.meshgrid(c, -c)
    lon, lat = p(xs.ravel(), ys.ravel(), inverse=True)
    return sample(img, np.asarray(lon), np.asarray(lat)).reshape(n, n, 3)


def rgb565(rgb):
    r, g, b = [np.clip(rgb[..., i] + 0.5, 0, 255).astype(np.uint16) for i in range(3)]
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def main():
    ap = argparse.ArgumentParser()
    yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
    ap.add_argument("--date", default=yesterday, help="UTC day of the mosaic (default: yesterday, the newest complete one)")
    ap.add_argument("--out", default=os.path.expanduser("~/tmp/cubic-clouds"))
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--size", type=int, default=480)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    src = os.path.join(args.out, f"gibs-{LAYER}-{args.date}.jpg")
    fetch(args.date, src)
    img = merged(src, fetch_ir(args.date, args.out))
    centres = [(args.lon0 + 90 * k, 0) for k in range(4)] + [(args.lon0, 90), (args.lon0, -90)]
    faces = [face(img, lo, la, args.size) for lo, la in centres]
    for k, f in enumerate(faces):
        rgb565(f).astype("<u2").tofile(os.path.join(args.out, f"face{k}.bin"))
    n = args.size
    sheet = Image.new("RGB", (4 * n, 3 * n))
    # the usual cross: north above face 0, south below it
    spots = {0: (0, 1), 1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (0, 0), 5: (0, 2)}
    for k, (cx, cy) in spots.items():
        sheet.paste(Image.fromarray(np.clip(faces[k], 0, 255).astype(np.uint8)), (cx * n, cy * n))
    sheet.save(os.path.join(args.out, "faces.png"))
    print(f"{args.date}: wrote face0-5.bin and faces.png to {args.out}")


if __name__ == "__main__":
    main()
