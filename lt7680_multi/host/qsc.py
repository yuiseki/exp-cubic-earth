"""QSC forward projection onto the six faces of earth_qsc480x6.h, written to
be ported line by line to C (qsc.h). Faces 0-3 are the sides centred on
lon0 + 90k, 4 the north pole and 5 the south pole, each drawn N x N with
north up on the sides and the poles joined to face 0 (make_qsc_faces.py).
The equations are the quadrilateralized spherical cube of Calabretta &
Greisen 2002 (FITS paper II, section 5.6.2)."""
import math


def face_frames(lon0):
    """Per face: (centre n, right x, up y) as unit vectors, x cross y = n."""
    out = []
    for k in range(4):
        l = math.radians(lon0 + 90 * k)
        c, s = math.cos(l), math.sin(l)
        out.append(((c, s, 0.0), (-s, c, 0.0), (0.0, 0.0, 1.0)))
    l = math.radians(lon0)
    c, s = math.cos(l), math.sin(l)
    out.append(((0.0, 0.0, 1.0), (-s, c, 0.0), (-c, -s, 0.0)))  # north: lon0's meridian points down
    out.append(((0.0, 0.0, -1.0), (-s, c, 0.0), (c, s, 0.0)))   # south: lon0's meridian points up
    return out


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _edge(zeta, w):
    """Half-width units (-1..1) along the dominant axis, and its partner."""
    a = math.sqrt(max(0.0, 1 - zeta) / (1 - 1 / math.sqrt(2 + w * w)))  # zeta may round past 1
    b = a / 15 * (math.degrees(math.atan(w)) - math.degrees(math.asin(w / math.sqrt(2 * (1 + w * w)))))
    return a, b


def to_face_pixel(lat, lon, lon0, n):
    la, lo = math.radians(lat), math.radians(lon)
    v = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    frames = face_frames(lon0)
    f = max(range(6), key=lambda k: _dot(v, frames[k][0]))
    nrm, ex, ey = frames[f]
    zeta, xi, eta = _dot(v, nrm), _dot(v, ex), _dot(v, ey)
    if abs(xi) >= abs(eta):
        a, b = _edge(zeta, eta / xi if xi else 0.0)
        s = 1.0 if xi > 0 else -1.0
        x, y = s * a, s * b
    else:
        a, b = _edge(zeta, xi / eta)
        s = 1.0 if eta > 0 else -1.0
        y, x = s * a, s * b
    return f, (x + 1) / 2 * n, (1 - y) / 2 * n
