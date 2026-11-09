"""iss_track.py: TLE -> SGP4 -> latitude/longitude -> QSC face pixel -> '#Q' lines. Offline: the TLE is a fixture
(testdata/iss.tle, Celestrak's ISS at epoch 26300.82) and the time is passed in. testdata/iss_golden.json holds what the
script printed before it was split into functions (time frozen), so the refactor is checked against the old output.

    uv run -q --no-project --with pytest --with sgp4 --with pyproj python -m pytest -q test_iss_track.py
"""
import datetime as dt
import json
import math
import os

import pytest

import iss_track as it

HERE = os.path.dirname(os.path.abspath(__file__))
TLE = open(os.path.join(HERE, "testdata", "iss.tle")).read()
GOLDEN = json.load(open(os.path.join(HERE, "testdata", "iss_golden.json")))


def utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def test_parse_tle_reads_the_name_and_builds_the_satellite():
    name, sat = it.parse_tle(TLE)
    assert name == "ISS (ZARYA)"
    assert sat.satnum == 25544
    assert sat.epochyr == 26 and sat.epochdays == pytest.approx(300.82187419)


def test_parse_tle_works_without_the_name_line():
    body = "\n".join(TLE.splitlines()[1:])
    name, sat = it.parse_tle(body)
    assert sat.satnum == 25544 and name == ""


def test_parse_tle_refuses_text_that_is_not_a_tle():
    with pytest.raises(ValueError):
        it.parse_tle("<html>rate limited</html>")


# ---- GMST ----

def test_gmst_at_j2000_is_280_46_degrees():
    assert math.degrees(it.gmst_rad(2451545.0)) == pytest.approx(280.46061837, abs=1e-6)


def test_gmst_advances_one_sidereal_day_in_a_solar_day():
    a, b = it.gmst_rad(2460000.5), it.gmst_rad(2460001.5)
    assert math.degrees((b - a) % (2 * math.pi)) == pytest.approx(0.9856473, abs=1e-4)  # 360.9856 - 360


def test_the_same_gmst_as_scene_iss_which_keeps_its_own_copy():
    import scene_iss

    for jd in (2451545.0, 2460000.5, 2461347.25):
        assert scene_iss.gmst_rad(jd) == pytest.approx(it.gmst_rad(jd), abs=1e-12)


# ---- position ----

def test_latlon_matches_the_recorded_position():
    _, sat = it.parse_tle(TLE)
    lat, lon = it.latlon(sat, utc("2026-11-07T03:00:00"))
    assert (round(lat, 2), round(lon, 2)) == (-49.95, 111.85)  # what the old script printed for this TLE and time


def test_latlon_stays_inside_the_inclination_and_the_longitude_range():
    _, sat = it.parse_tle(TLE)
    t0 = utc("2026-11-07T00:00:00")
    for k in range(0, 24 * 60, 7):
        lat, lon = it.latlon(sat, t0 + dt.timedelta(minutes=k))
        assert abs(lat) <= 51.7  # the ISS inclination is 51.64 degrees
        assert -180 <= lon < 180


def test_latlon_returns_none_when_sgp4_fails():
    _, sat = it.parse_tle(TLE)
    assert it.latlon(sat, utc("2126-11-07T00:00:00")) is None  # a century past the epoch: the orbit has decayed in the model


# ---- pixel ----

N = 480


