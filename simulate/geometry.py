"""Where each part of a face goes, and the two corner modules of the cube.

A face is one ER-TFT040-3 panel with its ER-PCBA5981-1 board folded onto
the back. Its parts are given in the panel frame of docs/DIMENSIONS.md:
seen from the display side with the FPC edge down, origin at the panel's
lower left corner, X right, Y up, Z toward the viewer (Z = 0 on the glass).

The cube's centre is the world origin. A face is placed by its outward
normal and the direction its FPC edge points to (both world axes), with
its glass at edge/2 from the centre. The first module is top + A + B, the
faces around the corner (+x, -y, +z). The second module is the same
module turned half way round about the axis (1, 1, 0), which takes the
corner to (-x, +y, -z) and top, A, B to bottom, C, D.
"""
import itertools
from dataclasses import dataclass

import numpy as np

PANEL_SIZE = (74.66, 76.54, 2.18)
PANEL_CENTER = np.array([PANEL_SIZE[0] / 2, PANEL_SIZE[1] / 2, 0.0])
BOARD_GAP = 0.2  # tape between the panel back and the board
BOARD_EDGE_FROM_FPC_EDGE = 20.0  # measured on the folded board

# Boxes as (low corner, high corner) in the panel frame.
PANEL = ((0.0, 0.0, -PANEL_SIZE[2]), (PANEL_SIZE[0], PANEL_SIZE[1], 0.0))
BOARD_FLAT = ((21.33, -70.09, -2.70), (53.33, -21.89, 1.62))  # as in the STEP


def box_of(points):
    p = np.asarray(points, float).reshape(-1, 3)
    return p.min(0), p.max(0)


def corners(box):
    lo, hi = np.asarray(box[0], float), np.asarray(box[1], float)
    return np.array([[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)])


def _fold_offset():
    flipped = corners(BOARD_FLAT) * [1, -1, -1]
    lo, hi = box_of(flipped)
    return np.array([0.0, BOARD_EDGE_FROM_FPC_EDGE - lo[1], -PANEL_SIZE[2] - BOARD_GAP - hi[2]])


FOLD_OFFSET = _fold_offset()


def fold_board(points):
    """Fold the FPC: the board turns over about the panel's bottom edge and
    lies on the back, parts side facing away from the panel."""
    return np.asarray(points, float) * [1, -1, -1] + FOLD_OFFSET


BOARD_FOLDED = box_of(fold_board(corners(BOARD_FLAT)))
_bz = BOARD_FOLDED[1][2]  # board side touching the panel back (tape)
_con1_lo, _con1_hi = 41.56, 67.86  # CON1 along Y once folded
# The FFC from CON1 toward the panel edge on the CON1 side (X = 74.66).
# Drawn 2mm past the edge to show where it leaves; it bends there.
FFC_STUB = ((53.33, (_con1_lo + _con1_hi) / 2 - 10.5, _bz - 1.6 - 1.1), (PANEL_SIZE[0] + 2.0, (_con1_lo + _con1_hi) / 2 + 10.5, _bz - 1.6 - 1.0))
# The panel FPC folded round the bottom edge and lying on the back up to CON2.
FPC = [
    ((24.69, -0.3, -PANEL_SIZE[2] - 0.1), (52.69, 0.0, 0.0)),
    ((24.69, 0.0, -PANEL_SIZE[2] - 0.1), (52.69, 3.0, -PANEL_SIZE[2])),
    ((19.12, 3.0, -PANEL_SIZE[2] - 0.6), (52.69, 14.5, -PANEL_SIZE[2])),
    ((27.08, 14.5, -PANEL_SIZE[2] - 0.1), (47.58, 20.0, -PANEL_SIZE[2])),
]

TURN = np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]], float)
PARTNER = {"top": "bottom", "A": "C", "B": "D"}
FIRST = {"top": (0, 0, 1), "A": (0, -1, 0), "B": (1, 0, 0)}


def face_rotation(normal, fpc):
    """Rotation taking the panel frame to the world: Z to the normal, -Y to
    the direction the FPC edge points to."""
    z, down = np.array(normal, float), np.array(fpc, float)
    if abs(z @ down) > 1e-9:
        raise ValueError(f"FPC direction {fpc} is not in the face with normal {normal}")
    y = -down
    return np.column_stack([np.cross(y, z), y, z])


