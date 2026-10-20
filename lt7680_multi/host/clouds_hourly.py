"""Hourly clouds for a flip-book: SSEC RealEarth global infrared over the Blue Marble, per board.

    uv run -q --no-project --with numpy --with pillow --with pyproj python clouds_hourly.py \\
        --hours 24 --boards 3:0,4:2,0:1 [--end YYYY-MM-DDTHH] [--out DIR]

Fetches the last `hours` of RealEarth's hourly global infrared composite
(product globalir; "Source: SSEC RealEarth, UW-Madison"), 1024x512 over
85S-85N in Web Mercator (the largest size without a "size limit exceeded"
watermark), lays each hour out as an equirectangular image, puts its
clouds (brighter = colder) white over the cloud-free Blue Marble, and cuts
the faces the boards show. --boards gives each board's face and turn in
board order (face:turn, as lt7680_multi's x,n,r), so the pixels come out in
the order the panel shows them. Writes b<board>-<frame>.bin (RGB565, little
endian, 480x480) and a contact sheet; the caps beyond 85 degrees take the
mean colour of the 85-degree ring. The same stretch is used for every hour,
so the frames do not flicker against each other.
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

import numpy as np
from PIL import Image

import clouds  # sample, face, rgb565, the Blue Marble path

URL = "https://realearth.ssec.wisc.edu/api/image?products=globalir&width=1024&height=512&bounds=-85,-180,85,180&time={t}"
R = 6378137.0
W, H = clouds.W // 2, clouds.H // 2  # 2048x1024 is plenty for a 1024-wide source


def times(hours, end):
    meta = json.loads(urllib.request.urlopen("https://realearth.ssec.wisc.edu/api/products?products=globalir", timeout=60).read())
    ts = sorted(meta[0]["times"])  # "YYYYMMDD.HHMMSS"
    if end:
        ts = [t for t in ts if t <= end.strftime("%Y%m%d.%H%M%S")]
    return ts[-hours:]


def fetch(t, out):
    path = os.path.join(out, f"ssec-globalir-{t}.png")
    if not os.path.exists(path):
        q = f"{t[:4]}-{t[4:6]}-{t[6:8]}+{t[9:11]}:{t[11:13]}"
        data = urllib.request.urlopen(URL.format(t=q), timeout=120).read()
        if not data.startswith(b"\x89PNG"):
            raise SystemExit(f"RealEarth did not return a PNG for {t}: {data[:200]!r}")
        open(path, "wb").write(data)
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def equirect(band):
    """Web Mercator 85S-85N (band) to W x H equirectangular; NaN beyond 85 degrees."""
    bh, bw = band.shape
    merc = lambda d: R * np.log(np.tan(np.pi / 4 + np.radians(d) / 2))
    top, bot = merc(85), merc(-85)
    lat = 90 - (np.arange(H) + 0.5) / H * 180
    out = np.full((H, W), np.nan, dtype=np.float32)
    inside = np.abs(lat) <= 85
    rows = np.clip(((top - merc(lat[inside])) / (top - bot) * bh).astype(int), 0, bh - 1)
    cols = np.clip((np.arange(W) + 0.5) / W * bw, 0, bw - 1).astype(int)
    out[inside] = band[rows][:, cols]
    return out


def turned(img, r):
    """The panel's view of a face image turned r quarter turns clockwise (lt7680_multi's rotatedIndex)."""
    return np.rot90(img, -r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--end", help="last hour, UTC (YYYY-MM-DDTHH); default the newest")
    ap.add_argument("--boards", default="3:0,4:2,0:1", help="face:turn for board 0, 1, 2 ...")
    ap.add_argument("--out", default=os.path.expanduser("~/tmp/cubic-hourly"))
    ap.add_argument("--lon0", type=float, default=139.767)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    boards = [tuple(int(v) for v in b.split(":")) for b in args.boards.split(",")]
    end = dt.datetime.strptime(args.end, "%Y-%m-%dT%H") if args.end else None
    ts = times(args.hours, end)
    irs = [equirect(fetch(t, args.out)) for t in ts]
    allv = np.concatenate([i[~np.isnan(i)] for i in irs])
    lo, hi = np.percentile(allv, 40), np.percentile(allv, 97)  # one stretch for every hour
    bm = np.asarray(Image.open(clouds.BLUE_MARBLE).convert("RGB").resize((W, H), Image.BILINEAR), dtype=np.float32)
    lat = 90 - (np.arange(H) + 0.5) / H * 180
    centres = [(args.lon0 + 90 * k, 0) for k in range(4)] + [(args.lon0, 90), (args.lon0, -90)]
    clouds.W, clouds.H = W, H  # clouds.sample reads the image size from there
    sheet = Image.new("RGB", (240 * len(boards), 240 * len(ts)))
    for i, (t, ir) in enumerate(zip(ts, irs)):
        a = np.clip((ir - lo) / (hi - lo), 0, 1)
        img = bm * (1 - a[..., None]) + 235 * a[..., None]
        for cap, edge in ((lat > 85, np.argmin(np.abs(lat - 84.9))), (lat < -85, np.argmin(np.abs(lat + 84.9)))):
            img[cap] = img[edge].mean(0)
        img = np.where(np.isnan(img), bm, img)
        for b, (f, r) in enumerate(boards):
            fimg = turned(clouds.face(img, *centres[f], 480), r)
            clouds.rgb565(fimg).astype("<u2").tofile(os.path.join(args.out, f"b{b}-{i:02d}.bin"))
            sheet.paste(Image.fromarray(np.clip(fimg, 0, 255).astype(np.uint8)).resize((240, 240)), (b * 240, i * 240))
        print(t, "done", flush=True)
    sheet.save(os.path.join(args.out, "sheet.jpg"))
    open(os.path.join(args.out, "times.txt"), "w").write("\n".join(ts) + "\n")
    print(f"{len(ts)} hours, {ts[0]} to {ts[-1]} (UTC), {len(boards)} boards, in {args.out}")


if __name__ == "__main__":
    main()
