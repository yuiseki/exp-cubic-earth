"""A triangular board inside a module's corner, square to the cube's diagonal.

The three panel backs of the first module meet at the inner corner
Q = (h, -h, h), h = edge/2 - panel thickness. The board lies in a plane
square to the diagonal through Q, at distance t from Q toward the cube's
centre; its centre is on the diagonal. Seen from the cube's centre, its
three corners point along the three panel-back edges that meet at Q when
turn = 0 (then the board's corners reach into the creases between two
panels), or between them when turn = 60 (its sides face the creases).

The board is a slab: its back (the side toward Q) on the plane, and
`front` mm of PCB and parts toward the cube's centre.

An equilateral triangle that just touches the three panel backs at
distance t has side sqrt(6) * t (turn = 0).
"""
import numpy as np

import geometry as g

FRONT = 1.6 + 5.0  # PCB plus the tallest part (the XIAO on its pads, the FFC connectors)


def inner_corner(edge):
    h = edge / 2 - g.PANEL_SIZE[2]
    return np.array([h, -h, h])


def plane_axes():
    """Two unit vectors in the board's plane: u toward the crease along -x
    (between the A and top panels), v a quarter turn on (right-handed about
    the diagonal pointing out of the corner)."""
    d = g.CORNER
    u = np.array([-1.0, 0.0, 0.0]) - d * (d @ [-1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def triangle(edge, t, side, turn=0.0):
    """The board's three corners on its back plane (world, first module)."""
    centre = inner_corner(edge) - g.CORNER * t
    u, v = plane_axes()
    r = side / np.sqrt(3)
    angles = np.radians(turn + np.array([0.0, 120.0, 240.0]))
    return np.array([centre + r * (np.cos(a) * u + np.sin(a) * v) for a in angles])


def slab(edge, t, side, turn=0.0, front=FRONT):
    tri = triangle(edge, t, side, turn)
    return np.vstack([tri, tri - g.CORNER * front])


def _separated(a, b, axis, tol):
    if np.linalg.norm(axis) < 1e-9:
        return False
    axis = axis / np.linalg.norm(axis)
    pa, pb = a @ axis, b @ axis
    return pa.max() <= pb.min() + tol or pb.max() <= pa.min() + tol


def slab_hits_box(prism, box, tol=0.01):
    """Separating-axis test between the triangular slab and an axis-aligned box."""
    boxp = g.corners(box)
    tri = prism[:3]
    edges = [tri[1] - tri[0], tri[2] - tri[1], tri[0] - tri[2], g.CORNER]
    axes = list(np.eye(3)) + [g.CORNER] + [np.cross(e, tri[1] - tri[0]) for e in edges[:3]]
    axes += [np.cross(a, e) for a in np.eye(3) for e in edges]
    return not any(_separated(prism, boxp, ax, tol) for ax in axes)


def obstacles(plan, edge):
    return [(label, box) for f in plan.faces for label, box in g.part_boxes(f, edge)]


def hits(plan, edge, t, side, turn=0.0, front=FRONT):
    prism = slab(edge, t, side, turn, front)
    return [label for label, box in obstacles(plan, edge) if slab_hits_box(prism, box)]


def largest_side(plan, edge, t, turn=0.0, front=FRONT):
    lo, hi = 0.0, 200.0
    if hits(plan, edge, t, 0.01, turn, front):
        return 0.0
    while hi - lo > 0.05:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if not hits(plan, edge, t, mid, turn, front) else (lo, mid)
    return lo