def axis_name(v):
    v = np.round(np.asarray(v, float)).astype(int)
    i = int(np.flatnonzero(v)[0])
    return ("+" if v[i] > 0 else "-") + "xyz"[i]


def parse_axis(s):
    v = np.zeros(3)
    v["xyz".index(s[1])] = 1 if s[0] == "+" else -1
    return v


PINWHEEL_CLEARANCE = 0.1  # between a tucked panel's edge and the back of the panel in front of it


@dataclass
class Face:
    name: str
    module: int
    normal: np.ndarray
    fpc: np.ndarray
    # (direction, depth): the panel's outline reaches edge/2 - depth along
    # that world direction (a neighbour's normal). Empty: centred on the face.
    reach: tuple = ()

    @property
    def rotation(self):
        return face_rotation(self.normal, self.fpc)

    def place(self, points, edge):
        out = (np.asarray(points, float) - PANEL_CENTER) @ self.rotation.T + self.normal * edge / 2
        if self.reach:
            outline = (corners(PANEL) - PANEL_CENTER) @ self.rotation.T
            for d, depth in self.reach:
                j = int(np.flatnonzero(np.round(d))[0])
                s = float(np.sign(d[j]))
                out[..., j] += s * (edge / 2 - depth - (s * outline[:, j]).max())
        return out

    @property
    def ffc_direction(self):
        return self.rotation @ [1, 0, 0]


@dataclass
class Plan:
    fpc: dict  # first module: face name -> direction its FPC edge points to
    # Overlap the panels at the corner instead of centring them: round the
    # first module's corner (top -> A -> B), each panel reaches the cube's
    # edge toward the panel before it and tucks behind the one after it.
    pinwheel: bool = False

    @classmethod
    def default(cls):
        return cls({"top": "-y", "A": "-z", "B": "-z"})

    @property
    def faces(self):
        out = []
        order = list(FIRST)
        for i, (name, normal) in enumerate(FIRST.items()):
            n, d = np.array(normal, float), parse_axis(self.fpc[name])
            reach = ()
            if self.pinwheel:
                before, after = (np.array(FIRST[order[(i + k) % 3]], float) for k in (-1, 1))
                reach = ((before, 0.0), (after, PANEL_SIZE[2] + PINWHEEL_CLEARANCE))
            out.append(Face(name, 1, n, d, reach))
            out.append(Face(PARTNER[name], 2, TURN @ n, TURN @ d, tuple((TURN @ v, depth) for v, depth in reach)))
        return out


def part_boxes(face, edge):
    """World boxes of a face's solid parts, for the collision check."""
    boxes = [("panel", PANEL), ("board", BOARD_FOLDED)] + [(f"fpc{i}", b) for i, b in enumerate(FPC)]
    return [(f"{face.name} {part}", box_of(face.place(corners(b), edge))) for part, b in boxes]


def collisions(plan, edge, tol=0.01):
    boxes = [(f.name, label, b) for f in plan.faces for label, b in part_boxes(f, edge)]
    hits = []
    for i, (fa, la, (alo, ahi)) in enumerate(boxes):
        for fb, lb, (blo, bhi) in boxes[i + 1:]:
            if fa != fb and all(np.minimum(ahi, bhi) - np.maximum(alo, blo) > tol):
                hits.append((la, lb))
    return hits


def minimum_edge(plan, lo=60.0, hi=140.0):
    """Smallest cube edge (glass to glass) at which no two faces' parts overlap."""
    assert collisions(plan, hi) == [], "collides even at the largest edge"
    while hi - lo > 0.01:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if collisions(plan, mid) == [] else (mid, hi)
    return hi


def ffc_destinations(plan):
    """For each face of the first module, the face its FFC leaves toward."""
    by_normal = {axis_name(f.normal): f.name for f in plan.faces}
    return {f.name: by_normal[axis_name(f.ffc_direction)] for f in plan.faces if f.module == 1}


def fpc_edges(plan):
    """For each face, the cube edge its FPC edge lies on, as the pair of the
    two faces' outward normals (axis names) that meet there."""
    return {f.name: frozenset((axis_name(f.normal), axis_name(f.fpc))) for f in plan.faces}


