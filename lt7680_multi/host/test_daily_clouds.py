"""uv run -q --no-project --with pytest --with numpy --with pillow --with pyproj python -m pytest -q test_daily_clouds.py"""
import datetime as dt

import daily_clouds as dc


def test_wanted_days_are_the_last_complete_ones_newest_first():
    now = dt.datetime(2026, 11, 5, 5, 20, tzinfo=dt.timezone.utc)
    assert dc.wanted_days(now, 3) == ["2026-11-04", "2026-11-03", "2026-11-02"]


def test_a_day_is_wanted_only_hours_after_it_ends():
    early = dt.datetime(2026, 11, 5, 3, 0, tzinfo=dt.timezone.utc)  # GIBS is still adding 11-04's last swaths
    assert dc.wanted_days(early, 2) == ["2026-11-03", "2026-11-02"]


def test_missing_skips_days_that_are_done(tmp_path):
    (tmp_path / "2026-11-03").mkdir()
    (tmp_path / "2026-11-03" / "faces.png").write_bytes(b"x")
    (tmp_path / "2026-11-02").mkdir()  # left half-made: not done
    assert dc.missing(tmp_path, ["2026-11-04", "2026-11-03", "2026-11-02"]) == ["2026-11-04", "2026-11-02"]


def test_make_day_publishes_only_a_finished_directory(tmp_path):
    def build(day, out):
        out.mkdir(parents=True, exist_ok=True)
        for k in range(6):
            (out / f"face{k}.bin").write_bytes(b"f")
        (out / "faces.png").write_bytes(b"p")

    dc.make_day(tmp_path, "2026-11-04", build)
    assert sorted(p.name for p in (tmp_path / "2026-11-04").iterdir())[-1] == "faces.png"
    assert not any(p.name.startswith(".") for p in tmp_path.iterdir())
    assert (tmp_path / "latest.txt").read_text() == "2026-11-04\n"


def test_make_day_leaves_nothing_public_when_the_build_fails(tmp_path):
    def build(day, out):
        out.mkdir(parents=True, exist_ok=True)
        raise RuntimeError("GIBS down")

    try:
        dc.make_day(tmp_path, "2026-11-04", build)
    except RuntimeError:
        pass
    assert not (tmp_path / "2026-11-04").exists()
    assert not (tmp_path / "latest.txt").exists()
    assert (tmp_path / ".2026-11-04.tmp").exists()  # kept for the next try


def test_make_day_sets_a_half_made_day_aside(tmp_path):
    (tmp_path / "2026-11-04").mkdir()
    (tmp_path / "2026-11-04" / "face0.bin").write_bytes(b"old")

    def build(day, out):
        out.mkdir(parents=True, exist_ok=True)
        (out / "faces.png").write_bytes(b"p")

    dc.make_day(tmp_path, "2026-11-04", build)
    assert (tmp_path / "2026-11-04" / "faces.png").exists()
    aside = [p for p in tmp_path.iterdir() if p.name.startswith(".2026-11-04.old-")]
    assert len(aside) == 1 and (aside[0] / "face0.bin").read_bytes() == b"old"


def test_latest_never_goes_back_in_time(tmp_path):
    def build(day, out):
        out.mkdir(parents=True, exist_ok=True)
        (out / "faces.png").write_bytes(b"p")

    dc.make_day(tmp_path, "2026-11-04", build)
    dc.make_day(tmp_path, "2026-11-02", build)  # a backfilled older day
    assert (tmp_path / "latest.txt").read_text() == "2026-11-04\n"
