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
