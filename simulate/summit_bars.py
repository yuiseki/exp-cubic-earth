"""The summit bars: slotted square bars on a module's three summit seams, and the corner bracket inside.

    uv run --no-project --with gmsh --with numpy --with numpy-stl python summit_bars.py

Each summit seam (top/A, A/B, B/top) gets one straight bar, SIZE mm square,
whose outer faces are the cube's faces. Seen across the seam it has two
slots that do not meet: each panel slides into its own slot, WALL behind the
bar's outer face, and its edge stops EDGE_AT from the other face, so the two
slots leave a WEB of bar between them and the bar stays one piece. The inner
corner of the bar, beyond the walls behind both panels, is cut away.
The panels are not overlapped at the corner (no pinwheel): each panel's two
summit edges stop EDGE_AT from the outer faces, and the cube's outer edge is
the longer panel side plus EDGE_AT at each end (OUT_EDGE).

At the corner the three bars meet in mitres (each point goes to the seam it
lies furthest along) and their ends make the cube's outer vertex. Inside,
behind all three panels, a corner bracket fills the inner corner (a cube of
BRACKET mm cut down to a tetrahedron) with the bars' back walls cut out of it
(BAR_CLEAR): the three bar ends sit in its pockets and it keeps them at 90
degrees. Build order: bars into the bracket, then each panel pushed in its
own plane toward the corner, into its two slots at once.

The module turns into itself a third of the way round its corner, so the
three bars are one bar. Printed in clear resin, lying on an outer face.
Writes build/summit_bars_bar<i>.stl/.step, build/summit_bars_bracket.stl/.step,
build/summit_bars_bar0_print.stl and build/summit_bars_module.3mf.
"""
import itertools
import os

import numpy as np

import geometry as g
import summit_frame as sf

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
PLAN_FPC = {"top": "-x", "A": "-z", "B": "+y"}

T = g.PANEL_SIZE[2]
CLEAR = 0.1  # each side of the panel in its slot
SLOT = T + 2 * CLEAR
WALL = 1.0  # in front of the panel (clear resin: the panel's border shows through it)
WEB = 1.0  # between the two slots
EDGE_AT = WALL + SLOT + WEB  # each panel's edge, from the other face's outer plane
DEPTH = 2.5  # how far the panel goes into the bar
SIZE = EDGE_AT + DEPTH
BACK = 1.2  # wall behind the panel
CUT = WALL + SLOT + BACK  # the bar's inner corner beyond this depth on both sides is cut away
OUT_EDGE = max(g.PANEL_SIZE[:2]) + 2 * EDGE_AT  # the cube's outer edge
BRACKET = 16.0  # the bracket's reach from the outer faces
BRACKET_TETRA = 26.0  # cut where the three depths beyond the panels' backs add up to more than this
BAR_CLEAR = 0.1  # between the bracket's pockets and the bars
PART_CLEAR = 0.5  # around the boards, FPCs and FFCs


def plan():
    return g.Plan(PLAN_FPC, summit_inset=EDGE_AT - WALL - CLEAR)


def first_module_faces():
    return {f.name: f for f in plan().faces if f.module == 1}


def glass_edge():
    """The edge to place the panels with: their glass plane WALL + CLEAR inside the outer faces."""
    return OUT_EDGE - 2 * (WALL + CLEAR)


def panel_box(face):
    return g.box_of(face.place(g.corners(g.PANEL), glass_edge()))


def depths(p):
    """Depth of p below each first-module face's outer plane, keyed by face name."""
    return {n: OUT_EDGE / 2 - float(np.dot(f.normal, p)) for n, f in first_module_faces().items()}


def seams():
    fs = first_module_faces()
    out = []
    for a, b in (("top", "A"), ("A", "B"), ("B", "top")):
        k, _ = sf._axis(np.cross(fs[a].normal, fs[b].normal))
        out.append((k, (a, b)))
    return out


def owner(p):
    """The bar a point near the corner belongs to: the one whose seam it is furthest along."""
    d = -np.sign(g.CORNER) * np.asarray(p, float) + OUT_EDGE / 2
    return max(range(3), key=lambda i: d[seams()[i][0]])


