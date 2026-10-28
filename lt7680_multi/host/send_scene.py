"""Write face<k>.bin files (from clouds.py) to lt7680_multi's microSD as one scene (#w).

    python send_scene.py PORT DIR SCENE [FACE ...]     (default faces: 0 1 2 3 4 5)

The XIAO stores them as /scenes/<SCENE>/face<f>.bin; #s<SCENE> (over USB or
ESP-NOW) then draws the scene. Needs pyserial (pi5-deck:
~/.venv-esptool/bin/python). Waits for the firmware's "k" after every 4096
bytes, as send_faces.py does.
"""
import os
import sys
import time

import serial

from send_faces import CHUNK, SIZE, wait_for


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


def main():
    port = serial.Serial(sys.argv[1], 115200, timeout=5)
    scene = int(sys.argv[3])
    faces = [int(f) for f in sys.argv[4:]] or list(range(6))
    for f in faces:
        send(port, scene, f, os.path.join(sys.argv[2], f"face{f}.bin"))


if __name__ == "__main__":
    main()
