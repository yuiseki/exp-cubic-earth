import numpy as np

import geometry as g
import summit_frame as sf


def inside(box, p):
    return np.all(p >= box[0] - 1e-9) and np.all(p <= box[1] + 1e-9)


def test_edge_is_the_smallest_for_the_plan():
    assert abs(g.minimum_edge(sf.PLAN) - sf.EDGE) < 0.01


def test_two_slabs_per_seam_each_a_lip_and_a_wall_all_reaching_the_corner():
    boxes = sf.rail_boxes()
    assert len(boxes) == 15
    h = sf.EDGE / 2
    corner = np.array([h, -h, h])  # the module's outer corner (+x, -y, +z)
    for label, b in boxes:
        if label.endswith("lip"):
            assert inside(b, corner)


def test_each_slab_covers_its_panels_edge_from_front_to_back():
    fs = sf.first_module_faces()
    for a, b in [("top", "A"), ("A", "B"), ("B", "top")]:
        for f, o in [(fs[a], fs[b]), (fs[b], fs[a])]:
            i = int(np.flatnonzero(f.normal)[0])
            j = int(np.flatnonzero(o.normal)[0])
            sj = o.normal[j]
            plo, phi = sf.panel_box(f)
            panel_edge = max(sj * plo[j], sj * phi[j])
            for box, reach in zip(sf.slab(f, o), (sf.OVERLAP, sf.WALL_OVERLAP)):
                along = np.array([box[0][i], box[1][i]]) * f.normal[i]
                across = np.array([box[0][j], box[1][j]]) * sj
                assert np.isclose(across.min(), panel_edge - reach)
                assert np.isclose(across.max(), sf.EDGE / 2 + sf.LIP)
            front, wall = (np.sort(np.array([b[0][i], b[1][i]]) * f.normal[i]) for b in sf.slab(f, o))
            # the lip in front of the glass, the wall behind the panel, the slot between
            assert np.isclose(front[1], sf.EDGE / 2 + sf.LIP)
            assert np.isclose(front[0], wall[1])
            assert np.isclose(wall[0], sf.EDGE / 2 - g.PANEL_SIZE[2] - sf.SLOT_CLEARANCE - sf.BACK)


def test_slot_is_the_panel_plus_clearance():
    assert np.isclose(g.PANEL_SIZE[2] + 2 * sf.SLOT_CLEARANCE, 2.38)


def test_frame_is_one_solid_and_misses_every_part(tmp_path):
    import gmsh

    n, vol = sf.build(str(tmp_path / "frame"))
    assert n == 1 and vol > 0
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ
        frame = occ.importShapes(str(tmp_path / "frame.step"))
        parts = []
        for f in sf.PLAN.faces:
            for _, (lo, hi) in g.part_boxes(f, sf.EDGE) + [(l, g.box_of(f.place(g.corners(b), sf.EDGE))) for l, b in sf.ffc_boxes()]:
                parts.append((3, occ.addBox(*lo, *(hi - lo))))
        common, _ = occ.intersect(frame, parts, removeObject=True, removeTool=True)
        occ.synchronize()
        assert sum(occ.getMass(d, t) for d, t in common) < 1e-6
    finally:
        gmsh.finalize()


def test_a_beam_fills_the_inside_corner_behind_both_panels_of_each_seam():
    fs = sf.first_module_faces()
    back = sf.EDGE / 2 - g.PANEL_SIZE[2] - sf.SLOT_CLEARANCE
    beams = [b for label, b in sf.rail_boxes() if label.endswith("beam")]
    assert len(beams) == 3
    for (a, b), (lo, hi) in zip([("top", "A"), ("top", "B"), ("A", "B")], beams):
        for f in (fs[a], fs[b]):
            i = int(np.flatnonzero(f.normal)[0])
            span = np.sort(np.array([lo[i], hi[i]]) * f.normal[i])
            assert np.allclose(span, (back - sf.BEAM, back))


def test_nothing_but_the_lips_lies_on_the_glass():
    """Over each panel, in front of its glass, the frame reaches only
    OVERLAP in from the two edges in slots, also at the corner where the
    lips meet (the beams and walls of the other seams stop at the panel's
    back)."""
    fs = sf.first_module_faces()
    h = sf.EDGE / 2
    for f in fs.values():
        i = int(np.flatnonzero(f.normal)[0])
        lo, hi = sf.panel_box(f)
        inner = []  # the panel's corner under the summit, then a step in by more than OVERLAP on both axes
        p = np.where(g.CORNER * np.sqrt(3) > 0, hi, lo).astype(float)
        p[i] = f.normal[i] * (h + sf.LIP / 2)
        step = -np.sign(g.CORNER) * (sf.OVERLAP + 0.3)
        step[i] = 0
        assert not sf.solid_at(p + step), f.name
        for k in range(3):  # and well inside along each edge
            if k != i:
                q = p + step
                q[k] -= np.sign(g.CORNER[k]) * 20
                assert not sf.solid_at(q), (f.name, k)
        edge_in = p + step / (sf.OVERLAP + 0.3) * (sf.OVERLAP - 0.3)
        assert sf.solid_at(edge_in), f.name  # the lip itself is there


def test_the_ffc_folds_inward_before_the_beam_so_the_beam_is_whole():
    fs = sf.first_module_faces()
    for a, b in [("top", "A"), ("A", "B"), ("B", "top")]:
        lo, hi = sf.beam(fs[a], fs[b])
        cuts = [c for l, c in sf.cut_boxes() if "ffc" in l]
        for clo, chi in cuts:
            assert not np.all(np.minimum(hi, chi) - np.maximum(lo, clo) > 1e-6), (a, b)
