# iss_track.py
# ISS の TLE (Celestrak) から SGP4 で地上軌跡を計算し、地球の面 (QSC、中心経度 lon0) の画素座標に変換して、
# XIAO の lt7680_multi に送る「#Q x y w h color」の行を出力する。面の裏側に回る区間は出さない。
#
#   uv run -q --no-project --with sgp4 --with pyproj python -I iss_track.py > cmds.txt
#
# 色は RGB565。過去 45 分は橙、未来 45 分は水色、現在位置は赤の大きな印。
import argparse, math, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from sgp4.api import Satrec, jday
from pyproj import Proj

ap = argparse.ArgumentParser()
ap.add_argument("--lon0", type=float, default=139.767)
ap.add_argument("--size", type=int, default=480)
ap.add_argument("--minutes", type=int, default=45, help="前後の分")
ap.add_argument("--step", type=int, default=20, help="点の間隔 (秒)")
ap.add_argument("--tle", default=os.path.expanduser("~/tmp/iss.tle"), help="TLE のキャッシュ")
ap.add_argument("--max-age", type=float, default=6 * 3600, help="キャッシュの寿命 (秒)")
args = ap.parse_args()

URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
if not os.path.exists(args.tle) or time.time() - os.path.getmtime(args.tle) > args.max_age:
    data = urllib.request.urlopen(URL, timeout=30).read().decode()
    os.makedirs(os.path.dirname(args.tle), exist_ok=True)
    open(args.tle, "w").write(data)
lines = [l.strip() for l in open(args.tle) if l.strip()]
l1 = next(l for l in lines if l.startswith("1 "))
l2 = next(l for l in lines if l.startswith("2 "))
sat = Satrec.twoline2rv(l1, l2)
print(f"# tle: {lines[0]} / epoch {sat.epochyr:02d}{sat.epochdays:.3f}", file=sys.stderr)


def gmst_rad(jd):
    # IAU 1982 の GMST (TEME → 経度の変換に十分な精度)
    t = (jd - 2451545.0) / 36525.0
    g = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((g / 240.0) % 360.0)


def latlon(dt):
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return None
    x, y, z = r
    lon = math.degrees(math.atan2(y, x) - gmst_rad(jd + fr))
    lon = (lon + 180) % 360 - 180
    lat = math.degrees(math.atan2(z, math.hypot(x, y)))
    return lat, lon


proj = Proj(f"+proj=qsc +R=1 +lat_0=0 +lon_0={args.lon0}")
L, _ = proj(args.lon0 + 45.0, 0.0)
N = args.size
c = (math.cos(math.radians(args.lon0)), math.sin(math.radians(args.lon0)), 0.0)


def to_pixel(lat, lon):
    # 面の表側か: 立方体の面の判定 (面の中心方向の成分が、東西方向・南北方向の成分より大きい)
    la, lo = math.radians(lat), math.radians(lon)
    v = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    f = v[0] * c[0] + v[1] * c[1]
    east = -v[0] * c[1] + v[1] * c[0]
    if f <= 0 or f < abs(east) or f < abs(v[2]):
        return None
    x, y = proj(lon, lat)
    px = (x + L) / (2 * L) * N
    py = (L - y) / (2 * L) * N
    if not (0 <= px < N and 0 <= py < N):
        return None
    return int(px), int(py)


now = datetime.now(timezone.utc)
out = []
for s in range(-args.minutes * 60, args.minutes * 60 + 1, args.step):
    ll = latlon(now + timedelta(seconds=s))
    if ll is None:
        continue
    p = to_pixel(*ll)
    if p is None:
        continue
    col = 0xFC00 if s < 0 else 0x07FF  # 橙 / 水色
    sz = 3
    out.append(f"#Q{max(p[0] - 1, 0)} {max(p[1] - 1, 0)} {sz} {sz} {col}")
ll = latlon(now)
p = to_pixel(*ll) if ll else None
print(f"# now {now:%H:%M:%S}Z lat {ll[0]:.2f} lon {ll[1]:.2f} -> {p}", file=sys.stderr)
if p:
    out.append(f"#Q{max(p[0] - 7, 0)} {max(p[1] - 7, 0)} 15 15 0")
    out.append(f"#Q{max(p[0] - 5, 0)} {max(p[1] - 5, 0)} 11 11 63488")
print("\n".join(out))
print(f"# {len(out)} commands", file=sys.stderr)
