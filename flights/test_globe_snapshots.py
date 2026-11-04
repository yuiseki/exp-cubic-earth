"""uv run -q --no-project --with pytest python -m pytest -q test_globe_snapshots.py"""
import globe_snapshots as gs


def test_airliner_needs_an_airline_callsign_and_a_large_category():
    assert gs.is_airliner("JAL5", "A3")
    assert gs.is_airliner("ANA123  ", "A5")
    assert gs.is_airliner("DLH7YA", None)       # category not sent
    assert not gs.is_airliner("JA123A", "A3")   # registration, not airline + number
    assert not gs.is_airliner("N123AB", "A1")
    assert not gs.is_airliner("JAL5", "A1")     # small aircraft
    assert not gs.is_airliner(None, "A3")


def pt(t, lat, lon, alt=30000, track=90.0, flags=0, details=None):
    return [t, lat, lon, alt, 450.0, track, flags, 0, details]


def test_samples_carry_the_last_callsign_forward():
    trace = [
        pt(0, 35.0, 139.0, details={"flight": "JAL5    ", "category": "A3"}),
        pt(600, 36.0, 140.0),
        pt(1200, 37.0, 141.0, details={"flight": "JAL6    "}),
    ]
    got = list(gs.samples(trace, base=1000, times=[1000, 1600, 2200], tol=120))
    assert got == [(1000, 35.0, 139.0, 90.0, "JAL5", "A3"),
                   (1600, 36.0, 140.0, 90.0, "JAL5", "A3"),
                   (2200, 37.0, 141.0, 90.0, "JAL6", "A3")]


def test_samples_skip_ground_stale_and_gaps():
    trace = [
        pt(0, 35.0, 139.0, alt="ground", details={"flight": "JAL5", "category": "A3"}),
        pt(600, 36.0, 140.0, flags=1),          # stale position
        pt(1000, 37.0, 141.0),
    ]
    # 0: on the ground, 600: stale, 1800: nearest point is 800 s away
    assert list(gs.samples(trace, base=0, times=[0, 600, 1800], tol=120)) == []
    assert list(gs.samples(trace, base=0, times=[1050], tol=120)) == [(1050, 37.0, 141.0, 90.0, "JAL5", "A3")]


def test_times_of_day_every_n_minutes():
    ts = gs.times_of_day("2026-11-03", 15)
    assert len(ts) == 96 and ts[1] - ts[0] == 900
    assert ts[0] == 1793664000