def test_the_face_centre_is_the_image_centre():
    for lon0 in (0.0, 90.0, 139.767, -120.0):
        x, y = it.to_pixel(0.0, lon0, lon0, N)
        assert abs(x - N // 2) <= 1 and abs(y - N // 2) <= 1


def test_north_is_up_and_east_is_right():
    x0, y0 = it.to_pixel(0.0, 0.0, 0.0, N)
    assert it.to_pixel(20.0, 0.0, 0.0, N)[1] < y0
    assert it.to_pixel(-20.0, 0.0, 0.0, N)[1] > y0
    assert it.to_pixel(0.0, 20.0, 0.0, N)[0] > x0
    assert it.to_pixel(0.0, -20.0, 0.0, N)[0] < x0


def test_a_point_behind_the_face_or_past_its_edges_is_dropped():
    assert it.to_pixel(0.0, 180.0, 0.0, N) is None  # the far side
    assert it.to_pixel(0.0, 50.0, 0.0, N) is None  # past the 45 degree edge on the equator
    assert it.to_pixel(0.0, 44.0, 0.0, N) is not None
    assert it.to_pixel(60.0, 0.0, 0.0, N) is None  # that belongs to the north-pole face
    assert it.to_pixel(-60.0, 0.0, 0.0, N) is None


def test_the_pixel_scales_with_the_image_size():
    a = it.to_pixel(10.0, 15.0, 0.0, 480)
    b = it.to_pixel(10.0, 15.0, 0.0, 240)
    assert abs(a[0] / 2 - b[0]) <= 1 and abs(a[1] / 2 - b[1]) <= 1


def test_pixels_are_always_inside_the_image():
    for lat in range(-45, 46, 5):
        for lon in range(-45, 46, 5):
            p = it.to_pixel(float(lat), float(lon), 0.0, N)
            if p is not None:
                assert 0 <= p[0] < N and 0 <= p[1] < N


# ---- the '#Q' lines ----

def test_past_is_orange_future_is_cyan_and_the_current_spot_gets_a_red_mark():
    _, sat = it.parse_tle(TLE)
    lines, ll, px = it.commands(sat, utc("2026-11-07T03:30:00"), minutes=60, step=60, lon0=-120.0, size=N)
    assert px is not None
    assert lines[-2].endswith(" 15 15 0") and lines[-1].endswith(" 11 11 63488")  # black ring, then red dot
    dots = lines[:-2]
    assert any(l.endswith(" 3 3 64512") for l in dots)  # 0xFC00 orange (the past)
    assert any(l.endswith(" 3 3 2047") for l in dots)  # 0x07FF cyan (the future)
    first_cyan = next(i for i, l in enumerate(dots) if l.endswith(" 2047"))
    assert all(l.endswith(" 64512") for l in dots[:first_cyan])  # the past comes first, the order of time


def test_no_current_mark_when_the_station_is_over_another_face():
    _, sat = it.parse_tle(TLE)
    lines, ll, px = it.commands(sat, utc("2026-11-07T03:00:00"), minutes=45, step=60, lon0=139.767, size=N)
    assert px is None and ll is not None
    assert not any(l.endswith(" 15 15 0") for l in lines)


def test_marks_never_start_left_of_or_above_the_image():
    _, sat = it.parse_tle(TLE)
    for t in ("03:30:00", "03:40:00", "04:00:00"):
        lines, _, _ = it.commands(sat, utc(f"2026-11-07T{t}"), minutes=60, step=20, lon0=-120.0, size=N)
        for l in lines:
            x, y = map(int, l[2:].split()[:2])
            assert x >= 0 and y >= 0


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: f"{c['now']}-lon0={c['args']['lon0']}-{c['args']['minutes']}min")
def test_same_output_as_the_script_before_it_was_split_into_functions(case):
    _, sat = it.parse_tle(TLE)
    a = case["args"]
    lines, ll, px = it.commands(sat, utc(case["now"]), a["minutes"], a["step"], a["lon0"], a["size"])
    assert lines == case["stdout"]
    assert it.status_line(utc(case["now"]), ll, px) == case["stderr_now"]


# ---- the TLE cache ----

def test_a_fresh_cache_is_used_without_the_network(tmp_path):
    p = tmp_path / "iss.tle"
    p.write_text(TLE)
    calls = []
    assert it.load_tle(str(p), 3600, fetch=lambda: calls.append(1) or "x") == TLE
    assert calls == []


def test_a_stale_or_missing_cache_is_fetched_and_saved_in_a_new_folder(tmp_path):
    p = tmp_path / "new" / "dir" / "iss.tle"
    assert it.load_tle(str(p), 3600, fetch=lambda: TLE) == TLE
    assert p.read_text() == TLE
    os.utime(p, (0, 0))  # 1970: older than any max age
    assert it.load_tle(str(p), 3600, fetch=lambda: TLE + "\n") == TLE + "\n"


def test_a_bad_reply_is_not_saved_over_a_good_cache(tmp_path):
    p = tmp_path / "iss.tle"
    p.write_text(TLE)
    os.utime(p, (0, 0))
    with pytest.raises(ValueError):
        it.load_tle(str(p), 3600, fetch=lambda: "<html>blocked</html>")
    assert p.read_text() == TLE  # the old TLE is kept for the next try
