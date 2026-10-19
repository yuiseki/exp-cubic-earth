"""Split the vendor STEP (panel + controller board, FPC laid flat) into
two meshes in the panel frame of docs/DIMENSIONS.md:

- build/panel.stl: the panel body and its glass, with the flat FPC cut off
  at the panel's bottom edge,
- build/board.stl: the controller board with its parts, as in the STEP
  (flat, below the panel).

The panel frame: seen from the display side with the FPC edge down,
origin at the panel's lower left corner, X right, Y up, Z toward the
viewer (Z = 0 on the glass).

    uv run --no-project --with gmsh --with numpy --with numpy-stl \
        python step_parts.py ER-TFT040-3-6011.STEP
"""
import os
import sys

import gmsh
import numpy as np
from stl import mesh

# STEP coordinates of the panel's lower left front corner (DIMENSIONS.md).
STEP_ORIGIN = np.array([-49.79, 55.57, 0.54])
PANEL_SIZE = (74.66, 76.54, 2.18)
BOARD_STEP_BOX = ((-28.46, -14.52, -2.16), (3.54, 33.68, 2.16))


def volume_box(tag):
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(3, tag)
    return np.array([x0, y0, z0]), np.array([x1, y1, z1])


def inside(lo, hi, box, tol=0.05):
    return all(lo >= np.array(box[0]) - tol) and all(hi <= np.array(box[1]) + tol)


def write_stl(tags, path):
    """Mesh the given volumes' surfaces and write them in the panel frame."""
    tris = []
    for tag in tags:
        for dim, surf in gmsh.model.getBoundary([(3, tag)], oriented=False):
            types, _, nodes = gmsh.model.mesh.getElements(2, abs(surf))
            for t, n in zip(types, nodes):
                if t != 2:
                    continue
                tris.append(n.reshape(-1, 3))
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    xyz = np.zeros((int(node_tags.max()) + 1, 3))
    xyz[node_tags.astype(int)] = coords.reshape(-1, 3)
    faces = np.concatenate(tris).astype(int)
    m = mesh.Mesh(np.zeros(len(faces), dtype=mesh.Mesh.dtype))
    m.vectors = xyz[faces] - STEP_ORIGIN
    m.save(path)
    lo, hi = m.vectors.reshape(-1, 3).min(0), m.vectors.reshape(-1, 3).max(0)
    print(f"wrote {path}: {len(faces)} triangles, X {lo[0]:.2f}..{hi[0]:.2f} Y {lo[1]:.2f}..{hi[1]:.2f} Z {lo[2]:.2f}..{hi[2]:.2f}")
    return lo, hi


def main():
    src = sys.argv[1]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")
    os.makedirs(out, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
        gmsh.model.occ.importShapes(src)
        gmsh.model.occ.synchronize()
        board, panel_body, glass = [], None, None
        for _, tag in gmsh.model.getEntities(3):
            lo, hi = volume_box(tag)
            size = hi - lo
            if inside(lo, hi, BOARD_STEP_BOX):
                board.append(tag)
            elif size[1] > 100:
                panel_body = tag
            elif size[0] > 70 and size[1] > 70:
                glass = tag
        assert panel_body and glass and board, (panel_body, glass, len(board))
        # Cut the flat FPC off the panel body at the bottom edge.
        x0, y0, z0 = STEP_ORIGIN[0] - 1, STEP_ORIGIN[1], -5
        keep = gmsh.model.occ.addBox(x0, y0, z0, 80, 80, 10)
        cut, _ = gmsh.model.occ.intersect([(3, panel_body)], [(3, keep)])
        gmsh.model.occ.synchronize()
        panel = [t for _, t in cut] + [glass]
        gmsh.model.mesh.generate(2)
        lo, hi = write_stl(panel, os.path.join(out, "panel.stl"))
        assert np.allclose(hi - lo, PANEL_SIZE, atol=0.05), hi - lo
        lo, hi = write_stl(board, os.path.join(out, "board.stl"))
        assert np.allclose((hi - lo)[:2], (32.00, 48.20), atol=0.05), hi - lo
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    main()
