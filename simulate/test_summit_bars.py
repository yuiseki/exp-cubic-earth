"""summit_bars.py: the slotted bars and the inner corner bracket (from the boxes, no CAD).

    uv run --no-project --with numpy --with pytest python -m pytest -q test_summit_bars.py
"""
import numpy as np
import pytest

import geometry as g
import summit_bars as sb

H = sb.OUT_EDGE / 2


def at(depths):
    """World point at the given depths from the outer faces of top (z), A (-y) and B (x)."""
    d = np.asarray(depths, float)
    return np.array([H - d[2], -(H - d[1]), H - d[0]])


def test_section_numbers():
    assert sb.SLOT == pytest.approx(2.38)
    assert sb.SIZE == pytest.approx(6.88)
    assert sb.EDGE_AT == pytest.approx(4.38)


def test_panels_sit_in_their_slots_and_stop_short_of_the_other_slot():
    fs = sb.first_module_faces()
    lo, hi = sb.panel_box(fs["top"])
    # the top panel: front 1.1 below the top's outer face, edges 4.38 in from A's and B's outer faces
    assert hi[2] == pytest.approx(H - sb.WALL - sb.CLEAR)
    assert hi[0] == pytest.approx(H - sb.EDGE_AT)
    assert lo[1] == pytest.approx(-H + sb.EDGE_AT)


def test_bar_section_on_the_top_B_seam():
    # half way along the seam (y = 0): depth from top's face, depth from B's face
    def solid(dt, db):
        return sb.solid_at(at((dt, 40, db)))
    assert solid(0.5, 0.5)            # the outer corner
    assert solid(0.5, 6.5)            # wall in front of the top panel
    assert not solid(2.0, 6.0)        # the top panel's slot
    assert not solid(6.0, 2.0)        # the B panel's slot
    assert solid(4.0, 4.0)            # the core between the slots
    assert not solid(6.0, 6.0)        # the inner corner is cut away
    assert not solid(0.5, 7.5)        # past the bar


def test_bars_and_bracket_miss_every_panel():
    fs = sb.first_module_faces()
    rng = np.random.default_rng(1)
    for _ in range(4000):
        d = rng.uniform(0, 20, 3)
        p = at(d)
        if sb.solid_at(p) or sb.bracket_at(p):
            for f in fs.values():
                lo, hi = sb.panel_box(f)
                assert not (np.all(p > lo + 1e-6) and np.all(p < hi - 1e-6)), (d, f.name)


def test_bracket_sits_behind_all_three_panels_and_never_inside_a_bar():
    rng = np.random.default_rng(2)
    n = 0
    for _ in range(6000):
        d = rng.uniform(0, 20, 3)
        if sb.bracket_at(at(d)):
            n += 1
            assert np.all(d >= sb.WALL + sb.SLOT - 1e-9)
            assert not sb.solid_at(at(d))
    assert n > 100


def test_bracket_wraps_each_bar_end():
    # near the corner, behind both of its panels, the top/B bar is an L of back walls (depths 3.38-4.58);
    # the bracket fills the inner corner of that L, so the bar end sits in the bracket's pocket
    assert sb.solid_at(at((4.0, 8.0, 4.0)))
    assert sb.bracket_at(at((5.2, 8.0, 5.2)))
    assert not sb.bracket_at(at((4.0, 8.0, 4.0)))


def test_owner_splits_the_corner_by_mitres():
    assert sb.owner(at((1, 1, 30))) != sb.owner(at((1, 30, 1)))
