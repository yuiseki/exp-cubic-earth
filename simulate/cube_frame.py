"""The whole cube's frame: a corner joint on each of the 8 vertices and a slotted bar on each of the 12 edges.

    uv run --no-project --with gmsh --with numpy --with numpy-stl python cube_frame.py

The section is summit_bars.py's (6.88 mm square, two slots that do not
meet). Every panel is centred on its face with its glass WALL + CLEAR
inside the outer face, and the cube's outer edge is the longer panel side
plus (EDGE_AT + CLEAR) at each end: the longer side sits 0.1 mm off each
slot's bottom, the shorter one (1.88 mm less) about 1 mm. A joint is the
three edges' sections within JOINT_ARM of its vertex, as one piece; a bar is
an edge's section between the joints. The slots are cut to their full
depth whatever the panel's size, so the 12 bars are one shape and the 8
joints another. The panels and the boards (grown
by a clearance) are cut out; the FPC and the FFC are flexible cables and
are left out of the CAD.
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
        # only the rigid parts: the FPC and the FFC are flexible cables, not shapes for the frame to make room for
        for label, (lo, hi) in g.part_boxes(f, glass_edge()):
            if label.endswith("panel"):
                out.append((label, (lo - CLEAR, hi + CLEAR)))
            elif label.endswith("board"):
                out.append((label, (lo - PART_CLEAR, hi + PART_CLEAR)))
    return out


def slot_boxes():
    """Every edge's two slots, cut to their full depth whatever the panel's size, so all bars are the same:
    on face (i, si) the slot is WALL..WALL + SLOT below it, from EDGE_AT below the other face inward."""
    h = OUT_EDGE / 2
    out = []
    for k, (i, si), (j, sj) in edges():
        for (a, sa), (b, sb_) in (((i, si), (j, sj)), ((j, sj), (i, si))):
            lo, hi = np.full(3, -(h - EDGE_AT)), np.full(3, h - EDGE_AT)  # along the edge: as far as a panel's corner can reach
            lo[a], hi[a] = sorted((sa * (h - WALL), sa * (h - WALL - SLOT)))
            lo[b], hi[b] = sorted((sb_ * (h - EDGE_AT), sb_ * (h - SIZE - 1.0)))
            out.append((f"slot {a}{sa:+.0f}/{b}{sb_:+.0f}", (lo, hi)))
    return out


def part_at(p):
    """("joint", vertex index) or ("bar", edge index) that holds point p, or None."""
    p = np.asarray(p, float)
    if any(np.all(p >= lo) and np.all(p <= hi) for _, (lo, hi) in cut_boxes() + slot_boxes()):
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
            solid, _ = occ.cut(solid, [add(b) for _, b in cut_boxes() + slot_boxes()])
            occ.synchronize()
            ents = gmsh.model.getEntities(3)
            vol = sum(occ.getMass(d, t) for d, t in ents)
            out[(kind, n)] = (len(ents), vol)
            gmsh.model.mesh.generate(2)
            gmsh.write(f"{stem}_{kind}{n}.stl")
        return out
    finally:
        gmsh.finalize()


def face_name(axis, sign):
    v = np.zeros(3)
    v[axis] = sign
    return next(f.name for f in faces() if np.allclose(f.normal, v))


def lay_flat(tris, along, down):
    """Turn so world axis `along` (index) runs along x and the outward normal `down` (vector) points to -z; floor at 0."""
    x = np.zeros(3)
    x[along] = 1.0
    zdown = np.asarray(down, float)
    z = -zdown
    y = np.cross(z, x)
    R = np.array([x, y, z])  # rows: new axes in world coordinates
    out = tris @ R.T
    return out - out.reshape(-1, 3).min(0)


def write_print_parts(stem, out_dir):
    """One STL per part, lying on an outer face: joint<n> and bar_<faces>.stl. Returns [(file, size)]."""
    from stl import mesh

    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for e, (k, (i, si), (j, sj)) in enumerate(edges()):
        tris = mesh.Mesh.from_file(f"{stem}_bar{e}.stl").vectors.astype(float)
        down = np.zeros(3)
        down[i] = si
        flat = lay_flat(tris, k, down)
        name = f"bar{e:02d}_{face_name(i, si)}-{face_name(j, sj)}.stl"
        rows.append((name, flat))
    for n, v in enumerate(vertices()):
        tris = mesh.Mesh.from_file(f"{stem}_joint{n}.stl").vectors.astype(float)
        flat = lay_flat(tris, 0, (0, 0, v[2]))
        rows.append((f"joint{n}.stl", flat))
    out = []
    for name, flat in rows:
        m = mesh.Mesh(np.zeros(len(flat), dtype=mesh.Mesh.dtype))
        m.vectors = flat
        m.save(os.path.join(out_dir, name))
        out.append((name, flat.reshape(-1, 3).max(0)))
    return out


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
    parts = [p for f in faces() for p in cube.face_parts(f, glass_edge(), panel, board, np.zeros(3)) if "FPC" not in p[0]]
    for (kind, n) in sorted(res):
        color = "#BBDDFFAA" if kind == "joint" else "#CCE4FFAA"
        parts.append((f"{kind} {n}", color, mesh.Mesh.from_file(f"{stem}_{kind}{n}.stl").vectors.astype(float)))
    for name, size in write_print_parts(stem, os.path.join(BUILD, "cube_frame_print")):
        print(f"[cube frame] print/{name}: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")
    lift = -min(tris[..., 2].min() for _, _, tris in parts)
    cube.write_3mf(os.path.join(BUILD, "cube_frame.3mf"), [(a, c, t + [0, 0, lift]) for a, c, t in parts])


if __name__ == "__main__":
    main()
