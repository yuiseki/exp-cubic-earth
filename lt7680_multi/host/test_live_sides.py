"""uv run -q --no-project --with numpy --with pillow --with pyproj --with pytest python -m pytest -q test_live_sides.py"""
import numpy as np

import live_sides


def rotated_index(x, y, r, n):
    """lt7680_multi's rotate.h: the source pixel shown at panel (x, y) for r clockwise quarter turns."""
    return {0: y * n + x, 1: (n - 1 - x) * n + y, 2: (n - 1 - y) * n + (n - 1 - x), 3: x * n + (n - 1 - y)}[r % 4]


def test_panel_view_matches_the_firmware_rotation():
    n = 5
    face = np.arange(n * n).reshape(n, n)
    for r in range(4):
        panel = live_sides.panel_view(face, r)
        for y in range(n):
            for x in range(n):
                assert panel[y, x] == face.flat[rotated_index(x, y, r, n)]


def test_modules_parse_board_faces_and_turns():
    mods = live_sides.parse_modules(["north=0:1,4:2,3:0", "south=1:3,5:3,2:2"])
    assert mods == {"north": [(0, 1), (4, 2), (3, 0)], "south": [(1, 3), (5, 3), (2, 2)]}


def test_side_names():
    assert live_sides.side_name("north", 0) == "north-side-a.jpg"
    assert live_sides.side_name("south", 2) == "south-side-c.jpg"


def test_caps_beyond_85_degrees_take_the_ring_mean():
    lat = np.array([89.0, 86.0, 84.9, 0.0, -84.9, -86.0])[:, None] * np.ones((1, 4))
    a = np.array([[np.nan] * 4, [np.nan] * 4, [0.2, 0.4, 0.6, 0.8], [0.0] * 4, [1.0, 1.0, 0.0, 0.0], [np.nan] * 4])
    out = live_sides.fill_caps(a, lat)
    assert np.allclose(out[0], 0.5) and np.allclose(out[1], 0.5)  # north cap: mean of the 84.9 ring
    assert np.allclose(out[5], 0.5)  # south cap
    assert np.allclose(out[2:5], a[2:5])  # the rest untouched
