"""uv run -q --no-project --with pytest python -m pytest -q test_daily_adsblol.py"""
import datetime as dt

import daily_adsblol as da


def rel(tag, *sizes):
    return {"tag_name": tag, "assets": [{"name": f"{tag}.tar.a{c}", "size": s, "browser_download_url": f"https://x/{tag}.tar.a{c}"}
                                        for c, s in zip("abcdef", sizes)]}


def test_prefers_prod_with_parts_in_order():
    rs = [rel("v2026.11.03-planes-readsb-staging-0", 2000, 900), rel("v2026.11.03-planes-readsb-prod-0", 2000, 1500),
          rel("v2026.11.03-planes-readsb-mlatonly-0", 1000), rel("v2026.11.02-planes-readsb-prod-0", 2000, 1000)]
    tag, urls = da.pick_release("2026-11-03", rs)
    assert tag == "v2026.11.03-planes-readsb-prod-0"
    assert urls == ["https://x/v2026.11.03-planes-readsb-prod-0.tar.aa", "https://x/v2026.11.03-planes-readsb-prod-0.tar.ab"]


def test_staging_when_prod_is_missing_or_much_smaller():
    st = rel("v2026.11.03-planes-readsb-staging-0", 2000, 900)
    assert da.pick_release("2026-11-03", [st])[0] == st["tag_name"]
    small = rel("v2026.11.03-planes-readsb-prod-0", 1000)
    assert da.pick_release("2026-11-03", [small, st])[0] == st["tag_name"]
    assert da.pick_release("2026-11-04", [small, st]) is None  # not published yet


def test_rate_limit_wait():
    now = 1000
    assert da.rate_wait(200, {"x-ratelimit-remaining": "59"}, now) == 0
    assert da.rate_wait(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1600"}, now) == 600
    assert da.rate_wait(429, {"retry-after": "120"}, now) == 120
    assert da.rate_wait(200, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "1300"}, now) == 300  # nearly out: back off
    assert da.rate_wait(403, {}, now) == 3600  # forbidden with no hint: treat as limited, try next run


def test_day_before_in_utc():
    assert da.day_before(dt.datetime(2026, 11, 4, 6, 30, tzinfo=dt.timezone.utc)) == "2026-11-03"
    jst = dt.timezone(dt.timedelta(hours=9))
    assert da.day_before(dt.datetime(2026, 11, 4, 8, 0, tzinfo=jst)) == "2026-11-02"  # still 11-03 in UTC
