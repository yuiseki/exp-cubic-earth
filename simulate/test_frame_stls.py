"""The print STLs in hardware/frame: one connected piece each, the sizes and volumes the README states,
and the -deep pair is the original pair with the slot 1.0 mm deeper (same outer edge, section 1.0 mm bigger).

    uv run -q --no-project --with numpy --with numpy-stl --with pytest python -m pytest -q test_frame_stls.py
"""
import os

import numpy as np
import pytest
from stl import mesh

FRAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "frame")


def load(name):
    return mesh.Mesh.from_file(os.path.join(FRAME, name)).vectors.astype(float)


def pieces(tris):
    pts = np.round(tris.reshape(-1, 3), 4)
    _, idx = np.unique(pts, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    parent = list(range(int(idx.max()) + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in idx:
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    return len({find(int(t)) for t in idx[:, 0]})


def volume_cm3(tris):
    return abs(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum() / 6) / 1000


def size(tris):
    p = tris.reshape(-1, 3)
    return np.sort(p.max(0) - p.min(0))


def watertight(tris):
    """Every edge is shared by exactly two triangles (so the slicer sees a closed solid)."""
    pts = np.round(tris.reshape(-1, 3), 4)
    _, idx = np.unique(pts, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    edges = np.concatenate([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]])
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool((counts == 2).all())


NAMES = ["joint.stl", "bar.stl", "joint-deep.stl", "bar-deep.stl"]


@pytest.mark.parametrize("name", NAMES)
def test_each_part_is_one_closed_piece(name):
    t = load(name)
    assert pieces(t) == 1
    assert watertight(t)


@pytest.mark.parametrize("name,want_size,want_cm3", [
    ("joint.stl", (20.0, 20.0, 20.0), 1.46),
    ("bar.stl", (6.88, 6.88, 45.5), 1.37),
    ("joint-deep.stl", (20.0, 20.0, 20.0), 1.62),
    ("bar-deep.stl", (7.88, 7.88, 45.5), 1.57),
])
def test_sizes_and_volumes_match_the_readme(name, want_size, want_cm3):
    t = load(name)
    assert size(t) == pytest.approx(want_size, abs=0.01)
    assert volume_cm3(t) == pytest.approx(want_cm3, abs=0.01)


def test_the_deep_pair_is_the_original_with_a_section_one_millimetre_bigger():
    bar, deep = size(load("bar.stl")), size(load("bar-deep.stl"))
    assert deep[2] == pytest.approx(bar[2])  # same length
    assert deep[:2] == pytest.approx(bar[:2] + 1.0, abs=0.01)
    assert size(load("joint-deep.stl")) == pytest.approx(size(load("joint.stl")))  # the arm length does not change


def test_the_deep_pair_holds_more_resin_so_the_slot_cannot_have_shrunk():
    assert volume_cm3(load("joint-deep.stl")) > volume_cm3(load("joint.stl"))
    assert volume_cm3(load("bar-deep.stl")) > volume_cm3(load("bar.stl"))


def test_the_readme_lists_every_part():
    text = open(os.path.join(FRAME, "README.md"), encoding="utf-8").read()
    for name in NAMES:
        assert f"`{name}`" in text
