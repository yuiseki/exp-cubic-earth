"""uv run -q --no-project --with pytest python -m pytest -q test_collect_ais.py"""
import collect_ais as ca


def pr(mmsi, lat, lon, sog, cog=90.0, kind="PositionReport"):
    return {"MessageType": kind, "MetaData": {"MMSI": mmsi},
            "Message": {kind: {"Latitude": lat, "Longitude": lon, "Sog": sog, "Cog": cog, "Valid": True}}}


def sd(mmsi, name, typ):
    return {"MessageType": "ShipStaticData", "MetaData": {"MMSI": mmsi},
            "Message": {"ShipStaticData": {"Name": name, "Type": typ, "Valid": True}}}


def test_position_keeps_moving_ships():
    assert ca.position(pr(431000001, 35.5, 139.8, 12.3)) == (431000001, 35.5, 139.8, 90.0)
    assert ca.position(pr(431000001, 35.5, 139.8, 8, kind="StandardClassBPositionReport"))[0] == 431000001


def test_position_drops_still_fast_unavailable_and_non_ships():
    assert ca.position(pr(431000001, 35.5, 139.8, 0.5)) is None    # moored or drifting
    assert ca.position(pr(431000001, 35.5, 139.8, 102.3)) is None  # 102.3 = speed not available
    assert ca.position(pr(431000001, 91, 181, 12)) is None         # position not available
    assert ca.position(pr(111431001, 35.5, 139.8, 120)) is None    # SAR aircraft
    assert ca.position(pr(992431001, 35.5, 139.8, 5)) is None      # aid to navigation
    assert ca.position(pr(12345, 35.5, 139.8, 5)) is None          # malformed MMSI
    assert ca.position(sd(431000001, "X", 70)) is None


def test_static_name_and_type():
    assert ca.static(sd(431000001, "HIKAWA MARU         ", 60)) == (431000001, "HIKAWA MARU", 60)
    assert ca.static(pr(431000001, 35.5, 139.8, 12)) is None


def test_window_keeps_latest_fix_and_learns_names():
    w = ca.Window()
    for m in [pr(431000001, 35.0, 139.0, 10), sd(431000001, "A", 70), pr(431000001, 35.1, 139.1, 10),
              pr(431000002, 0.0, 0.0, 0.0)]:
        w.add(m)
    assert w.ships == {431000001: (35.1, 139.1, 90.0)}
    assert w.names == {431000001: ("A", 70)}


def test_rows_use_snapshot_layout_with_known_types():
    rows = ca.rows({431000001: (35.1, 139.1, 90.0), 431000002: (1.0, 2.0, 180.0)}, {431000001: ("A", 70)})
    # [lat, lon, track, key, type, filled] like globe_snapshots.py; the key is the MMSI
    assert rows == [[35.1, 139.1, 90.0, "431000001", 70, 0], [1.0, 2.0, 180.0, "431000002", None, 0]]


def test_collect_reconnects_until_the_window_ends(monkeypatch):
    monkeypatch.setattr(ca, "log", lambda msg: None)
    calls, clock = [], [0.0]

    async def listen(key, until, w):
        calls.append(until)
        clock[0] += 100  # each connection breaks after 100 s
        raise ConnectionError("dropped")

    w = ca.Window()
    ca.collect("k", 300, w, listen, now=lambda: clock[0], tries=5)
    assert calls == [300, 300, 300]  # 0-100, 100-200, 200-300, then the window is over
    assert w.breaks == 3