def _depth_box(ranges):
    """World box from {face name: (depth lo, depth hi)}; faces not given span the whole cube."""
    fs = first_module_faces()
    h = OUT_EDGE / 2
    lo, hi = np.full(3, -h), np.full(3, h)
    for name, (d0, d1) in ranges.items():
        i, s = sf._axis(fs[name].normal)
        a, b = sorted((s * (h - d0), s * (h - d1)))
        lo[i], hi[i] = a, b
    return lo, hi


def bar_boxes():
    """Per seam, the two boxes whose union is the bar before the slots and mitres."""
    out = []
    for _, (a, b) in seams():
        out.append([_depth_box({a: (0, CUT), b: (0, SIZE)}), _depth_box({a: (0, SIZE), b: (0, CUT)})])
    return out


def cut_boxes():
    """Panels grown by CLEAR (the slots), boards, FPCs and FFCs grown by PART_CLEAR."""
    out = []
    for f in plan().faces:
        for label, (lo, hi) in g.part_boxes(f, glass_edge()):
            c = CLEAR if label.endswith("panel") else PART_CLEAR
            out.append((label, (lo - c, hi + c)))
        for label, b in sf.ffc_boxes():
            lo, hi = g.box_of(f.place(g.corners(b), glass_edge()))
            out.append((f"{f.name} {label}", (lo - PART_CLEAR, hi + PART_CLEAR)))
    return out


def _in(p, box, grow=0.0):
    return bool(np.all(p >= box[0] - grow) and np.all(p <= box[1] + grow))


def solid_at(p, bar=None):
    p = np.asarray(p, float)
    if any(_in(p, b) for _, b in cut_boxes()):
        return False
    for i, boxes in enumerate(bar_boxes()):
        if any(_in(p, b) for b in boxes) and owner(p) == i and (bar is None or bar == i):
            return True
    return False


def bracket_region():
    behind = WALL + SLOT
    return _depth_box({n: (behind, BRACKET) for n in first_module_faces()})


def bracket_at(p):
    p = np.asarray(p, float)
    if not _in(p, bracket_region()):
        return False
    d = depths(p)
    if sum(v - (WALL + SLOT) for v in d.values()) > BRACKET_TETRA:
        return False
    if any(_in(p, b, BAR_CLEAR) for boxes in bar_boxes() for b in boxes):
        return False
    return not any(_in(p, b) for _, b in cut_boxes())


def build(stem):
    """Write the three bars and the bracket (in place) and bar 0 laid flat; return the volumes."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.option.setNumber("Mesh.Binary", 1)
        occ = gmsh.model.occ
        add = lambda b, grow=0.0: (3, occ.addBox(*(np.asarray(b[0]) - grow), *(np.asarray(b[1]) - b[0] + 2 * grow)))
        vols = {}
        for i, (k, _) in enumerate(seams()):
            gmsh.clear()
            boxes = [add(b) for b in bar_boxes()[i]]
            bar, _ = occ.fuse(boxes[:1], boxes[1:])
            bar, _ = occ.cut(bar, [add(b) for _, b in cut_boxes()])
            for j, _ in seams():
                if j != k:
                    bar, _ = occ.intersect(bar, [_half_space(occ, k, j)])
            occ.synchronize()
            solids = gmsh.model.getEntities(3)
            assert len(solids) == 1, f"bar {i} is {len(solids)} pieces"
            vols[f"bar{i}"] = sum(occ.getMass(d, t) for d, t in solids)
            gmsh.write(f"{stem}_bar{i}.step")
            gmsh.model.mesh.generate(2)
            gmsh.write(f"{stem}_bar{i}.stl")
            if i == 0:
                _lay_flat(gmsh, occ, solids, f"{stem}_bar0_print.stl")
        gmsh.clear()
        lo, hi = bracket_region()
        br = add((lo, hi))
        corner = np.sign(g.CORNER) * OUT_EDGE / 2
        # the tetrahedron: the depths beyond the panels' backs add up to at most BRACKET_TETRA
        br, _ = occ.intersect([br], [_tetra_half(occ, corner, WALL + SLOT, BRACKET_TETRA)])
        bars = [add(b, BAR_CLEAR) for boxes in bar_boxes() for b in boxes]
        br, _ = occ.cut(br, bars + [add(b) for _, b in cut_boxes()])
        occ.synchronize()
        solids = gmsh.model.getEntities(3)
        assert len(solids) == 1, f"bracket is {len(solids)} pieces"
        vols["bracket"] = sum(occ.getMass(d, t) for d, t in solids)
        gmsh.write(f"{stem}_bracket.step")
        gmsh.model.mesh.generate(2)
        gmsh.write(f"{stem}_bracket.stl")
        return vols
    finally:
        gmsh.finalize()


def _lay_flat(gmsh, occ, solids, path):
    """Bar 0 (top/A, along x) lying on the top's outer face: turn half way round x, then down to z = 0."""
    occ.rotate(solids, 0, 0, 0, 1, 0, 0, np.pi)
    occ.synchronize()
    zmin = gmsh.model.getBoundingBox(-1, -1)[2]
    occ.translate(solids, 0, 0, -zmin)
    occ.synchronize()
    gmsh.model.mesh.clear()
    gmsh.model.mesh.generate(2)
    gmsh.write(path)


