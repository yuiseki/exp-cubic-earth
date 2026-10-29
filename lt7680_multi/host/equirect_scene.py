"""Any equirectangular (plate carree, 2:1) image onto the six faces for a microSD scene.

    uv run -q --no-project --with numpy --with pillow --with pyproj python -I equirect_scene.py IMAGE OUT_DIR [--west -180] [--lon0 139.767] [--size 480]

The image runs 360 degrees east from --west at its left edge (180W for
Dagik Earth's map_N.jpg, 0 for the NIPR Dagik pages' images), 90N at the
top to 90S. Writes
face0-5.bin and faces.png as scene_compose.py does, for send_scene.py.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # clouds.py beside this file (python -I leaves it out)
import clouds  # noqa: E402

# where each face goes on faces.png: the four sides in a row, north above face 0, south below it
SHEET = [(1, 1), (2, 1), (3, 1), (0, 1), (1, 0), (1, 2)]


def shift(img, west):
    """The same image rolled so that its left edge is 180W."""
    return np.roll(img, round((west + 180.0) / 360.0 * img.shape[1]), axis=1)


def faces(img, lon0, size):
    """Faces 0-3 around the equator from lon0 eastwards, 4 the north, 5 the south."""
    centres = [(lon0 + 90 * k, 0) for k in range(4)] + [(lon0, 90), (lon0, -90)]
    return [clouds.face(img, lo, la, size) for lo, la in centres]


def write(fs, out):
    os.makedirs(out, exist_ok=True)
    for k, f in enumerate(fs):
        clouds.rgb565(f).astype("<u2").tofile(os.path.join(out, f"face{k}.bin"))
    n = fs[0].shape[0]
    sheet = Image.new("RGB", (4 * n, 3 * n))
    for f, (cx, cy) in zip(fs, SHEET):
        sheet.paste(Image.fromarray(np.clip(f, 0, 255).astype(np.uint8)), (cx * n, cy * n))
    sheet.save(os.path.join(out, "faces.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--west", type=float, default=-180.0, help="longitude at the image's left edge (NIPR's Dagik images: 0)")
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--size", type=int, default=480)
    args = ap.parse_args()
    img = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.float32)
    write(faces(shift(img, args.west), args.lon0, args.size), args.out)
    print(f"{args.image} ({img.shape[1]}x{img.shape[0]}): wrote {args.out}")


if __name__ == "__main__":
    main()
