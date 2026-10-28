"""The whole cube's frame: a corner joint on each of the 8 vertices and a slotted bar on each of the 12 edges.

    uv run --no-project --with gmsh --with numpy --with numpy-stl python cube_frame.py

The section is summit_bars.py's (6.88 mm square, two slots that do not
meet). Every panel is centred on its face with its glass WALL + CLEAR
inside the outer face, and the cube's outer edge is the longer panel side
plus (EDGE_AT + CLEAR) at each end: the longer side sits 0.1 mm off each
slot's bottom, the shorter one (1.88 mm less) about 1 mm. A joint is the
three edges' sections within JOINT_ARM of its vertex, as one piece; a bar is
an edge's section between the joints. Every panel, board, FPC and FFC
(grown by a clearance) is cut out, so the FPC that wraps round a panel's
edge gets its own notch in the slot.
Writes build/cube_frame_joint<i>.stl, build/cube_frame_bar<i>.stl and
build/cube_frame.3mf (with the panels).
"""
import itertools
import os

import numpy as np

import geometry as g
import summit_bars as sb
import summit_frame as sf

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
PLAN = g.Plan(sb.PLAN_FPC)
WALL, CLEAR, SLOT, EDGE_AT, SIZE, CUT = sb.WALL, sb.CLEAR, sb.SLOT, sb.EDGE_AT, sb.SIZE, sb.CUT
PART_CLEAR = sb.PART_CLEAR
JOINT_ARM = sb.JOINT_ARM
OUT_EDGE = max(g.PANEL_SIZE[:2]) + 2 * (EDGE_AT + CLEAR)
BAR_LENGTH = OUT_EDGE - 2 * JOINT_ARM


def faces():
    return PLAN.faces


def glass_edge():
    return OUT_EDGE - 2 * (WALL + CLEAR)


def panel_box(face):
    return g.box_of(face.place(g.corners(g.PANEL), glass_edge()))


def vertices():
    return [np.array(s, float) for s in itertools.product((-1, 1), repeat=3)]


def edges():
    """(axis k, signs (s_i, s_j) on the other two axes i < j)."""
    out = []
    for k in range(3):
        i, j = [a for a in range(3) if a != k]
        for si, sj in itertools.product((-1, 1), repeat=2):
            out.append((k, (i, si), (j, sj)))
    return out


def depth(p, axis, sign):
    return OUT_EDGE / 2 - sign * p[axis]


def _section(p, i, si, j, sj):
    di, dj = depth(p, i, si), depth(p, j, sj)
    return (0 <= di <= CUT and 0 <= dj <= SIZE) or (0 <= di <= SIZE and 0 <= dj <= CUT)


def cut_boxes():
    out = []
    for f in faces():
        for label, (lo, hi) in g.part_boxes(f, glass_edge()):
            c = CLEAR if label.endswith("panel") else PART_CLEAR
            out.append((label, (lo - c, hi + c)))
        for label, b in sf.ffc_boxes():
            lo, hi = g.box_of(f.place(g.corners(b), glass_edge()))
            out.append((f"{f.name} {label}", (lo - PART_CLEAR, hi + PART_CLEAR)))
    return out


def part_at(p):
    """("joint", vertex index) or ("bar", edge index) that holds point p, or None."""
    p = np.asarray(p, float)
    if any(np.all(p >= lo) and np.all(p <= hi) for _, (lo, hi) in cut_boxes()):
        return None
    for e, (k, (i, si), (j, sj)) in enumerate(edges()):
        if not _section(p, i, si, j, sj):
            continue
        a = OUT_EDGE / 2 + p[k]  # 0 at the -k end
        if a < JOINT_ARM or a > OUT_EDGE - JOINT_ARM:
            v = np.zeros(3)
            v[k], v[i], v[j] = (1 if a > OUT_EDGE / 2 else -1), si, sj
            return ("joint", next(n for n, w in enumerate(vertices()) if np.all(w == v)))
        return ("bar", e)
    return None


def _boxes(e, along):
    """The two section boxes of edge e, between `along` = (lo, hi) measured from its -k end."""
    k, (i, si), (j, sj) = edges()[e]
    h = OUT_EDGE / 2
    out = []
    for di, dj in ((CUT, SIZE), (SIZE, CUT)):
        lo, hi = np.zeros(3), np.zeros(3)
        lo[k], hi[k] = -h + along[0], -h + along[1]
        for ax, s, d in ((i, si, di), (j, sj, dj)):
            lo[ax], hi[ax] = sorted((s * h, s * (h - d)))
        out.append((lo, hi))
    return out


def build(stem):
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.option.setNumber("Mesh.Binary", 1)
        occ = gmsh.model.occ
        add = lambda b: (3, occ.addBox(*b[0], *(np.asarray(b[1]) - b[0])))
        out = {}
        jobs = [("bar", e, [(e, (JOINT_ARM, OUT_EDGE - JOINT_ARM))]) for e in range(12)]
        for n, v in enumerate(vertices()):
            arms = []
            for e, (k, (i, si), (j, sj)) in enumerate(edges()):
                if v[i] == si and v[j] == sj:
                    arms.append((e, (0, JOINT_ARM) if v[k] < 0 else (OUT_EDGE - JOINT_ARM, OUT_EDGE)))
            jobs.append(("joint", n, arms))
        for kind, n, arms in jobs:
            gmsh.clear()
            boxes = [add(b) for e, along in arms for b in _boxes(e, along)]
            solid, _ = occ.fuse(boxes[:1], boxes[1:])
            solid, _ = occ.cut(solid, [add(b) for _, b in cut_boxes()])
            occ.synchronize()
            ents = gmsh.model.getEntities(3)
            vol = sum(occ.getMass(d, t) for d, t in ents)
            out[(kind, n)] = (len(ents), vol)
            gmsh.model.mesh.generate(2)
            gmsh.write(f"{stem}_{kind}{n}.stl")
        return out
    finally:
        gmsh.finalize()


def main():
    from stl import mesh

    import cube

    os.makedirs(BUILD, exist_ok=True)
    stem = os.path.join(BUILD, "cube_frame")
    res = build(stem)
    for (kind, n), (pieces, vol) in sorted(res.items()):
        print(f"[cube frame] {kind} {n}: {vol / 1000:.2f} cm3{'' if pieces == 1 else f', {pieces} PIECES'}")
    total = sum(v for _, v in res.values())
    print(f"[cube frame] outer edge {OUT_EDGE:.2f} mm, bar {BAR_LENGTH:.2f} mm, total {total / 1000:.2f} cm3")
    panel = mesh.Mesh.from_file(os.path.join(BUILD, "panel.stl")).vectors.astype(float)
    board = mesh.Mesh.from_file(os.path.join(BUILD, "board.stl")).vectors.astype(float)
    parts = [p for f in faces() for p in cube.face_parts(f, glass_edge(), panel, board, np.zeros(3))]
    for (kind, n) in sorted(res):
        color = "#BBDDFFAA" if kind == "joint" else "#CCE4FFAA"
        parts.append((f"{kind} {n}", color, mesh.Mesh.from_file(f"{stem}_{kind}{n}.stl").vectors.astype(float)))
    lift = -min(tris[..., 2].min() for _, _, tris in parts)
    cube.write_3mf(os.path.join(BUILD, "cube_frame.3mf"), [(a, c, t + [0, 0, lift]) for a, c, t in parts])


if __name__ == "__main__":
    main()
