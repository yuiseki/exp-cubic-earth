"""Check the routed board against WIRING.md (構成 3), independently of make.py.

    /usr/bin/python3 -m pytest -q test_hub3.py
"""
import os

import pcbnew
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# WIRING.md: XIAO pin -> ER-PCBA5981-1 CON1 pin, shared by all boards
SHARED = {"D9": 6, "D10": 7, "D8": 8, "D3": 9, "D1": 11, "D5": 18, "D4": 19}
XIAO_PIN = {"D0": "1", "D1": "2", "D2": "3", "D3": "4", "D4": "5", "D5": "6", "D6": "7", "D7": "8",
            "D8": "9", "D9": "10", "D10": "11", "3V3": "12", "GND": "13", "5V": "14"}
# 74HC138: A, B, C from D0, D2, D6; board b: LCM_SCS (CON1 5) on Yb, LCD_CS (CON1 16) on Y(3+b)
HC138_IN = {"D0": "1", "D2": "2", "D6": "3"}
HC138_Y = {0: "15", 1: "14", 2: "13", 3: "12", 4: "11", 5: "10", 6: "9", 7: "7"}
FFC = {0: "J1", 1: "J2", 2: "J3"}


@pytest.fixture(scope="module")
def pads():
    board = pcbnew.LoadBoard(os.path.join(HERE, "hub3.kicad_pcb"))
    out = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNumber():
                out[(fp.GetReference(), p.GetNumber())] = p.GetNetCode()
    return out, board


def same(pads, a, b):
    return pads[a] == pads[b] and pads[a] != 0


def test_shared_lines_reach_every_board(pads):
    pads, _ = pads
    for pin, con1 in SHARED.items():
        for j in FFC.values():
            assert same(pads, ("U2", XIAO_PIN[pin]), (j, str(con1))), (pin, j, con1)


def test_power(pads):
    pads, _ = pads
    for j in FFC.values():
        for con1 in ("1", "2"):
            assert same(pads, ("U2", XIAO_PIN["GND"]), (j, con1))
        for con1 in ("3", "4"):
            assert same(pads, ("U2", XIAO_PIN["5V"]), (j, con1))
    assert same(pads, ("U2", XIAO_PIN["3V3"]), ("U1", "16"))  # VCC
    assert same(pads, ("U2", XIAO_PIN["3V3"]), ("U1", "6"))  # G1
    for gnd in ("4", "5", "8"):  # G2A, G2B, GND
        assert same(pads, ("U2", XIAO_PIN["GND"]), ("U1", gnd))


def test_decoder_selects_each_board(pads):
    pads, _ = pads
    for pin, hc in HC138_IN.items():
        assert same(pads, ("U2", XIAO_PIN[pin]), ("U1", hc))
    for b, j in FFC.items():
        assert same(pads, ("U1", HC138_Y[b]), (j, "5"))
        assert same(pads, ("U1", HC138_Y[3 + b]), (j, "16"))


def test_no_other_connections(pads):
    pads, _ = pads
    for j in FFC.values():
        for con1 in ("10", "12", "13", "14", "15", "17", "20"):
            net = pads[(j, con1)]
            assert [k for k, v in pads.items() if v == net] == [(j, con1)], (j, con1)
    for y in (6, 7):
        net = pads[("U1", HC138_Y[y])]
        assert [k for k, v in pads.items() if v == net] == [("U1", HC138_Y[y])]


def test_power_tracks_are_wide(pads):
    """+5V carries all three boards' backlights. The router may neck power
    tracks down where they enter the 1.0mm-pitch FFC pads; keep that short
    (GND also has both copper pours, so only its width is checked)."""
    _, board = pads
    narrow = {"+5V": 0.0, "+3V3": 0.0, "GND": 0.0}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in narrow:
            width = pcbnew.ToMM(t.GetWidth())
            assert width >= 0.45 - 1e-6, (t.GetNetname(), width)
            if width < 0.6 - 1e-6:
                narrow[t.GetNetname()] += pcbnew.ToMM(t.GetLength())
    assert narrow["+5V"] <= 5.0 and narrow["+3V3"] <= 5.0, narrow
