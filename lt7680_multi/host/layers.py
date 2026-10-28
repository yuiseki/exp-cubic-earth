"""Overlay layers for the cube's scenes, drawn on an equirectangular canvas (scene_compose.py --layers).

Each layer is an alpha (0..1, H x W) and a colour; scene_compose.py lays it
over the ground and the clouds. Lines and points are drawn `supersample`
times larger and shrunk, so a line thinner than a canvas pixel still shows
as a faint line.

- rail, rivers: tile.yuiseki.net's vector tiles (railways_low and
  rivers_low, zoom 3, the whole world in 64 tiles; OpenStreetMap
  contributors, ODbL), cached in ~/tmp/cubic-tiles/.
- airports: OurAirports (public domain, "Data from OurAirports"), large
  airports bright, medium ones with scheduled service faint.
- population: Kontur Population 2023-11-01 on H3 resolution 4 (CC BY),
  each cell's people at its centre, log scaled.
"""
import math
import os
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

TILES = "https://tile.yuiseki.net/data/{layer}/{z}/{x}/{y}.pbf"
TILE_CACHE = os.path.expanduser("~/tmp/cubic-tiles")
AIRPORTS = "/sata_hdd_24tb/www/html/static/ourairports/2026-10-01/airports.parquet"
KONTUR = "/sata_hdd_24tb/hf_data/kontur-population-2023-11-01-22km/data/parquet/kontur_population_20231101_r4.parquet"


def tile_lonlat(z, tx, ty, px, py, extent):
    """Longitude and latitude of tile pixels (px, py from the tile's top left, 0..extent)."""
    n = 2 ** z
    lon = (tx + px / extent) / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (ty + py / extent) / n))))
    return lon, lat


def canvas_xy(lon, lat, w, h):
    return (lon + 180) / 360 * w, (90 - lat) / 180 * h


class Canvas:
    def __init__(self, w, h, supersample=2):
        self.w, self.h, self.s = w, h, supersample
        self.img = Image.new("L", (w * supersample, h * supersample), 0)
        self.draw = ImageDraw.Draw(self.img)

    def _xy(self, lon, lat):
        x, y = canvas_xy(np.asarray(lon, float), np.asarray(lat, float), self.w * self.s, self.h * self.s)
        return x, y

    def line(self, lon, lat, width=1):
        x, y = self._xy(lon, lat)
        jump = np.abs(np.diff(x)) > self.w * self.s / 2  # across the date line
        start = 0
        for cut in list(np.flatnonzero(jump) + 1) + [len(x)]:
            if cut - start >= 2:
                self.draw.line(list(zip(x[start:cut], y[start:cut])), fill=255, width=width)
            start = cut

    def points(self, lon, lat, radius=1):
        x, y = self._xy(lon, lat)
        r = radius * self.s / 2
        for xi, yi in zip(x, y):
            self.draw.ellipse((xi - r, yi - r, xi + r, yi + r), fill=255)

    def alpha(self):
        img = self.img if self.s == 1 else self.img.resize((self.w, self.h), Image.BOX)
        return np.asarray(img, dtype=np.float32) / 255


def density(lon, lat, people, w, h, blur=1):
    """People summed per canvas pixel, log scaled to 0..1 (1 = the most crowded pixel), softly blurred."""
    x, y = canvas_xy(lon, lat, w, h)
    xi, yi = np.clip(x.astype(int), 0, w - 1), np.clip(y.astype(int), 0, h - 1)
    grid = np.zeros((h, w), dtype=np.float64)
    np.add.at(grid, (yi, xi), people)
    for _ in range(int(blur)):  # PIL cannot blur a float image: a 3x3 box, `blur` times
        p = np.pad(grid, 1, mode="edge")
        grid = sum(p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)) / 9
    # blur the people, then take the log: the other way round the empty pixels between cell centres stay a lattice
    g = np.log1p(grid)
    return (g / g.max()).astype(np.float32) if g.max() > 0 else g.astype(np.float32)


def _tile(layer, z, x, y):
    path = os.path.join(TILE_CACHE, layer, str(z), str(x), f"{y}.pbf")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(TILES.format(layer=layer, z=z, x=x, y=y), headers={"User-Agent": "cubic-earth-scene/1.0"})
        data = urllib.request.urlopen(req, timeout=60).read()  # Python's default User-Agent gets a 403
        open(path, "wb").write(data)
    return open(path, "rb").read()


def vector_lines(layer, source_layer, w, h, z=3, width=1, supersample=2):
    import mapbox_vector_tile
    canvas = Canvas(w, h, supersample)
    for x in range(2 ** z):
        for y in range(2 ** z):
            tile = mapbox_vector_tile.decode(_tile(layer, z, x, y), default_options={"y_coord_down": True})
            src = tile.get(source_layer)
            if not src:
                continue
            for f in src["features"]:
                g = f["geometry"]
                parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
                for part in parts:
                    p = np.asarray(part, float)
                    lon, lat = tile_lonlat(z, x, y, p[:, 0], p[:, 1], src["extent"])
                    canvas.line(lon, lat, width)
    return canvas.alpha()


def airports(w, h, supersample=2):
    import duckdb
    rows = duckdb.sql(f"select type, longitude_deg, latitude_deg from '{AIRPORTS}' "
                      "where type = 'large_airport' or (type = 'medium_airport' and scheduled_service = 'yes')").fetchall()
    big = Canvas(w, h, supersample)
    small = Canvas(w, h, supersample)
    for t, lon, lat in rows:
        (big if t == "large_airport" else small).points([lon], [lat], radius=6 if t == "large_airport" else 3)
    return np.maximum(big.alpha(), small.alpha() * 0.6), len(rows)


def population(w, h):
    import duckdb
    import h3
    rows = duckdb.sql(f"select h3, population from '{KONTUR}'").fetchall()
    ll = np.array([h3.cell_to_latlng(c) for c, _ in rows])
    people = np.array([p for _, p in rows])
    return density(ll[:, 1], ll[:, 0], people, w, h, blur=3), int(people.sum())  # a cell centre every ~2 px: blur the lattice away
