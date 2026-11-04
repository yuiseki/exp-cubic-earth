"""uv run -q --no-project --with pytest python -m pytest -q test_pack_flights.py"""
import struct

import pack_flights as pf

T0 = 1793664000


def test_face_matches_the_firmware_cube():
    # qscInit(qsc, 139.767, 480): face 0 is centred on Tokyo's meridian, then +90 deg east, 4 north, 5 south
    assert pf.face_of(35.7, 139.8) == 0
    assert pf.face_of(0, 139.767 + 90) == 1
    assert pf.face_of(0, 139.767 - 90) == 3
    assert pf.face_of(0, 139.767 + 180) == 2
    assert pf.face_of(80, 0) == 4 and pf.face_of(-80, 0) == 5


def snaps(**tracks):
    """tracks: callsign -> list of (lat, lon) or None per key"""
    keys = max(len(v) for v in tracks.values())
    out = {str(T0 + 900 * i): [] for i in range(keys)}
    for cs, pts in tracks.items():
        for i, p in enumerate(pts):
            if p:
                out[str(T0 + 900 * i)].append([p[0], p[1], 90.0, cs, "A320", 0])
    return out


def test_tracks_by_callsign_with_gaps():
    keys, tracks = pf.tracks(snaps(JAL5=[(35, 139), None, (36, 140)], ANA1=[None, (10, 10)]))
    assert keys == [T0, T0 + 900, T0 + 1800]
    assert tracks["JAL5"] == [(35, 139), None, (36, 140)]
    assert tracks["ANA1"] == [None, (10, 10), None]


def test_select_keeps_each_face_under_the_cap_at_every_key():
    near_tokyo = [(35, 139)] * 3
    t = {f"JAL{i}": near_tokyo for i in range(10)}
    t["DLH1"] = [(50, 8)] * 3  # another face, not crowded
    keys, tr = pf.tracks(snaps(**t))
    picked = pf.select(tr, cap=4, seed=1)
    assert sum(1 for c in picked if c.startswith("JAL")) == 4
    assert "DLH1" in picked


def test_pack_layout():
    keys, tr = pf.tracks(snaps(JAL5=[(35.123, 139.456), None], ANA1=[None, (-10.5, -179.99)]))
    b = pf.pack(keys, tr, ["JAL5", "ANA1"])
    assert b[:4] == b"CEF1"
    nk, step, t0, n = struct.unpack_from("<HHII", b, 4)
    assert (nk, step, t0, n) == (2, 15, T0, 2)
    assert len(b) == 16 + 2 * (8 + 2 * 4)
    assert b[16:24] == b"JAL5\0\0\0\0"
    assert struct.unpack_from("<4h", b, 24) == (3512, 13946, -32768, -32768)
    assert struct.unpack_from("<4h", b, 16 + 16 + 8) == (-32768, -32768, -1050, -17999)
