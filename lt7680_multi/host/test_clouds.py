"""Offline tests for clouds.py (sampling, QSC faces, RGB565) and clouds_hourly.py (Mercator band, turns, time list, fetch).

    uv run -q --no-project --with pytest --with numpy --with pillow --with pyproj python -m pytest -q test_clouds.py
"""
import io
import json

import numpy as np
import pytest
from PIL import Image

import clouds
import clouds_hourly as ch


def lonlat_ramp(w=360, h=180):
    """R = pixel column, G = pixel row, B = 0: every sample says where it came from."""
    img = np.zeros((h, w, 3), dtype=np.float32)
    img[..., 0] = np.arange(w)[None, :]
    img[..., 1] = np.arange(h)[:, None]
    return img


# ---- sample ----

def test_sample_at_a_pixel_centre_returns_that_pixel():
    img = lonlat_ramp()
    # pixel (x=100, y=50) has its centre at lon = (100.5/360 - 0.5)*360, lat = (0.5 - 50.5/180)*180
    lon, lat = 100.5 - 180, 90 - 50.5
    out = clouds.sample(img, np.array([lon]), np.array([lat]))
    assert out[0] == pytest.approx([100, 50, 0], abs=1e-3)


def test_sample_is_bilinear_between_two_pixels():
    img = np.zeros((2, 4, 3), dtype=np.float32)
    img[:, 1] = 100.0
    # lon at the boundary between columns 0 and 1 (x=0.5 pixel units from centre 0): halfway
    lon = (1.0 / 4 - 0.5) * 360  # the edge between column 0 and column 1
    out = clouds.sample(img, np.array([lon]), np.array([0.0]))
    assert out[0, 0] == pytest.approx(50.0, abs=1e-3)


def test_sample_blends_column_359_with_column_0_across_the_seam():
    img = lonlat_ramp()
    # lon = 180 is the edge between the last column (R=359) and the first (R=0): halfway is 179.5 only if it wraps
    for lon in (180.0, -180.0, 540.0):
        out = clouds.sample(img, np.array([lon]), np.array([0.0]))
        assert out[0, 0] == pytest.approx(179.5, abs=1e-3)


def test_sample_clamps_at_the_poles_instead_of_failing():
    img = lonlat_ramp()
    top = clouds.sample(img, np.array([0.0]), np.array([90.0]))
    bottom = clouds.sample(img, np.array([0.0]), np.array([-90.0]))
    assert top[0, 1] == pytest.approx(0.0, abs=0.51)
    assert bottom[0, 1] == pytest.approx(179.0, abs=0.51)


# ---- face ----

def test_a_face_of_a_uniform_image_is_uniform():
    img = np.full((180, 360, 3), 77.0, dtype=np.float32)
    f = clouds.face(img, 90.0, 0.0, 16)
    assert f.shape == (16, 16, 3)
    assert f == pytest.approx(77.0, abs=1e-3)