def _half_space(occ, k, j, size=400.0):
    s = np.sign(g.CORNER)
    n = np.zeros(3)
    n[j], n[k] = s[j], -s[k]
    n /= np.linalg.norm(n)
    tag = occ.addBox(0, -size / 2, -size / 2, size, size, size)
    axis = np.cross([1.0, 0.0, 0.0], n)
    occ.rotate([(3, tag)], 0, 0, 0, *axis, np.arccos(np.clip(n[0], -1, 1)))
    return (3, tag)


def _tetra_half(occ, corner, behind, total, size=400.0):
    """Half-space where the depths from the three outer faces, each less `behind`, add up to at most `total`."""
    inward = -np.sign(corner)
    n = inward / np.linalg.norm(inward)  # depth sum grows along n
    # plane: sum of depths = 3 * behind + total; a point at depth D on all three has n . (p - corner) = D * sqrt(3)
    p0 = corner + inward * (behind + total / 3)
    tag = occ.addBox(-size, -size / 2, -size / 2, size, size, size)  # x <= 0 half
    axis = np.cross([1.0, 0.0, 0.0], n)
    occ.rotate([(3, tag)], 0, 0, 0, *axis, np.arccos(np.clip(n[0], -1, 1)))
    occ.translate([(3, tag)], *p0)
    return (3, tag)


def main():
    from stl import mesh

    import cube

    os.makedirs(BUILD, exist_ok=True)
    stem = os.path.join(BUILD, "summit_bars")
    vols = build(stem)
    for k, v in vols.items():
        print(f"[summit bars] {k}: {v / 1000:.2f} cm3")
    panel = mesh.Mesh.from_file(os.path.join(BUILD, "panel.stl")).vectors.astype(float)
    board = mesh.Mesh.from_file(os.path.join(BUILD, "board.stl")).vectors.astype(float)
    parts = [p for f in first_module_faces().values() for p in cube.face_parts(f, glass_edge(), panel, board, np.zeros(3))]
    for i, color in enumerate(("#DDEEFF99", "#CCE4FF99", "#BBDDFF99")):
        parts.append((f"summit bar {i}", color, mesh.Mesh.from_file(f"{stem}_bar{i}.stl").vectors.astype(float)))
    parts.append(("corner bracket", "#FFAA44FF", mesh.Mesh.from_file(f"{stem}_bracket.stl").vectors.astype(float)))
    parts = [(name, color, tris @ g.SUMMIT_UP.T) for name, color, tris in parts]
    floor = min(tris[..., 2].min() for _, _, tris in parts)
    parts = [(name, color, tris - [0, 0, floor]) for name, color, tris in parts]
    cube.write_3mf(os.path.join(BUILD, "summit_bars_module.3mf"), parts)


if __name__ == "__main__":
    main()