def fpc_edge_meetings(plan):
    """Pairs of faces whose FPC edges lie on the same cube edge. The FPC edge
    has the panel's 2.81mm bottom border (and the folded FPC), so two of them
    side by side on one cube edge make the widest seam."""
    edges = list(fpc_edges(plan).items())
    return [(a, b) for i, (a, ea) in enumerate(edges) for b, eb in edges[i + 1:] if ea == eb]


# The side faces in the order the QSC faces go east (counterclockwise seen
# from above); lt7680_multi/earth_qsc480x6.h has faces 0-3 on the sides, the
# north pole 4 joined to face 0's top edge and the south pole 5 to its bottom
SIDES_EAST = ["A", "B", "D", "C"]


def earth_faces(face0="A"):
    """Cube face -> QSC face, with QSC face 0 on `face0`."""
    i = SIDES_EAST.index(face0)
    out = {f: k for k, f in enumerate(SIDES_EAST[i:] + SIDES_EAST[:i])}
    out.update(top=4, bottom=5)
    return out


EARTH_FACE = earth_faces()


def earth_turns(plan, face0="A"):
    """For each face, (QSC face, r): turn that face's image r quarter turns
    clockwise (lt7680_multi's x,n,r) so it joins its neighbours, with QSC
    face 0 on `face0`. Assumes the image's top row is shown along the
    panel's top edge (away from the FPC edge), not mirrored; if not, every
    r is off by the same amount."""
    normal = {f.name: f.normal for f in plan.faces}
    # the image's top: north on the sides; the poles' edges joined to face 0
    want = {f: np.array([0.0, 0.0, 1.0]) for f in SIDES_EAST}
    want["top"], want["bottom"] = -normal[face0], normal[face0]
    faces = earth_faces(face0)
    out = {}
    for f in plan.faces:
        up, right = f.rotation @ [0, 1, 0], f.rotation @ [1, 0, 0]
        # after r clockwise quarter turns the image's top is toward these
        tops = [up, right, -up, -right]
        r = next(i for i, t in enumerate(tops) if np.allclose(t, want[f.name]))
        out[f.name] = (faces[f.name], r)
    return out


CORNER = np.array([1.0, -1.0, 1.0]) / np.sqrt(3)  # the first module's corner


def _turn_about(axis, angle):
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * k @ k


def turning(plan):
    """'counterclockwise' or 'clockwise' (seen from outside the corner) when
    the three faces are one face turned a third of the way round the corner
    each time, so every FFC leaves toward the next face; else None."""
    fs = {f.name: f for f in plan.faces if f.module == 1}
    q = _turn_about(CORNER, 2 * np.pi / 3)
    if not all(np.allclose(q @ fs[a].rotation, fs[b].rotation) for a, b in (("top", "A"), ("A", "B"), ("B", "top"))):
        return None
    sense = {float(np.sign(np.cross(f.normal, f.ffc_direction) @ CORNER)) for f in fs.values()}
    if sense == {1.0}:
        return "counterclockwise"
    if sense == {-1.0}:
        return "clockwise"
    return None


def search():
    """Every way to turn the first module's three panels (4 x 4 x 4)."""
    axes = ["+x", "-x", "+y", "-y", "+z", "-z"]
    choices = {n: [a for a in axes if abs(parse_axis(a) @ np.array(FIRST[n], float)) < 0.5] for n in FIRST}
    rows = []
    for combo in itertools.product(*choices.values()):
        plan = Plan(dict(zip(FIRST, combo)))
        dest = ffc_destinations(plan)
        rows.append({
            "plan": ",".join(f"{n}={a}" for n, a in zip(FIRST, combo)),
            "dest": dest,
            "inside": set(dest.values()) <= set(FIRST),
            "turning": turning(plan),
            "meetings": len(fpc_edge_meetings(plan)),
            "edge": minimum_edge(plan),
        })
    return rows


def _summit_up():
    """Rotation standing the first module on its rim, its corner (the summit)
    straight up and the top face leaning toward the viewer (-y)."""
    z = CORNER
    top = np.array(FIRST["top"], float)
    y = -(top - z * (z @ top))
    y /= np.linalg.norm(y)
    return np.array([np.cross(y, z), y, z])


SUMMIT_UP = _summit_up()
