"""The summit frame: three slotted bars that meet at a module's corner.

    uv run --no-project --with gmsh --with numpy --with numpy-stl python summit_frame.py

A rail runs along each of the three seams that meet at the first module's
corner (top/A, A/B, B/top), from the corner to the far end of the seam.
Seen across the seam it is an L of two slabs, one on each panel: each slab
has a lip over the glass and a wall behind the panel, and the panel's edge
slides into the slot between them. The two slots are square to each other,
so the panels stand at 90 degrees. Nothing but the lips holds the panels:
no tape.

The three rails are three separate straight bars, mitred where they meet
at the corner (each point goes to the seam it lies furthest along), so
each prints lying flat, a few mm high: printing is charged by volume, and
a Y joined at the corner would need a print about 80mm high. The module
turns into itself a third of the way round its corner (geometry.turning),
so the three bars are one bar, and the other module's three are the same:
one design printed six times.

All the parts here are boxes square to the cube's axes, so a rail slab is
one box, and the slots and the passages for the boards, FPCs and FFCs are
the faces' part boxes (geometry.part_boxes, grown by a clearance) cut out
of it. Writes build/summit_frame_bar<i>.step/.stl (in place, the cube's
centre at the origin), build/summit_frame_bar0_print.stl (one bar lying on
its lip's outer face, for printing) and build/summit_frame_module_<plan>.3mf
(the bars with the module's parts, standing summit up as cube.py --module).
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
    # from the far end of the seam (flush with the next module's glass) to
    # past the corner for the lip; the wall stops at the third panel's back,
    # or it would stand on that panel's glass at the corner
    front = axis_range_box({n: (back, h + LIP), (j, sj): (panel_edge - OVERLAP, h + LIP), (k, sk): (-h, h + LIP)})
    wall = axis_range_box({n: (back - BACK, back), (j, sj): (panel_edge - WALL_OVERLAP, h + LIP), (k, sk): (-h, back)})
    return front, wall


def rail_boxes(plan=PLAN, edge=EDGE):
    fs = first_module_faces(plan)
    out = []
    for a, b in itertools.combinations(fs, 2):
        for f, o in ((a, b), (b, a)):
            front, wall = slab(fs[f], fs[o], edge)
            out += [(f"{a}/{b} on {f}: lip", front), (f"{a}/{b} on {f}: wall", wall)]
    return out


# The FFC leaves CON1 toward the seam but folds inward (toward the cube's
# centre) before it, so it never reaches the walls: in the panel frame it
# runs from the board edge to FFC_TURN_X and then goes back from the panel
# FFC_DOWN mm. A box for the fold and the leg, not the exact bend.
FFC_TURN_X = 68.0
FFC_DOWN = 25.0


def ffc_boxes():
    (x0, y0, z0), (_, y1, z1) = g.FFC_STUB
    run = ((x0, y0, z0), (FFC_TURN_X, y1, z1))
    leg = ((FFC_TURN_X - 3.0, y0, z0 - FFC_DOWN), (FFC_TURN_X, y1, z1))
    return [("ffc run", run), ("ffc fold", leg)]


def cut_boxes(plan=PLAN, edge=EDGE):
    """What the frame must leave room for: every face's panel (the slots,
    grown by SLOT_CLEARANCE) and its board, FPC and FFC (grown by
    PART_CLEARANCE)."""
    out = []
    for f in plan.faces:
        for label, (lo, hi) in g.part_boxes(f, edge):
            c = SLOT_CLEARANCE if label.endswith("panel") else PART_CLEARANCE
            out.append((label, (lo - c, hi + c)))
        for label, b in ffc_boxes():
            lo, hi = g.box_of(f.place(g.corners(b), edge))
            out.append((f"{f.name} {label}", (lo - PART_CLEARANCE, hi + PART_CLEARANCE)))
    return out


def seams(plan=PLAN):
    """The three bars, in the order the module's turn round its corner takes
    one to the next (top/A, A/B, B/top): (axis the seam runs along, faces)."""
    fs = first_module_faces(plan)
    out = []
    for a, b in (("top", "A"), ("A", "B"), ("B", "top")):
        k, _ = _axis(np.cross(fs[a].normal, fs[b].normal))
        out.append((k, (a, b)))
    return out


def _inward(p):
    """How far p is from the corner along each axis, toward the cube's inside."""
    return -np.sign(g.CORNER) * np.asarray(p, float) + EDGE / 2


