"""cube_frame.py: corner joints on all 8 vertices and bars on all 12 edges (from the boxes, no CAD).

    uv run --no-project --with numpy --with pytest python -m pytest -q test_cube_frame.py
"""
import numpy as np
import pytest

import cube_frame as cf

H = cf.OUT_EDGE / 2


def test_counts_and_bar_length():
    assert len(cf.vertices()) == 8
    assert len(cf.edges()) == 12
    assert cf.BAR_LENGTH == pytest.approx(cf.OUT_EDGE - 2 * cf.JOINT_ARM)


def test_panels_are_centred_with_their_glass_wall_plus_clear_inside():
    for f in cf.faces():
        lo, hi = cf.panel_box(f)
        i = int(np.flatnonzero(f.normal)[0])
        s = f.normal[i]
        front = hi[i] if s > 0 else -lo[i]
        assert front == pytest.approx(H - cf.WALL - cf.CLEAR)
        for j in range(3):
            if j != i:
                assert lo[j] == pytest.approx(-hi[j])
                assert H - hi[j] >= cf.EDGE_AT - 1e-9  # no panel edge deeper into a slot than its bottom


def test_every_part_misses_every_panel():
    rng = np.random.default_rng(4)
    boxes = [cf.panel_box(f) for f in cf.faces()]
    hits = 0
    for _ in range(20000):
        p = rng.uniform(-H, H, 3)
        p[rng.integers(3)] = rng.choice([-1, 1]) * rng.uniform(H - 8, H)  # near a face
        if cf.part_at(p) is not None:
            hits += 1
            assert not any(np.all(p > lo + 1e-6) and np.all(p < hi - 1e-6) for lo, hi in boxes), p
    assert hits > 500


def test_a_point_belongs_to_one_joint_or_one_bar():
    # near a vertex: a joint; half way along an edge: a bar
    v = np.array([1, 1, 1]) * (H - 0.5)
    assert cf.part_at(v)[0] == "joint"
    e = np.array([0.0, H - 0.5, H - 0.5])
    assert cf.part_at(e)[0] == "bar"


def test_lay_flat_puts_the_axis_on_x_and_the_face_on_the_floor():
    tri = np.array([[[0.0, 0.0, 5.0], [0.0, 10.0, 5.0], [1.0, 0.0, 4.0]]])  # along y, outer face z = 5 (normal +z)
    flat = cf.lay_flat(tri, 1, (0, 0, 1))
    assert flat[..., 0].max() == pytest.approx(10)  # y became x
    assert flat[0, 0, 2] == pytest.approx(0) and flat[0, 2, 2] == pytest.approx(1)  # the face at z = 5 is now the floor


def test_slots_reach_their_full_depth_on_every_edge():
    # half way along any edge, a point in each slot just above its bottom is empty, whatever panel sits there
    for k, (i, si), (j, sj) in cf.edges():
        for (a, sa), (b, sb) in (((i, si), (j, sj)), ((j, sj), (i, si))):
            p = np.zeros(3)
            p[a] = sa * (H - cf.WALL - cf.SLOT / 2)
            p[b] = sb * (H - cf.EDGE_AT - 0.05)
            assert cf.part_at(p) is None


def test_no_slot_breaks_through_an_outer_face():
    # every point just under an outer face, inside the outer walls' depth, is frame or nothing but never a slot
    rng = np.random.default_rng(5)
    for _ in range(4000):
        p = rng.uniform(-H, H, 3)
        a = rng.integers(3)
        p[a] = rng.choice([-1, 1]) * (H - rng.uniform(0, cf.WALL * 0.9))
        for _, (lo, hi) in cf.slot_boxes():
            assert not (np.all(p > lo) and np.all(p < hi)), p
