"""Assemble the cube from two identical corner modules and write 3MFs.

    uv run --no-project --with numpy --with numpy-stl python cube.py
    uv run --no-project --with numpy --with numpy-stl python cube.py --fpc top=-y,A=-z,B=-z --edge 82

--search lists the 64 ways to turn the first module's three panels: where
each FFC leaves, whether all stay in the module, and the smallest edge.

--fpc gives, for the first module (top, A, B), the world direction each
panel's FPC edge points to; the second module (bottom, C, D) is the same
module turned half way round (geometry.py). Without --edge the cube is
made as small as it can be without two faces' parts overlapping.

Needs build/panel.stl and build/board.stl from step_parts.py. Writes
build/cube_<plan>.3mf (joined) and build/cube_<plan>_exploded.3mf (the
second module pulled 40mm away along the cube's diagonal).
"""
import argparse
import os
import zipfile

import numpy as np
from stl import mesh

import geometry as g

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
EXPLODE_MM = 40.0
COLORS = {
    "panel 1": "#F28C28FF",
    "panel 2": "#2AA198FF",
    "glass": "#202020FF",
    "board": "#1F5FBFFF",
    "fpc": "#E0A030FF",
    "ffc": "#E8E8E8FF",
}


def box_triangles(box):
    (x0, y0, z0), (x1, y1, z1) = box
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return v[np.array(f)]


def indexed(tris):
    flat = np.round(tris.reshape(-1, 3), 5)
    verts, inverse = np.unique(flat, axis=0, return_inverse=True)
    return verts, inverse.reshape(-1, 3)


def write_3mf(path, parts):
    materials = "".join(f'<base name="{name}" displaycolor="{color}"/>' for name, color, _ in parts)
    objects, items = [], []
    for i, (name, _, tris) in enumerate(parts):
        verts, faces = indexed(tris)
        vs = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in verts)
        ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
        oid = i + 2
        objects.append(f'<object id="{oid}" name="{name}" type="model" pid="1" pindex="{i}"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')
        items.append(f'<item objectid="{oid}"/>')
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f'<resources><basematerials id="1">{materials}</basematerials>{"".join(objects)}</resources>'
        f'<build>{"".join(items)}</build></model>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
    print(f"wrote {path}")


def face_parts(face, edge, panel, board, lift):
    def put(tris):
        return face.place(tris.reshape(-1, 3), edge).reshape(-1, 3, 3) + lift

    label = f"module {face.module} {face.name}"
    parts = [
        (f"{label}: panel", COLORS[f"panel {face.module}"], put(panel)),
        (f"{label}: board", COLORS["board"], put(g.fold_board(board.reshape(-1, 3)).reshape(-1, 3, 3))),
        (f"{label}: FFC from CON1", COLORS["ffc"], put(box_triangles(g.FFC_STUB))),
    ]
    parts += [(f"{label}: FPC {i}", COLORS["fpc"], put(box_triangles(b))) for i, b in enumerate(g.FPC)]
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fpc", default="top=-y,A=-z,B=-z")
    ap.add_argument("--edge", type=float)
    ap.add_argument("--search", action="store_true", help="list the 64 ways to turn the first module's panels")
    args = ap.parse_args()
    if args.search:
        rows = sorted(g.search(), key=lambda r: (not r["inside"], r["turning"] is None, r["edge"]))
        print("plan (FPC edge of top, A, B) | FFC of top, A, B leaves toward | FFCs stay in the module | same face round the corner | smallest edge")
        for r in rows:
            dest = ", ".join(r["dest"].values())
            print(f"{r['plan']:18s} | {dest:14s} | {'yes' if r['inside'] else 'no ':3s} | {r['turning'] or '-':16s} | {r['edge']:.2f}")
        return
    plan = g.Plan(dict(kv.split("=") for kv in args.fpc.split(",")))
    faces = plan.faces
    edge_min = g.minimum_edge(plan)
    edge = args.edge or edge_min
    print(f"plan {args.fpc}: smallest edge without overlaps {edge_min:.2f} mm (glass to glass), using {edge:.2f} mm")
    for a, b in g.collisions(plan, edge):
        print(f"  overlap: {a} / {b}")
    normals = {g.axis_name(f.normal): f for f in faces}
    for f in faces:
        to = normals[g.axis_name(f.ffc_direction)]
        print(f"  module {f.module} {f.name:6s} normal {g.axis_name(f.normal)}  FPC edge {g.axis_name(f.fpc)}  "
              f"FFC leaves toward {g.axis_name(f.ffc_direction)} = {to.name} (module {to.module})")

    panel = mesh.Mesh.from_file(os.path.join(BUILD, "panel.stl")).vectors.astype(float)
    board = mesh.Mesh.from_file(os.path.join(BUILD, "board.stl")).vectors.astype(float)
    tag = args.fpc.replace("=", "").replace(",", "_").replace("+", "p").replace("-", "m")
    diagonal = np.array([-1.0, 1.0, -1.0]) / np.sqrt(3)
    for exploded in (False, True):
        parts = []
        for f in faces:
            lift = diagonal * EXPLODE_MM if (exploded and f.module == 2) else np.zeros(3)
            parts += face_parts(f, edge, panel, board, lift)
        write_3mf(os.path.join(BUILD, f"cube_{tag}{'_exploded' if exploded else ''}.3mf"), parts)


if __name__ == "__main__":
    main()
