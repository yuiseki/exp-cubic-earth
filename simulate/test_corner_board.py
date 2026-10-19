import numpy as np
import pytest

import corner_board as cb
import geometry as g

EDGE = 81.69
PLAN = g.Plan({"top": "-x", "A": "-z", "B": "+y"})


def test_triangle_is_equilateral_square_to_the_diagonal_and_centred_on_it():
    tri = cb.triangle(EDGE, 20, 30)
    sides = [np.linalg.norm(tri[i] - tri[(i + 1) % 3]) for i in range(3)]
    assert np.allclose(sides, 30)
    assert np.allclose((tri - tri.mean(0)) @ g.CORNER, 0)
    centre = tri.mean(0) - cb.inner_corner(EDGE)
    assert np.allclose(centre, -g.CORNER * 20)


def test_corners_touch_the_panel_backs_at_side_sqrt6_t():
    t = 10.0
    tri = cb.triangle(EDGE, t, np.sqrt(6) * t)
    h = EDGE / 2 - g.PANEL_SIZE[2]
    # each corner lies on a crease: two of |x|, |y|, |z| equal h
    for p in tri:
        assert sum(np.isclose(abs(p), h)) == 2


def test_separating_axis_test():
    prism = cb.slab(EDGE, 20, 30)
    lo, hi = prism.min(0), prism.max(0)
    assert cb.slab_hits_box(prism, (lo - 1, hi + 1))
    assert not cb.slab_hits_box(prism, (hi + 1, hi + 2))
    # a box in the bounding box's corner but off the slab
    far = cb.inner_corner(EDGE)
    assert not cb.slab_hits_box(prism, (far - 0.5, far))


def test_a_small_board_fits_and_a_huge_one_does_not():
    assert cb.hits(PLAN, EDGE, 25, 10) == []
    assert cb.hits(PLAN, EDGE, 25, 150) != []


def test_largest_side_is_tight():
    side = cb.largest_side(PLAN, EDGE, 25)
    assert side > 0
    assert cb.hits(PLAN, EDGE, 25, side) == []
    assert cb.hits(PLAN, EDGE, 25, side + 0.1) != []
