"""The baked earth (earth_qsc480x6.h) as face0-5.bin, for the microSD's /earth.

    uv run -q --no-project --with numpy python -I earth_header.py ../earth_qsc480x6.h OUT_DIR [--size 480]
    python3 send_scene.py PORT OUT_DIR earth          (on pi4-deck, with the module on USB)

The firmware no longer carries the earth: it reads /earth/face0-5.bin after boot (480x480, RGB565 little
endian, faces 0-3 around the equator from 139.767E, 4 the north, 5 the south) and shows a name card until then.
"""
import argparse
import os
import re
import sys

import numpy as np


def faces_from_header(text, size=480):
    """The six faces of the C array in text, each size x size, little-endian uint16."""
    v = np.array([int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", text)], dtype="<u2")
    if v.size != 6 * size * size:
        raise ValueError(f"expected {6 * size * size} values for 6 faces of {size}x{size}, found {v.size}")
    return list(v.reshape(6, size, size))


def write_bins(faces, out):
    os.makedirs(out, exist_ok=True)
    for k, f in enumerate(faces):
        f.astype("<u2").tofile(os.path.join(out, f"face{k}.bin"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("header")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=480)
    a = ap.parse_args(argv)
    try:
        faces = faces_from_header(open(a.header).read(), a.size)
    except (OSError, ValueError) as e:
        print(f"earth_header: {e}", file=sys.stderr)
        return 1
    write_bins(faces, a.out)
    print(f"earth_header: wrote {len(faces)} faces to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
