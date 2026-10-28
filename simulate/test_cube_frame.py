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
