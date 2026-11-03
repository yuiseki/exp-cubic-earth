"""uv run -q --no-project --with pytest python -m pytest -q test_collect_departures.py"""
import collect_departures as cd


def test_plan_continues_from_where_it_stopped_and_wraps_round():
    airports = ["A", "B", "C", "D", "E"]
    assert cd.plan(airports, start=3, credits=100, cost=30, reserve=0) == ["D", "E", "A"]
    assert cd.plan(airports, start=0, credits=1000, cost=30, reserve=0) == airports  # never twice in one day


def test_plan_keeps_a_reserve():
    assert cd.plan(["A", "B", "C"], start=0, credits=100, cost=30, reserve=40) == ["A", "B"]
    assert cd.plan(["A", "B", "C"], start=0, credits=50, cost=30, reserve=40) == []


def test_day_window_is_one_utc_day():
    b, e = cd.day_window("2026-11-02")
    assert b == 1793577600 and e - b == 86400


def test_next_start():
    assert cd.next_start(5, start=3, done=2) == 0
    assert cd.next_start(5, start=1, done=2) == 3
