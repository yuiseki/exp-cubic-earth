"""layers.py: tile coordinates, line and point drawing on the equirectangular canvas.

    uv run -q --no-project --with numpy --with pillow --with pytest python -m pytest -q test_layers.py
"""
import numpy as np
import pytest

import layers


def test_tile_pixel_to_lonlat():
    # the top left of tile z1 (0, 0) is (-180, 85.05), its bottom right (0, 0)
    lon, lat = layers.tile_lonlat(1, 0, 0, np.array([0.0, 4096.0]), np.array([0.0, 4096.0]), 4096)
    assert lon[0] == pytest.approx(-180) and lat[0] == pytest.approx(85.0511, abs=1e-3)
    assert lon[1] == pytest.approx(0) and lat[1] == pytest.approx(0, abs=1e-9)


def test_lonlat_to_canvas_pixel():
    x, y = layers.canvas_xy(np.array([-180.0, 0.0]), np.array([90.0, 0.0]), 400, 200)
    assert x[0] == pytest.approx(0) and y[0] == pytest.approx(0)
    assert x[1] == pytest.approx(200) and y[1] == pytest.approx(100)


def test_lines_light_their_pixels_and_skip_the_antimeridian_jump():
    canvas = layers.Canvas(400, 200, supersample=1)
    canvas.line(np.array([-10.0, 10.0]), np.array([0.0, 0.0]))
    canvas.line(np.array([179.0, -179.0]), np.array([45.0, 45.0]))  # crosses the date line: no line across the map
    a = canvas.alpha()
    assert a[100, 195:205].min() > 0.5
    assert a[50, 10:390].max() == 0


def test_points_and_alpha_range():
    canvas = layers.Canvas(400, 200, supersample=2)
    canvas.points(np.array([0.0]), np.array([0.0]), radius=2)
    a = canvas.alpha()
    assert a.shape == (200, 400) and a.max() <= 1 and a[100, 200] > 0.5 and a[0, 0] == 0


def test_density_glow_is_log_scaled_and_zero_where_nobody_lives():
    g = layers.density(np.array([0.0, 0.0, 90.0]), np.array([0.0, 0.0, 0.0]), np.array([1000.0, 1000.0, 10.0]), 400, 200, blur=0)
    assert g[100, 200] == pytest.approx(1)
    assert 0 < g[100, 300] < g[100, 200]
    assert g[10, 10] == 0


def test_density_reaches_one_after_blurring():
    g = layers.density(np.array([0.0]), np.array([0.0]), np.array([1000.0]), 400, 200, blur=2)
    assert g.max() == pytest.approx(1)
