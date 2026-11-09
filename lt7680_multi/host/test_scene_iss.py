"""scene_iss.py: the ISS track drawn on the six scene faces (RGB565, 480x480). Offline: the TLE is the fixture of
test_iss_track.py and the time is passed in. testdata/scene_iss_golden.json holds the sha256 of every face the script wrote
before it was split into functions (blank source faces, time frozen), so the split is checked against the old pixels.

    uv run -q --no-project --with pytest --with numpy --with sgp4 --with pyproj python -m pytest -q test_scene_iss.py
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pytest

import iss_track
import scene_iss as si

HERE = os.path.dirname(os.path.abspath(__file__))
TLE = os.path.join(HERE, "testdata", "iss.tle")
GOLDEN = json.load(open(os.path.join(HERE, "testdata", "scene_iss_golden.json")))
N = 480


def utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def blank(value=0):
    return [np.full((N, N), value, dtype="<u2") for _ in range(6)]


def sat():
    return si.satellite(TLE, max_age=1e12)


# ---- dot ----

def test_dot_fills_a_square_of_side_two_r_plus_one():
    faces = blank()
    si.dot(faces, 2, 100, 200, 3, 0xABCD)
    assert (faces[2] == 0xABCD).sum() == 7 * 7
    assert (faces[2][197:204, 97:104] == 0xABCD).all()
    assert all((faces[f] == 0).all() for f in (0, 1, 3, 4, 5))


def test_dot_is_clipped_at_every_edge():
    faces = blank()
    si.dot(faces, 0, 0, 0, 3, 1)
    assert (faces[0] == 1).sum() == 4 * 4  # columns and rows 0..3 only
    si.dot(faces, 1, N - 1, N - 1, 3, 1)
    assert (faces[1] == 1).sum() == 4 * 4
    si.dot(faces, 3, 0, N - 1, 2, 1)
    assert (faces[3] == 1).sum() == 3 * 3


def test_dot_takes_float_positions_by_truncating():
    faces = blank()
    si.dot(faces, 0, 10.9, 20.9, 1, 5)
    assert (faces[0][19:22, 9:12] == 5).all()


# ---- the TLE and the shared maths ----

def test_satellite_reads_the_cached_tle_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(iss_track.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network used"))
    p = tmp_path / "iss.tle"
    p.write_text(open(TLE).read())
    assert si.satellite(str(p)).satnum == 25544


def test_the_maths_is_iss_tracks_not_a_second_copy():
    assert si.gmst_rad is iss_track.gmst_rad
    assert si.latlon is iss_track.latlon


def test_importing_scene_iss_does_not_need_pyproj():
    # as `python -I scene_iss.py` runs it (no pyproj in that uv environment): the import is blocked, the file is loaded by path
    code = (
        "import sys, importlib.util; sys.modules['pyproj'] = None; "  # None makes `import pyproj` raise ImportError
        f"spec = importlib.util.spec_from_file_location('scene_iss', {os.path.join(HERE, 'scene_iss.py')!r}); "
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')"
    )
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr


# ---- the drawing ----

def test_the_current_spot_is_a_red_dot_in_a_black_rim_on_an_untouched_face():
    faces = blank(0x1234)
    lat, lon, f, x, y = si.draw_track(faces, sat(), utc("2026-11-07T03:40:00"), 0, 139.767)  # minutes=0: only now
    x, y = int(x), int(y)
    px = lambda dx, dy: int(faces[f][min(max(y + dy, 0), N - 1), min(max(x + dx, 0), N - 1)])
    assert (lat, lon) == pytest.approx((38.5, -109.6), abs=0.1)
    assert px(0, 0) == si.NOW == 0xF800
    ring = [(dx, dy) for dx in range(-8, 9) for dy in range(-8, 9) if max(abs(dx), abs(dy)) in (7, 8) and 0 <= x + dx < N and 0 <= y + dy < N]
    assert ring and all(px(dx, dy) == si.RIM for dx, dy in ring)
    for g in range(6):
        if g != f:
            assert (faces[g] == 0x1234).all()


def test_past_is_orange_and_future_is_cyan():
    faces = blank()
    si.draw_track(faces, sat(), utc("2026-11-07T03:00:00"), 90, 139.767)
    all_px = np.concatenate([f.ravel() for f in faces])
    assert (all_px == si.PAST).sum() > 0 and (all_px == si.FUTURE).sum() > 0
    assert set(np.unique(all_px)) <= {0, si.PAST, si.FUTURE, si.NOW, si.RIM}


def test_a_wider_window_draws_more_of_the_track():
    a, b = blank(), blank()
    si.draw_track(a, sat(), utc("2026-11-07T03:00:00"), 20, 139.767)
    si.draw_track(b, sat(), utc("2026-11-07T03:00:00"), 90, 139.767)
    assert sum(int((f != 0).sum()) for f in b) > sum(int((f != 0).sum()) for f in a)


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: f"{c['now']}-{c['minutes']}min-lon0={c['lon0']}")
def test_same_pixels_as_the_script_before_it_was_split_into_functions(case):
    faces = blank()
    lat, lon, f, x, y = si.draw_track(faces, sat(), utc(case["now"]), case["minutes"], case["lon0"])
    assert [hashlib.sha256(face.astype("<u2").tobytes()).hexdigest() for face in faces] == case["sha256"]
    assert [int((face != 0).sum()) for face in faces] == case["nonzero"]
    assert case["stderr"].split("; wrote")[0] == f"ISS at {lat:.1f}, {lon:.1f} on face {f} ({x:.0f}, {y:.0f})"


# ---- files ----

def test_faces_round_trip_through_the_bin_files(tmp_path):
    faces = [np.arange(N * N, dtype="<u2").reshape(N, N) + k for k in range(6)]
    si.write_faces(faces, str(tmp_path / "new" / "out"))
    back = si.read_faces(str(tmp_path / "new" / "out"))
    assert len(back) == 6 and all((a == b).all() for a, b in zip(faces, back))
    assert (tmp_path / "new" / "out" / "face5.bin").stat().st_size == N * N * 2


def test_a_missing_or_short_face_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        si.read_faces(str(tmp_path))
    si.write_faces(blank(), str(tmp_path))
    (tmp_path / "face3.bin").write_bytes(b"\0" * 100)
    with pytest.raises(ValueError):
        si.read_faces(str(tmp_path))


def test_the_command_line_writes_six_faces_with_the_station_on_them(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    si.write_faces(blank(), str(src))
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "scene_iss.py"), str(src), str(out), "--minutes", "30", "--tle", TLE, "--max-age", "1e12"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ISS at" in r.stderr
    back = si.read_faces(str(out))
    assert sum(int((f != 0).sum()) for f in back) > 0
    assert all((a == 0).all() for a in si.read_faces(str(src)))  # the source is left alone
