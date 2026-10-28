"""scene_compose.py: cloud alpha, the sun's position and the day/night blend.

    uv run -q --no-project --with numpy --with pillow --with pyproj --with pytest python -m pytest -q test_scene_compose.py
"""
import datetime as dt

import numpy as np
import pytest

import scene_compose as sc


def test_cloud_alpha_is_how_much_brighter_than_the_cloudless_ground():
    ground = np.array([[[20, 40, 80], [200, 180, 140], [20, 40, 80]]], dtype=np.float32)  # sea, desert, sea
    sat = np.array([[[20, 40, 80], [205, 185, 145], [240, 240, 240]]], dtype=np.float32)  # clear sea, clear desert, cloud
    a = sc.cloud_alpha(sat, ground)
    assert a[0, 0] == pytest.approx(0, abs=0.02)
    assert a[0, 1] < 0.1  # a bright desert is not a cloud
    assert a[0, 2] > 0.9


def test_cloud_alpha_is_zero_where_the_mosaic_has_no_data():
    ground = np.full((1, 1, 3), 30, dtype=np.float32)
    assert sc.cloud_alpha(np.zeros((1, 1, 3), dtype=np.float32), ground)[0, 0] == 0


def test_subsolar_point_at_the_march_equinox_noon_utc():
    lat, lon = sc.subsolar(dt.datetime(2026, 3, 20, 12, 0, tzinfo=dt.timezone.utc))
    assert abs(lat) < 1
    assert abs(lon) < 5  # the equation of time is a few minutes


def test_subsolar_latitude_at_the_june_solstice():
    lat, _ = sc.subsolar(dt.datetime(2026, 6, 21, 0, 0, tzinfo=dt.timezone.utc))
    assert lat == pytest.approx(23.44, abs=0.3)


def test_daylight_is_one_under_the_sun_zero_opposite_and_soft_at_the_terminator():
    lat = np.array([0.0, 0.0, 0.0])
    lon = np.array([0.0, 180.0, 90.0])
    d = sc.daylight(lat, lon, 0.0, 0.0)
    assert d[0] == 1 and d[1] == 0
    assert 0 < d[2] < 1


def test_compose_keeps_city_lights_under_thin_night_clouds():
    day = np.full((1, 1, 3), 100, dtype=np.float32)
    night = np.full((1, 1, 3), 200, dtype=np.float32)  # a city
    out = sc.compose(day, night, alpha=np.ones((1, 1)), light=np.zeros(1).reshape(1, 1), opacity=0.5)
    assert out[0, 0, 0] > 60  # half the lights still come through
