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
