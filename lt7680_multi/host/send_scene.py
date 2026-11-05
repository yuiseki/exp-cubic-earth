"""Write face<k>.bin files (from clouds.py) to lt7680_multi's microSD as one scene (#w).

    python send_scene.py PORT DIR SCENE [FACE ...]     (default faces: 0 1 2 3 4 5)
    python send_scene.py PORT ROOT SET [FACE ...] --tree   (ROOT/<YYYY-MM-DD>/ as SET/<YYYY-MM-DD>, for #v)

The XIAO stores them as /scenes/<SCENE>/face<f>.bin; #s<SCENE> (over USB or
ESP-NOW) then draws the scene. Needs pyserial (pi5-deck:
~/.venv-esptool/bin/python). Waits for the firmware's "k" after every 4096
bytes, as send_faces.py does.
"""
import argparse
import os
import re
import sys
import termios
import time

import serial

from send_faces import CHUNK, SIZE, wait_for


def wait_ready(port, timeout=20):
    """Send "#r" every 2 s until the shell answers "cmd r:". A XIAO just plugged in (or reset by
    opening the port, as on pi4-deck 2026-10-29) is still booting, and a #w sent then loses its
    "#" so the rest reads as a face assignment (2026-11-03). True once it answers."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        port.reset_input_buffer()
        port.write(b"#r\n")
        buf, t1 = b"", time.time()
        while time.time() - t1 < 2:
            buf += port.read(port.in_waiting or 1)
            if b"cmd r:" in buf:
                return True
        time.sleep(0.5)
    return False


def open_port(path):
    port = serial.Serial(path, 115200, timeout=5)
    try:  # do not drop DTR/RTS on close (a line change can reset the XIAO)
        attrs = termios.tcgetattr(port.fd)
        attrs[2] &= ~termios.HUPCL
        termios.tcsetattr(port.fd, termios.TCSANOW, attrs)
    except termios.error:
        pass
    if not wait_ready(port):
        raise SystemExit("the XIAO shell did not answer #r")
    return port


def send(port, scene, face, path):
    data = open(path, "rb").read()
    assert len(data) == SIZE, (path, len(data))
    port.reset_input_buffer()
    port.write(f"#w{scene},{face}\n".encode())
    wait_for(port, "w ready", 5)
    t0 = time.time()
    for i in range(0, SIZE, CHUNK):
        port.write(data[i:i + CHUNK])
        c = port.read(1)
        while c in (b"\r", b"\n"):  # the end of the "w ready" line
            c = port.read(1)
        if c != b"k":
            raise SystemExit(f"face {face}: no ack after byte {i} (got {c!r})")
    wait_for(port, f"w done {scene} {face}", 10)
    print(f"scene {scene} face {face}: {SIZE} bytes in {time.time() - t0:.1f} s")


def jobs(root, scene, faces, tree):
    """(scene name, face, file) to send. With tree, root holds one directory per dated frame
    (YYYY-MM-DD, as lst_year.py writes them) and each goes to <scene>/<date>."""
    if not tree:
        return [(scene, f, os.path.join(root, f"face{f}.bin")) for f in faces]
    dates = sorted(d for d in os.listdir(root) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and os.path.isdir(os.path.join(root, d)))
    return [(f"{scene}/{d}", f, os.path.join(root, d, f"face{f}.bin")) for d in dates for f in faces]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("dir")
    ap.add_argument("scene", help="a number (#s<k>) or a name (#v, e.g. shikisai-lst/2025-07-01)")
    ap.add_argument("faces", nargs="*", type=int, default=list(range(6)))
    ap.add_argument("--tree", action="store_true", help="dir holds dated frames; send each as <scene>/<date>")
    a = ap.parse_args()
    port = open_port(a.port)
    for scene, f, path in jobs(a.dir, a.scene, a.faces, a.tree):
        send(port, scene, f, path)


if __name__ == "__main__":
    main()
