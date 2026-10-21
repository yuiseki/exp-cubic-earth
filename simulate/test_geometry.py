import numpy as np
import pytest

import geometry as g


def test_face_frame_is_a_rotation_with_z_out_and_fpc_edge_down():
    for normal, fpc in [((0, 0, 1), (0, -1, 0)), ((0, -1, 0), (0, 0, -1)), ((1, 0, 0), (0, 1, 0))]:
        m = g.face_rotation(normal, fpc)
        assert np.allclose(m @ m.T, np.eye(3))
        assert np.isclose(np.linalg.det(m), 1)
        assert np.allclose(m @ [0, 0, 1], normal)
        assert np.allclose(m @ [0, -1, 0], fpc)


def test_fpc_direction_must_lie_in_the_face():
    with pytest.raises(ValueError):
        g.face_rotation((0, 0, 1), (0, 0, -1))


def test_second_module_is_the_first_turned_half_way_round():
    first = {"top": (0, 0, 1), "A": (0, -1, 0), "B": (1, 0, 0)}
    second = {g.PARTNER[k]: tuple(int(v) for v in g.TURN @ n) for k, n in first.items()}
    assert second == {"bottom": (0, 0, -1), "C": (-1, 0, 0), "D": (0, 1, 0)}
    assert np.isclose(np.linalg.det(g.TURN), 1)


def test_folded_board_sits_on_the_panel_back_20mm_from_the_fpc_edge():
    lo, hi = g.box_of(g.BOARD_FOLDED)
    assert np.allclose(lo[:2], (21.33, 20.0), atol=0.01)
    assert np.allclose(hi[:2], (53.33, 68.20), atol=0.01)
    assert np.isclose(hi[2], -g.PANEL_SIZE[2] - g.BOARD_GAP)


def test_fold_turns_the_step_board_into_the_measured_place():
    lo, hi = g.box_of(g.fold_board(np.array(g.BOARD_FLAT)))
    assert np.allclose(lo, g.box_of(g.BOARD_FOLDED)[0], atol=0.01)
    assert np.allclose(hi, g.box_of(g.BOARD_FOLDED)[1], atol=0.01)


def test_ffc_leaves_toward_the_panel_edge_on_the_con1_side():
    lo, hi = g.box_of(g.FFC_STUB)
    assert lo[0] == pytest.approx(53.33) and hi[0] > g.PANEL_SIZE[0]


def test_minimum_edge_is_tight():
    plan = g.Plan.default()
    edge = g.minimum_edge(plan)
    assert g.collisions(plan, edge) == []
    assert g.collisions(plan, edge - 0.05) != []


def test_eight_plans_keep_every_ffc_in_its_own_module():
    rows = g.search()
    inside = [r for r in rows if r["inside"]]
    assert len(rows) == 64 and len(inside) == 8
    for r in inside:
        assert set(r["dest"].values()) <= set(g.FIRST)


def test_four_plans_turn_one_face_round_the_corner_and_two_keep_the_ffcs_inside():
    rows = [r for r in g.search() if r["turning"]]
    assert len(rows) == 4
    inside = {r["plan"]: r["turning"] for r in rows if r["inside"]}
    assert inside == {"top=-y,A=+x,B=+z": "clockwise", "top=-x,A=-z,B=+y": "counterclockwise"}


def test_fpc_edges_meet_on_three_cube_edges_in_the_chosen_plan():
    # top=-x,A=-z,B=+y: every panel's FPC edge lies on the same cube edge as
    # its partner's in the other module, so the two bottom borders face each other
    plan = g.Plan({"top": "-x", "A": "-z", "B": "+y"})
    assert sorted(tuple(sorted(m)) for m in g.fpc_edge_meetings(plan)) == [("A", "bottom"), ("B", "D"), ("C", "top")]


def test_every_plan_gives_each_face_one_fpc_edge_on_the_cube():
    for r in g.search():
        edges = g.fpc_edges(g.Plan(dict(kv.split("=") for kv in r["plan"].split(","))))
        assert len(edges) == 6 and all(len(e) == 2 for e in edges.values())
        assert r["meetings"] == len(g.fpc_edge_meetings(g.Plan(dict(kv.split("=") for kv in r["plan"].split(",")))))