def owner(p):
    """The bar a point near the corner belongs to: the seam it lies
    furthest along from the corner. The mitres are the planes through the
    corner and the cube's centre where two of these distances are equal."""
    d = _inward(p)
    return max(range(3), key=lambda i: d[seams()[i][0]])


def solid_at(p, bar=None):
    """Whether point p is inside the frame (or the given bar), from the
    boxes (no CAD)."""
    p = np.asarray(p, float)
    def inb(b):
        return bool(np.all(p >= b[0]) and np.all(p <= b[1]))
    inside = any(inb(b) for _, b in rail_boxes()) and not any(inb(b) for _, b in cut_boxes())
    return inside and (bar is None or owner(p) == bar)


def build(path_stem):
    """Write each bar in place and bar 0 laid flat; return their volumes."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.option.setNumber("Mesh.Binary", 1)
        occ = gmsh.model.occ
        add = lambda b: (3, occ.addBox(*b[0], *(np.asarray(b[1]) - b[0])))
        vols = []
        for i, (k, _) in enumerate(seams()):
            gmsh.clear()
            rails = [add(b) for _, b in rail_boxes()]
            frame, _ = occ.fuse(rails[:1], rails[1:])
            frame, _ = occ.cut(frame, [add(b) for _, b in cut_boxes()])
            for j, _ in seams():  # keep where this seam's distance is the largest
                if j != k:
                    frame, _ = occ.intersect(frame, [_half_space(occ, k, j)])
            occ.synchronize()
            solids = gmsh.model.getEntities(3)
            assert len(solids) == 1, f"bar {i} is {len(solids)} pieces"
            vols.append(sum(occ.getMass(d, t) for d, t in solids))
            print(f"[summit frame] bar {i}: volume {vols[-1]:.1f} mm3")
            gmsh.write(f"{path_stem}_bar{i}.step")
            gmsh.model.mesh.generate(2)
            gmsh.write(f"{path_stem}_bar{i}.stl")
            if i == 0:
                # lay it on the outer face of the top panel's lip: turn half
                # way round its own axis (x), then down to z = 0
                occ.rotate(solids, 0, 0, 0, 1, 0, 0, np.pi)
                occ.synchronize()
                zmin = gmsh.model.getBoundingBox(-1, -1)[2]
                occ.translate(solids, 0, 0, -zmin)
                occ.synchronize()
                gmsh.model.mesh.clear()
                gmsh.model.mesh.generate(2)
                gmsh.write(f"{path_stem}_bar0_print.stl")
        return vols
    finally:
        gmsh.finalize()


def _half_space(occ, k, j, size=400.0):
    """The side of the mitre between seams along k and j where the distance
    from the corner along k is at least that along j: n . p >= 0 with
    n = s_j e_j - s_k e_k (the plane holds the corner and the centre)."""
    s = np.sign(g.CORNER)
    n = np.zeros(3)
    n[j], n[k] = s[j], -s[k]
    n /= np.linalg.norm(n)
    tag = occ.addBox(0, -size / 2, -size / 2, size, size, size)
    axis = np.cross([1.0, 0.0, 0.0], n)
    occ.rotate([(3, tag)], 0, 0, 0, *axis, np.arccos(np.clip(n[0], -1, 1)))
    return (3, tag)


def main():
    from stl import mesh

    import cube

    os.makedirs(BUILD, exist_ok=True)
    stem = os.path.join(BUILD, "summit_frame")
    build(stem)
    panel = mesh.Mesh.from_file(os.path.join(BUILD, "panel.stl")).vectors.astype(float)
    board = mesh.Mesh.from_file(os.path.join(BUILD, "board.stl")).vectors.astype(float)
    parts = [p for f in first_module_faces().values() for p in cube.face_parts(f, EDGE, panel, board, np.zeros(3))]
    for i, color in enumerate(("#F5F5F0FF", "#C8C8C0FF", "#A0A098FF")):
        parts.append((f"summit frame bar {i}", color, mesh.Mesh.from_file(f"{stem}_bar{i}.stl").vectors.astype(float)))
    parts = [(name, color, tris @ g.SUMMIT_UP.T) for name, color, tris in parts]
    floor = min(tris[..., 2].min() for _, _, tris in parts)
    parts = [(name, color, tris - [0, 0, floor]) for name, color, tris in parts]
    cube.write_3mf(os.path.join(BUILD, "summit_frame_module_topmx_Amz_Bpy.3mf"), parts)


if __name__ == "__main__":
    main()
