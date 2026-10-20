"""qsc.py (the C port's reference) against PROJ's +proj=qsc, face by face.

    uv run -q --no-project --with pyproj --with numpy --with pytest python -m pytest -q test_qsc.py
"""
import numpy as np
import pytest
from pyproj import Proj

import qsc

LON0 = 139.767
N = 480


def proj_pixel(face, lon, lat):
    """Pixel of (lon, lat) in face `face` the way make_qsc_faces.py draws it."""
    lat0, lon_c = {4: (90, LON0), 5: (-90, LON0)}.get(face, (0, LON0 + 90 * face))
    p = Proj(f"+proj=qsc +R=1 +lat_0={lat0} +lon_0={lon_c}")
    L, _ = Proj(f"+proj=qsc +R=1 +lat_0=0 +lon_0={lon_c}")(lon_c + 45.0, 0.0)
    x, y = p(lon, lat)
    return (x + L) / (2 * L) * N, (L - y) / (2 * L) * N


def test_face_centres():
    assert qsc.to_face_pixel(0.0, LON0, LON0, N)[:1] == (0,)
    for k in range(4):
        f, x, y = qsc.to_face_pixel(0.0, LON0 + 90 * k, LON0, N)
        assert f == k and x == pytest.approx(N / 2) and y == pytest.approx(N / 2)
    assert qsc.to_face_pixel(89.9999, 0.0, LON0, N)[0] == 4
    assert qsc.to_face_pixel(-89.9999, 0.0, LON0, N)[0] == 5


def test_matches_proj_everywhere():
    rng = np.random.default_rng(1)
    v = rng.normal(size=(4000, 3))
    v /= np.linalg.norm(v, axis=1)[:, None]
    lats, lons = np.degrees(np.arcsin(v[:, 2])), np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    seen = set()
    for lat, lon in zip(lats, lons):
        f, x, y = qsc.to_face_pixel(lat, lon, LON0, N)
        seen.add(f)
        px, py = proj_pixel(f, lon, lat)
        assert x == pytest.approx(px, abs=1e-6) and y == pytest.approx(py, abs=1e-6), (lat, lon, f)
        assert 0 <= x <= N and 0 <= y <= N
    assert seen == set(range(6))