def test_earth_turns_put_north_up_on_the_sides_and_face_0_below_the_north_pole():
    # a plan where every side panel stands upright (FPC edge down) needs no turn there
    plan = g.Plan({"top": "-y", "A": "-z", "B": "-z"})
    turns = g.earth_turns(plan)
    assert turns["A"] == (0, 0) and turns["B"] == (1, 0)
    # top: FPC edge toward A (-y), so the panel's top is +y, as face 4's top
    assert turns["top"] == (4, 0)
    assert {f: q for f, (q, _) in turns.items()} == g.EARTH_FACE


def test_earth_turns_of_the_chosen_plan():
    turns = g.earth_turns(g.Plan({"top": "-x", "A": "-z", "B": "+y"}))
    assert all(0 <= r <= 3 for _, r in turns.values())


def test_earth_turns_can_start_the_sides_on_another_face():
    plan = g.Plan({"top": "-x", "A": "-z", "B": "+y"})
    turns = g.earth_turns(plan, face0="B")
    assert {f: q for f, (q, _) in turns.items()} == {"B": 0, "D": 1, "C": 2, "A": 3, "top": 4, "bottom": 5}
    # the sides keep their turns (north is up whichever face is face 0)
    default = g.earth_turns(plan)
    assert all(turns[f][1] == default[f][1] for f in "ABCD")
    # top: its FPC edge points to -x, so the panel's top is +x; face 4's top must point away from B (+x)
    assert turns["top"] == (4, 2)


def test_summit_up_stands_the_first_module_on_its_rim_with_the_corner_up():
    r = g.SUMMIT_UP
    assert np.allclose(r @ r.T, np.eye(3))
    assert np.isclose(np.linalg.det(r), 1)
    assert np.allclose(r @ g.CORNER, (0, 0, 1))
    # the top face leans toward the viewer (-y), the other two to the back
    top = r @ np.array(g.FIRST["top"], float)
    assert np.isclose(top[0], 0) and top[1] < 0
    for name in ("A", "B"):
        assert (r @ np.array(g.FIRST[name], float))[1] > 0


PINWHEEL = g.Plan({"top": "-x", "A": "-z", "B": "+y"}, pinwheel=True)


def _panel_reach(face, toward, edge):
    """How far face's panel outline reaches along the axis toward (signed)."""
    lo, hi = g.box_of(face.place(g.corners(g.PANEL), edge))
    j = int(np.flatnonzero(toward)[0])
    return max(toward[j] * lo[j], toward[j] * hi[j])


def test_pinwheel_lays_each_summit_seams_panels_one_flush_one_tucked_behind():
    edge = 80.0
    h = edge / 2
    fs = {f.name: f for f in PINWHEEL.faces}
    tucked = h - g.PANEL_SIZE[2] - g.PINWHEEL_CLEARANCE
    # round the corner top -> A -> B: each panel reaches the cube's edge
    # toward the panel before it and tucks behind the one after it
    for a, b in [("top", "A"), ("A", "B"), ("B", "top")]:
        assert np.isclose(_panel_reach(fs[a], fs[b].normal, edge), tucked)
        assert np.isclose(_panel_reach(fs[b], fs[a].normal, edge), h)


def test_pinwheel_second_module_is_the_first_turned():
    edge = 80.0
    fs = {f.name: f for f in PINWHEEL.faces}
    for a, b in g.PARTNER.items():
        la = g.box_of(fs[a].place(g.corners(g.PANEL), edge))
        lb = g.box_of(fs[b].place(g.corners(g.PANEL), edge))
        assert np.allclose(g.box_of(g.corners(la) @ g.TURN.T), lb)


def test_pinwheel_makes_the_cube_smaller():
    assert g.minimum_edge(PINWHEEL) < g.minimum_edge(g.Plan(PINWHEEL.fpc)) - 2
