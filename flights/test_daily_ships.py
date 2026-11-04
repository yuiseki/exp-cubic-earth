"""uv run -q --no-project --with pytest python -m pytest -q test_daily_ships.py"""
import datetime as dt
import json

import daily_ships as ds


def test_day_snapshots_keep_every_hour_even_when_missing(tmp_path):
    day = "2026-11-04"
    d = tmp_path / day
    d.mkdir()
    (d / "00.json").write_text(json.dumps({"rows": [[1, 2, 3, "431000001", 70, 0]]}))
    (d / "02.json").write_text(json.dumps({"rows": [[1.5, 2.5, 3, "431000001", 70, 0]]}))
    snaps, seen = ds.day_snapshots(tmp_path, day)
    t0 = int(dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc).timestamp())
    assert sorted(int(k) for k in snaps) == [t0 + 3600 * h for h in range(24)]  # even spacing for the cube
    assert snaps[str(t0)] == [[1, 2, 3, "431000001", 70, 0]]
    assert snaps[str(t0 + 3600)] == []
    assert seen == 2


def test_day_before_is_utc():
    now = dt.datetime(2026, 11, 5, 8, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))  # 23:00 UTC on the 4th
    assert ds.day_before(now) == "2026-11-03"


def test_keep_only_ships_seen_in_two_consecutive_hours():
    a, b, c = [1, 2, 3, "A", 70, 0], [1, 2, 3, "B", 70, 0], [1, 2, 3, "C", 70, 0]
    snaps = {"0": [a, b], "3600": [a], "7200": [b, c], "10800": [c]}
    # A: hours 0 and 1, C: hours 2 and 3 -> drawn; B: hours 0 and 2 only -> the cube never shows it
    assert ds.drawable(snaps) == {"0": [a], "3600": [a], "7200": [c], "10800": [c]}