@pytest.mark.parametrize("lon0", [0.0, 90.0, 139.767, -120.0])
def test_a_side_face_is_centred_on_its_lon0(lon0):
    img = lonlat_ramp()
    n = 31  # odd, so there is a centre pixel
    f = clouds.face(img, lon0, 0.0, n)
    mid = f[n // 2, n // 2]
    want_x = (lon0 / 360.0 + 0.5) % 1.0 * 360 - 0.5
    assert mid[0] == pytest.approx(want_x, abs=1.0)
    assert mid[1] == pytest.approx(89.5, abs=1.0)  # the equator


def test_a_side_face_has_north_up_and_east_to_the_right():
    img = lonlat_ramp()
    f = clouds.face(img, 90.0, 0.0, 31)
    assert f[0, 15, 1] < f[-1, 15, 1]  # image rows grow southward: the top of the face is the north
    assert f[15, 0, 0] < f[15, -1, 0]  # columns grow eastward (no wrap at lon0 = 90)


# ---- rgb565 ----

@pytest.mark.parametrize("rgb,want", [((0, 0, 0), 0x0000), ((255, 255, 255), 0xFFFF), ((255, 0, 0), 0xF800), ((0, 255, 0), 0x07E0), ((0, 0, 255), 0x001F)])
def test_rgb565_primaries(rgb, want):
    px = np.array([[rgb]], dtype=np.float32)
    assert int(clouds.rgb565(px)[0, 0]) == want


def test_rgb565_clips_out_of_range_values():
    px = np.array([[(300.0, -20.0, 255.4)]], dtype=np.float32)
    assert int(clouds.rgb565(px)[0, 0]) == 0xF81F


# ---- clouds_hourly ----

def test_turned_is_clockwise_quarter_turns():
    a = np.array([[1, 2], [3, 4]])
    assert ch.turned(a, 0).tolist() == [[1, 2], [3, 4]]
    assert ch.turned(a, 1).tolist() == [[3, 1], [4, 2]]
    assert ch.turned(a, 2).tolist() == [[4, 3], [2, 1]]
    assert ch.turned(a, 4).tolist() == [[1, 2], [3, 4]]


def test_equirect_is_nan_beyond_85_degrees_and_filled_inside():
    band = np.full((512, 1024), 200.0, dtype=np.float32)
    out = ch.equirect(band)
    assert out.shape == (ch.H, ch.W)
    lat = 90 - (np.arange(ch.H) + 0.5) / ch.H * 180
    assert np.isnan(out[np.abs(lat) > 85]).all()
    assert (out[np.abs(lat) <= 85] == 200.0).all()


def test_equirect_puts_the_equator_in_the_middle_of_the_mercator_band():
    rows = np.arange(512, dtype=np.float32)[:, None] * np.ones((1, 1024), dtype=np.float32)
    out = ch.equirect(rows)
    lat = 90 - (np.arange(ch.H) + 0.5) / ch.H * 180
    eq = int(np.argmin(np.abs(lat)))
    assert out[eq, 0] == pytest.approx(256, abs=2)
    assert out[eq - 100, 0] < out[eq, 0] < out[eq + 100, 0]  # north is the top of the band


def test_equirect_keeps_longitude_columns_in_order():
    cols = np.ones((512, 1)) * np.arange(1024, dtype=np.float32)[None, :]
    out = ch.equirect(cols.astype(np.float32))
    row = out[ch.H // 2]
    assert (np.diff(row) >= 0).all()
    assert row[0] < 2 and row[-1] > 1021


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


def test_times_returns_the_newest_hours_in_order(monkeypatch):
    meta = [{"times": ["20261107.100000", "20261107.080000", "20261107.090000", "20261107.110000"]}]
    monkeypatch.setattr(ch.urllib.request, "urlopen", lambda *a, **k: FakeResponse(json.dumps(meta).encode()))
    assert ch.times(2, None) == ["20261107.100000", "20261107.110000"]


def test_times_can_stop_at_an_end_time(monkeypatch):
    import datetime as dt

    meta = [{"times": ["20261107.080000", "20261107.090000", "20261107.100000", "20261107.110000"]}]
    monkeypatch.setattr(ch.urllib.request, "urlopen", lambda *a, **k: FakeResponse(json.dumps(meta).encode()))
    assert ch.times(10, dt.datetime(2026, 11, 7, 9, 30)) == ["20261107.080000", "20261107.090000"]


def png_bytes(value):
    buf = io.BytesIO()
    Image.new("L", (4, 4), value).save(buf, "PNG")
    return buf.getvalue()


def test_fetch_downloads_once_and_reuses_the_file(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ch.urllib.request, "urlopen", lambda url, **k: (calls.append(url), FakeResponse(png_bytes(90)))[1])
    a = ch.fetch("20261107.100000", str(tmp_path))
    b = ch.fetch("20261107.100000", str(tmp_path))
    assert len(calls) == 1
    assert "time=2026-11-07+10:00" in calls[0]
    assert a.shape == (4, 4) and (a == 90).all() and (b == a).all()


def test_fetch_refuses_a_watermarked_or_error_reply(monkeypatch, tmp_path):
    monkeypatch.setattr(ch.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"<html>Size limit exceeded</html>"))
    with pytest.raises(SystemExit):
        ch.fetch("20261107.100000", str(tmp_path))
    assert not list(tmp_path.iterdir())  # nothing half-written is left to be reused
