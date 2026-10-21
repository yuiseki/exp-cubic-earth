"""The summit frame: three slotted rails joined at a module's corner.

    uv run --no-project --with gmsh --with numpy --with numpy-stl python summit_frame.py

A rail runs along each of the three seams that meet at the first module's
corner (top/A, A/B, B/top), from the corner to the far end of the seam.
Seen across the seam it is an L of two slabs, one on each panel: each slab
has a lip over the glass and a wall behind the panel, and the panel's edge
slides into the slot between them. The two slots are square to each other,
so the panels stand at 90 degrees. The three rails are one part, joined at
the corner.

All the parts here are boxes square to the cube's axes, so a rail slab is
one box, and the slots and the passages for the boards, FPCs and FFCs are
the faces' part boxes (geometry.part_boxes, grown by a clearance) cut out
of it. Writes build/summit_frame.step/.stl (module frame, the cube's
centre at the origin) and build/summit_frame_module_<plan>.3mf (the frame
with the module's parts, standing summit up as cube.py --module).
"""
import itertools
import os

import numpy as np

import geometry as g

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
PLAN = g.Plan({"top": "-x", "A": "-z", "B": "+y"})
EDGE = 81.69  # glass to glass, g.minimum_edge(PLAN)

LIP = 1.0  # in front of the glass
OVERLAP = 1.0  # how far the lip reaches over the panel, from its edge (the glass's black border is about 1.4 from it)
BACK = 1.2  # wall behind the panel
WALL_OVERLAP = 3.0  # how far the wall reaches behind the panel: the depth of the slot
SLOT_CLEARANCE = 0.1  # each side of the panel in the slot (slot 2.38 for 2.18)
PART_CLEARANCE = 0.5  # around the boards, FPCs and FFCs


def axis_range_box(ranges):
    """Box from {(axis index, sign): (lo, hi)} in signed coordinates."""
    lo, hi = np.zeros(3), np.zeros(3)
    for (i, s), (a, b) in ranges.items():
        lo[i], hi[i] = sorted((s * a, s * b))
    return lo, hi


def _axis(v):
    i = int(np.flatnonzero(np.round(v))[0])
    return i, float(np.sign(v[i]))


def first_module_faces(plan=PLAN):
    return {f.name: f for f in plan.faces if f.module == 1}


def panel_box(face, edge=EDGE):
    return g.box_of(face.place(g.corners(g.PANEL), edge))


def slab(face, other, edge=EDGE):
    """The slab of the rail on the seam between face and other that lies on
    face, as two boxes: the front one from the panel's back to in front of
    its glass, reaching OVERLAP over the panel from its edge (the lip); the
    back one, the wall behind the panel, reaching WALL_OVERLAP. Both run
    from the cube's edge (plus LIP) inward."""
    h = edge / 2
    n, (j, sj) = _axis(face.normal), _axis(other.normal)
    lo, hi = panel_box(face, edge)
    panel_edge = max(sj * lo[j], sj * hi[j])  # the panel's edge toward the seam, signed along other's normal
    seam = np.cross(face.normal, other.normal)
    k, _ = _axis(seam)
    sk = float(np.sign(g.CORNER[k]))
    back = h - g.PANEL_SIZE[2] - SLOT_CLEARANCE
    along = (-h, h + LIP)  # from the far end of the seam (flush with the next module's glass) to past the corner
    front = axis_range_box({n: (back, h + LIP), (j, sj): (panel_edge - OVERLAP, h + LIP), (k, sk): along})
    wall = axis_range_box({n: (back - BACK, back), (j, sj): (panel_edge - WALL_OVERLAP, h + LIP), (k, sk): along})
    return front, wall


def rail_boxes(plan=PLAN, edge=EDGE):
    fs = first_module_faces(plan)
    out = []
    for a, b in itertools.combinations(fs, 2):
        for f, o in ((a, b), (b, a)):
            front, wall = slab(fs[f], fs[o], edge)
            out += [(f"{a}/{b} on {f}: lip", front), (f"{a}/{b} on {f}: wall", wall)]
    return out


def cut_boxes(plan=PLAN, edge=EDGE):
    """What the frame must leave room for: every face's panel (the slots,
    grown by SLOT_CLEARANCE) and its board, FPC and FFC (grown by
    PART_CLEARANCE)."""
    out = []
    for f in plan.faces:
        for label, (lo, hi) in g.part_boxes(f, edge):
            c = SLOT_CLEARANCE if label.endswith("panel") else PART_CLEARANCE
            out.append((label, (lo - c, hi + c)))
        lo, hi = g.box_of(f.place(g.corners(g.FFC_STUB), edge))
        out.append((f"{f.name} ffc", (lo - PART_CLEARANCE, hi + PART_CLEARANCE)))
    return out


def build(path_stem):
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ
        add = lambda b: (3, occ.addBox(*b[0], *(np.asarray(b[1]) - b[0])))
        rails = [add(b) for _, b in rail_boxes()]
        frame, _ = occ.fuse(rails[:1], rails[1:])
        cuts = [add(b) for _, b in cut_boxes()]
        frame, _ = occ.cut(frame, cuts)
        occ.synchronize()
        solids = gmsh.model.getEntities(3)
        vol = sum(occ.getMass(d, t) for d, t in solids)
        print(f"[summit frame] solids {len(solids)}, volume {vol:.1f} mm3")
        gmsh.write(path_stem + ".step")
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.model.mesh.generate(2)
        gmsh.write(path_stem + ".stl")
        return len(solids), vol
    finally:
        gmsh.finalize()


def main():
    from stl import mesh

    import cube

    os.makedirs(BUILD, exist_ok=True)
    stem = os.path.join(BUILD, "summit_frame")
    build(stem)
    panel = mesh.Mesh.from_file(os.path.join(BUILD, "panel.stl")).vectors.astype(float)
    board = mesh.Mesh.from_file(os.path.join(BUILD, "board.stl")).vectors.astype(float)
    parts = [p for f in first_module_faces().values() for p in cube.face_parts(f, EDGE, panel, board, np.zeros(3))]
    parts.append(("summit frame", "#F5F5F0FF", mesh.Mesh.from_file(stem + ".stl").vectors.astype(float)))
    parts = [(name, color, tris @ g.SUMMIT_UP.T) for name, color, tris in parts]
    floor = min(tris[..., 2].min() for _, _, tris in parts)
    parts = [(name, color, tris - [0, 0, floor]) for name, color, tris in parts]
    cube.write_3mf(os.path.join(BUILD, "summit_frame_module_topmx_Amz_Bpy.3mf"), parts)


if __name__ == "__main__":
    main()
