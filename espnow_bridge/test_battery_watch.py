"""battery_watch.py: reading the bridge's replies per module.

    uv run -q --no-project --with pyserial --with pytest python -m pytest -q test_battery_watch.py
"""
import battery_watch as bw

M1, M2 = "B8:F8:62:F8:DB:A0", "8C:BF:EA:8F:3F:38"
LINES = [
    "sent ok (unicast): #p",
    f"delivered ok to {M1}",
    f"delivered FAIL to {M2}",
    f"rx {M1}: ping from the cube",
]


def test_acked_is_per_module():
    assert bw.acked(LINES, M1)
    assert not bw.acked(LINES, M2)


def test_pinged_is_per_module():
    assert bw.pinged(LINES, M1)
    assert not bw.pinged(LINES, M2)


def test_mac_case_does_not_matter():
    assert bw.acked(LINES, M1.lower()) and bw.pinged(LINES, M1.lower())


def test_header_has_three_columns_per_module():
    assert bw.header([M1, M2]) == ["time", "ack_G_DBA0", "ack_p_DBA0", "ping_DBA0", "ack_G_3F38", "ack_p_3F38", "ping_3F38"]


def test_loads_cover_the_heavy_kinds_and_run_for_show_seconds():
    import random
    rng = random.Random(1)
    seen = {bw.pick_load(rng, 40)[0] for _ in range(200)}
    assert seen == {"t", "G", "v", "j"}
    kinds = dict(bw.pick_load(random.Random(s), 40) for s in range(50))
    assert kinds["t"] == "#t40" and kinds["G"] == "#G40,1,30" and kinds["j"] == "#j"
    assert kinds["v"].startswith("#vshikisai-lst,") and kinds["v"].endswith(",2026-10,3")


def test_fixed_load_keeps_the_old_behaviour():
    import random
    assert bw.pick_load(random.Random(0), 40, kinds="G") == ("G", "#G40,1,30")


def test_header_can_name_the_load():
    assert bw.header([M1], load=True)[:2] == ["time", "load"]
