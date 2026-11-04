"""Pack one day of airliner positions into the cube's flight file (lt7680_multi/flight_track.h).

Input is globe_snapshots.py output (preferably with --fill). Both modules read the same
file and draw only what falls on their own faces, so the cap is per cube face: at every
keyframe no face carries more than CAP flights (each one costs two BTE copies a frame).

Usage: python -I pack_flights.py SNAPSHOTS.json OUT.bin [--cap 60] [--seed 0]
"""
import argparse
import math
import random
import struct

LON0 = 139.767  # qscInit(qsc, 139.767, 480) in lt7680_multi.ino
NONE = -32768


def face_of(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    v = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    normals = []
    for k in range(4):
        l = math.radians(LON0 + 90 * k)
        normals.append((math.cos(l), math.sin(l), 0.0))
    normals += [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]
    return max(range(6), key=lambda f: sum(a * b for a, b in zip(v, normals[f])))


def tracks(snapshots):
    """-> (sorted key times, {callsign: [(lat, lon) or None per key]}). A callsign seen twice at one key keeps the first."""
    keys = sorted(int(k) for k in snapshots)
    out = {}
    for i, k in enumerate(keys):
        for p in snapshots[str(k)]:
            tr = out.setdefault(p[3], [None] * len(keys))
            if tr[i] is None:
                tr[i] = (p[0], p[1])
    return keys, out


def select(trs, cap, seed=0):
    """Random flights, skipping any that would put more than cap on a face at some key."""
    order = sorted(trs)
    random.Random(seed).shuffle(order)
    load, picked = {}, []
    for cs in order:
        cells = [(i, face_of(*p)) for i, p in enumerate(trs[cs]) if p]
        if all(load.get(c, 0) < cap for c in cells):
            for c in cells:
                load[c] = load.get(c, 0) + 1
            picked.append(cs)
    return picked


def pack(keys, trs, picked):
    step = (keys[1] - keys[0]) // 60 if len(keys) > 1 else 15
    b = bytearray(b"CEF1" + struct.pack("<HHII", len(keys), step, keys[0], len(picked)))
    for cs in picked:
        b += cs.encode("ascii", "replace")[:7].ljust(8, b"\0")
        for p in trs[cs]:
            b += struct.pack("<hh", *(round(p[0] * 100), round(p[1] * 100)) if p else (NONE, NONE))
    return bytes(b)


def main():
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshots")
    ap.add_argument("out")
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    keys, trs = tracks(json.load(open(a.snapshots)))
    picked = select(trs, a.cap, a.seed)
    b = pack(keys, trs, picked)
    open(a.out, "wb").write(b)
    print(f"keys {len(keys)}, flights {len(trs)}, picked {len(picked)} (cap {a.cap} per face), {len(b)} bytes")


if __name__ == "__main__":
    main()
