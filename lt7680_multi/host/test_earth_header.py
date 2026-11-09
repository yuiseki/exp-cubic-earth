"""earth_header.py: the baked earth_qsc480x6.h turned into face0-5.bin for the microSD's /earth (send_scene.py ... earth)."""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import earth_header  # noqa: E402


def header(size, faces=6, name="EARTH_QSC480X6"):
    n = size * size
    rows = []
    for f in range(faces):
        vals = ", ".join(f"0x{(f * 4096 + i) & 0xFFFF:04X}" for i in range(n))
        rows.append(f"  {{ {vals} }}")
    return f"#pragma once\n#include <stdint.h>\nstatic const uint16_t {name}[{faces}][{n}] = {{\n" + ",\n".join(rows) + "\n};\n"


def test_parses_six_faces_in_order():
    fs = earth_header.faces_from_header(header(2), 2)
    assert len(fs) == 6 and all(f.dtype == np.dtype("<u2") and f.shape == (2, 2) for f in fs)
    assert fs[3].flatten().tolist() == [3 * 4096 + i for i in range(4)]


def test_wrong_count_is_an_error():
    try:
        earth_header.faces_from_header(header(2, faces=5), 2)
    except ValueError as e:
        assert "30" in str(e) or "24" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_writes_little_endian_bins(tmp_path):
    out = tmp_path / "earth"
    earth_header.write_bins(earth_header.faces_from_header(header(2), 2), str(out))
    assert sorted(os.listdir(out)) == [f"face{k}.bin" for k in range(6)]
    raw = (out / "face1.bin").read_bytes()
    assert len(raw) == 8 and raw[:2] == bytes([0x00, 0x10])  # 0x1000 little endian


def test_command_line(tmp_path):
    h = tmp_path / "e.h"
    h.write_text(header(2))
    out = tmp_path / "o"
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "earth_header.py"), str(h), str(out), "--size", "2"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert len(os.listdir(out)) == 6
    bad = subprocess.run([sys.executable, "-I", os.path.join(HERE, "earth_header.py"), str(tmp_path / "nope.h"), str(out)],
                         capture_output=True, text=True)
    assert bad.returncode != 0
