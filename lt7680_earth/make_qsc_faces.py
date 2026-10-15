# make_qsc_faces.py
# 正距円筒の全球画像から、QSC (Quadrilateralized Spherical Cube) 投影で
# 立方体の側面4面 (赤道帯、経度90度おき) を切り出して RGB565 C 配列にする。
#
# QSC は球を立方体に投影するための等積図法 (Chan & O'Neill 1975, COBE 由来)。
# PROJ の +proj=qsc を pyproj 経由で逆変換に使う。
# 面の正方形は全域が球面に対応するので、円形と違いマスク不要で四隅まで地球。
#
# 実行 (pi4-d-hdmi):
#   ~/.venv-qsc/bin/python make_qsc_faces.py blue_marble_2002.jpg earth_qsc.h --lon0 139.767
import argparse
import math
from PIL import Image
from pyproj import Proj

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("--lon0", type=float, default=139.767,
                help="面1の中心経度 (deg)")
ap.add_argument("--count", type=int, default=4,
                help="生成する面の数 (自転用リングは 12 など)")
ap.add_argument("--step", type=float, default=90.0,
                help="面の中心経度の間隔 (deg)")
ap.add_argument("--name", default="EARTH_QSC", help="C配列名")
ap.add_argument("--size", type=int, default=240)
args = ap.parse_args()

img = Image.open(args.src).convert("RGB")
W, H = img.size
px = img.load()
N = args.size


def sample(lon_deg, lat_deg):
    """経緯度(deg)で正距円筒からバイリニアサンプリング。経度ラップ"""
    fx = ((lon_deg / 360.0) + 0.5) % 1.0 * W - 0.5
    fy = (0.5 - lat_deg / 180.0) * H - 0.5
    x0 = math.floor(fx)
    y0 = math.floor(fy)
    tx = fx - x0
    ty = fy - y0

    def gp(x, y):
        return px[int(x) % W, min(max(int(y), 0), H - 1)]

    c00 = gp(x0, y0)
    c10 = gp(x0 + 1, y0)
    c01 = gp(x0, y0 + 1)
    c11 = gp(x0 + 1, y0 + 1)
    out = []
    for k in range(3):
        top = c00[k] * (1 - tx) + c10[k] * tx
        bot = c01[k] * (1 - tx) + c11[k] * tx
        v = int(round(top * (1 - ty) + bot * ty))
        out.append(v)
    r, g, b = out
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def render_face(lon0):
    """中心 (0, lon0) の QSC 面を N x N で描く"""
    p = Proj(f"+proj=qsc +R=1 +lat_0=0 +lon_0={lon0}")
    # 面の半幅 L: 面の右端 (lon0+45, lat 0) の x 座標
    L, _ = p(lon0 + 45.0, 0.0)
    # ピクセル中心の投影座標グリッドを作って一括逆変換
    xs, ys = [], []
    for j in range(N):
        y = L - (j + 0.5) / N * 2 * L   # 上が北
        for i in range(N):
            x = (i + 0.5) / N * 2 * L - L
            xs.append(x)
            ys.append(y)
    lons, lats = p(xs, ys, inverse=True)
    return [sample(lo, la) for lo, la in zip(lons, lats)]


centers = [args.lon0 + args.step * k for k in range(args.count)]
faces = [render_face(c) for c in centers]

with open(args.dst, "w") as f:
    f.write("#pragma once\n#include <stdint.h>\n")
    f.write("// NASA Blue Marble 2002 -> QSC (Quadrilateralized Spherical Cube)\n")
    f.write("// side faces, centers (lat=0): " +
            ", ".join("%.3f" % (c % 360) for c in centers) + " deg lon\n")
    f.write("static const uint16_t %s[%d][%d * %d] = {\n"
            % (args.name, args.count, N, N))
    for fi, vals in enumerate(faces):
        f.write("{ // face %d: lon %.3f\n" % (fi, centers[fi] % 360))
        for i in range(0, len(vals), 12):
            f.write("  " + ",".join("0x%04X" % v for v in vals[i:i + 12]) + ",\n")
        f.write("},\n")
    f.write("};\n")

print("wrote", args.dst, "faces:", ["%.3f" % (c % 360) for c in centers])
