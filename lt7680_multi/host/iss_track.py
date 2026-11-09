# iss_track.py
# ISS の TLE (Celestrak) から SGP4 で地上軌跡を計算し、地球の面 (QSC、中心経度 lon0) の画素座標に変換して、
# XIAO の lt7680_multi に送る「#Q x y w h color」の行を出力する。面の裏側に回る区間は出さない。
#
#   uv run -q --no-project --with sgp4 --with pyproj python -I iss_track.py > cmds.txt
#
# 色は RGB565。過去 45 分は橙、未来 45 分は水色、現在位置は赤の大きな印。
# 読み込んだだけでは何も実行しない (関数は test_iss_track.py で確かめる。TLE と時刻は引数で渡す)。
import argparse
import functools
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from sgp4.api import Satrec, jday

URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"


def parse_tle(text):
    """(name, Satrec). The name line is optional; text that has no TLE lines raises ValueError."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    try:
        l1 = next(l for l in lines if l.startswith("1 "))
        l2 = next(l for l in lines if l.startswith("2 "))
    except StopIteration:
        raise ValueError(f"not a TLE: {text[:80]!r}") from None
    name = lines[0] if lines and not lines[0].startswith(("1 ", "2 ")) else ""
    return name, Satrec.twoline2rv(l1, l2)


def fetch_tle():
    return urllib.request.urlopen(URL, timeout=30).read().decode()


def load_tle(path, max_age, fetch=fetch_tle):
    """The cached TLE text if it is younger than max_age seconds, otherwise a fresh one (saved). A reply that is not a TLE
    raises ValueError and never replaces the cache."""
    if os.path.exists(path) and time.time() - os.path.getmtime(path) <= max_age:
        return open(path).read()
    data = fetch()
    parse_tle(data)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").write(data)
    return data


def gmst_rad(jd):
    # IAU 1982 の GMST (TEME → 経度の変換に十分な精度)
    t = (jd - 2451545.0) / 36525.0
    g = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((g / 240.0) % 360.0)


def latlon(sat, when):
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second + when.microsecond / 1e6)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return None
    x, y, z = r
    lon = math.degrees(math.atan2(y, x) - gmst_rad(jd + fr))
    lon = (lon + 180) % 360 - 180
    lat = math.degrees(math.atan2(z, math.hypot(x, y)))
    return lat, lon


@functools.lru_cache(maxsize=None)
def _face(lon0):
    from pyproj import Proj  # only here: scene_iss uses this module's maths and has no pyproj

    proj = Proj(f"+proj=qsc +R=1 +lat_0=0 +lon_0={lon0}")
    half, _ = proj(lon0 + 45.0, 0.0)
    c = (math.cos(math.radians(lon0)), math.sin(math.radians(lon0)), 0.0)
    return proj, half, c


def to_pixel(lat, lon, lon0, size):
    """The pixel on the face centred on lon0 (size x size), or None on the far side, past the face's edges, or on a pole face."""
    proj, half, c = _face(lon0)
    # 面の表側か: 立方体の面の判定 (面の中心方向の成分が、東西方向・南北方向の成分より大きい)
    la, lo = math.radians(lat), math.radians(lon)
    v = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    f = v[0] * c[0] + v[1] * c[1]
    east = -v[0] * c[1] + v[1] * c[0]
    if f <= 0 or f < abs(east) or f < abs(v[2]):
        return None
    x, y = proj(lon, lat)
    px = (x + half) / (2 * half) * size
    py = (half - y) / (2 * half) * size
    if not (0 <= px < size and 0 <= py < size):
        return None
    return int(px), int(py)


def commands(sat, now, minutes, step, lon0, size):
    """(lines, (lat, lon) now or None, pixel now or None). Past dots orange, future dots cyan, the current spot a red mark."""
    out = []
    for s in range(-minutes * 60, minutes * 60 + 1, step):
        ll = latlon(sat, now + timedelta(seconds=s))
        if ll is None:
            continue
        p = to_pixel(*ll, lon0, size)
        if p is None:
            continue
        col = 0xFC00 if s < 0 else 0x07FF  # 橙 / 水色
        sz = 3
        out.append(f"#Q{max(p[0] - 1, 0)} {max(p[1] - 1, 0)} {sz} {sz} {col}")
    ll = latlon(sat, now)
    p = to_pixel(*ll, lon0, size) if ll else None
    if p:
        out.append(f"#Q{max(p[0] - 7, 0)} {max(p[1] - 7, 0)} 15 15 0")
        out.append(f"#Q{max(p[0] - 5, 0)} {max(p[1] - 5, 0)} 11 11 63488")
    return out, ll, p


def status_line(now, ll, p):
    where = f"lat {ll[0]:.2f} lon {ll[1]:.2f}" if ll else "lat ? lon ?"
    return f"# now {now:%H:%M:%S}Z {where} -> {p}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lon0", type=float, default=139.767)
    ap.add_argument("--size", type=int, default=480)
    ap.add_argument("--minutes", type=int, default=45, help="前後の分")
    ap.add_argument("--step", type=int, default=20, help="点の間隔 (秒)")
    ap.add_argument("--tle", default=os.path.expanduser("~/tmp/iss.tle"), help="TLE のキャッシュ")
    ap.add_argument("--max-age", type=float, default=6 * 3600, help="キャッシュの寿命 (秒)")
    args = ap.parse_args(argv)

    name, sat = parse_tle(load_tle(args.tle, args.max_age))
    print(f"# tle: {name} / epoch {sat.epochyr:02d}{sat.epochdays:.3f}", file=sys.stderr)
    now = datetime.now(timezone.utc)
    out, ll, p = commands(sat, now, args.minutes, args.step, args.lon0, args.size)
    print(status_line(now, ll, p), file=sys.stderr)
    print("\n".join(out))
    print(f"# {len(out)} commands", file=sys.stderr)


if __name__ == "__main__":
    main()
