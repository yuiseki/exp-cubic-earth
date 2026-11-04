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
    assert got == [(1000, 35.0, 139.0, 90.0, "JAL5", "A3", False),
                   (1600, 36.0, 140.0, 90.0, "JAL5", "A3", False),
                   (2200, 37.0, 141.0, 90.0, "JAL6", "A3", False)]


def test_samples_skip_ground_stale_and_gaps():
    trace = [
        pt(0, 35.0, 139.0, alt="ground", details={"flight": "JAL5", "category": "A3"}),
        pt(600, 36.0, 140.0, flags=1),          # stale position
        pt(1000, 37.0, 141.0),
    ]
    # 0: on the ground, 600: stale, 1800: nearest point is 800 s away
    assert list(gs.samples(trace, base=0, times=[0, 600, 1800], tol=120)) == []
    assert list(gs.samples(trace, base=0, times=[1050], tol=120)) == [(1050, 37.0, 141.0, 90.0, "JAL5", "A3", False)]


def test_times_of_day_every_n_minutes():
    ts = gs.times_of_day("2026-11-03", 15)
    assert len(ts) == 96 and ts[1] - ts[0] == 900
    assert ts[0] == 1793664000


def test_ocean_gap_is_filled_along_the_great_circle():
    # Seen leaving Japan, seen again 9 h later near San Francisco: about 4,450 nm at ~495 kt.
    trace = [
        pt(0, 35.8, 141.0, details={"flight": "JAL2", "category": "A5"}),
        pt(9 * 3600, 37.6, -123.0),
    ]
    got = list(gs.samples(trace, base=0, times=[4.5 * 3600], tol=120, fill=True))
    assert len(got) == 1
    t, lat, lon, trk, fl, cat, filled = got[0]
    assert fl == "JAL2" and trk is None and filled
    assert 45 < lat < 52            # the great circle bows north over the Pacific
    assert lon > 170 or lon < -170  # near the date line, not over Kansas
    # without fill the gap stays empty
    assert list(gs.samples(trace, base=0, times=[4.5 * 3600], tol=120)) == []


def test_gap_is_not_filled_across_a_landing_or_at_implausible_speed():
    landed = [pt(0, 35.8, 141.0, details={"flight": "JAL2", "category": "A5"}),
              pt(9 * 3600, 37.6, -123.0, flags=2)]          # new leg starts here
    parked = [pt(0, 35.8, 141.0, details={"flight": "JAL2", "category": "A5"}),
              pt(9 * 3600, 35.9, 141.1)]                     # 9 h to move 7 nm
    for tr in (landed, parked):
        assert list(gs.samples(tr, base=0, times=[4.5 * 3600], tol=120, fill=True)) == []


def test_great_circle_midpoint():
    lat, lon = gs.gc_interp(0.0, 0.0, 0.0, 90.0, 0.5)
    assert abs(lat) < 1e-9 and abs(lon - 45.0) < 1e-9
