import numpy as np

import geometry as g
import summit_frame as sf


def inside(box, p):
    return np.all(p >= box[0] - 1e-9) and np.all(p <= box[1] + 1e-9)


def test_edge_is_the_smallest_for_the_plan():
    assert abs(g.minimum_edge(sf.PLAN) - sf.EDGE) < 0.01


def test_two_slabs_per_seam_each_a_lip_and_a_wall_all_reaching_the_corner():
    boxes = sf.rail_boxes()
    assert len(boxes) == 12
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


def test_each_point_near_the_corner_belongs_to_the_seam_it_runs_furthest_along():
    h = sf.EDGE / 2
    seams = sf.seams()
    assert [k for k, _ in seams] == [0, 2, 1]  # top/A along x, A/B along z, B/top along y
    assert sf.owner((h - 10, -h + 1, h - 1)) == 0
    assert sf.owner((h - 1, -h + 1, h - 10)) == 1
    assert sf.owner((h - 1, -h + 10, h - 1)) == 2


def test_the_three_bars_are_one_bar_turned_round_the_corner():
    q = g._turn_about(g.CORNER, 2 * np.pi / 3)
    fs = sf.first_module_faces()
    assert np.allclose(q @ fs["top"].normal, fs["A"].normal)
    rng = np.random.default_rng(0)
    h = sf.EDGE / 2
    pts = rng.uniform([-h, -h - 2, h - 9], [h + 2, -h + 9, h + 2], (4000, 3))  # round the top/A seam
    hits = 0
    for p in pts:
        a = sf.solid_at(p, bar=0)
        assert a == sf.solid_at(q @ p, bar=1) == sf.solid_at(q @ q @ p, bar=2)
        hits += a
    assert hits > 100


def test_bars_are_separate_solids_that_do_not_overlap_and_miss_every_part(tmp_path):
    import gmsh

    vols = sf.build(str(tmp_path / "frame"))
    assert len(vols) == 3
    assert max(vols) - min(vols) < 0.01 * max(vols)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ
        frame = [t for i in range(3) for t in occ.importShapes(str(tmp_path / f"frame_bar{i}.step"))]
        pair, _ = occ.intersect(frame[:1], frame[1:], removeObject=False, removeTool=False)
        occ.synchronize()
        assert sum(occ.getMass(d, t) for d, t in pair) < 1e-3
        occ.remove(pair, recursive=True)
        parts = []
        for f in sf.PLAN.faces:
            for _, (lo, hi) in g.part_boxes(f, sf.EDGE) + [(l, g.box_of(f.place(g.corners(b), sf.EDGE))) for l, b in sf.ffc_boxes()]:
                parts.append((3, occ.addBox(*lo, *(hi - lo))))
        common, _ = occ.intersect(frame, parts, removeObject=True, removeTool=True)
        occ.synchronize()
        assert sum(occ.getMass(d, t) for d, t in common) < 1e-6
    finally:
        gmsh.finalize()


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


def test_the_ffc_folds_inward_before_it_reaches_the_walls():
    rails = [b for _, b in sf.rail_boxes()]
    for lo, hi in [c for l, c in sf.cut_boxes() if "ffc" in l]:
        for rlo, rhi in rails:
            assert not np.all(np.minimum(hi, rhi) - np.maximum(lo, rlo) > 1e-6)


def test_a_bar_lies_flat_for_printing(tmp_path):
    from stl import mesh

    sf.build(str(tmp_path / "frame"))
    m = mesh.Mesh.from_file(str(tmp_path / "frame_bar0_print.stl"))
    size = m.max_ - m.min_
    assert np.isclose(m.min_[2], 0, atol=1e-6)
    assert size[2] < 8 and size[0] > 80  # along x, a few mm high
