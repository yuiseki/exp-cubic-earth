"""Write face<k>.bin files (from clouds.py) to lt7680_multi's microSD as one scene (#w).

    python send_scene.py PORT DIR SCENE [FACE ...]     (default faces: 0 1 2 3 4 5)

The XIAO stores them as /scenes/<SCENE>/face<f>.bin; #s<SCENE> (over USB or
ESP-NOW) then draws the scene. Needs pyserial (pi5-deck:
~/.venv-esptool/bin/python). Waits for the firmware's "k" after every 4096
bytes, as send_faces.py does.
"""
import os
import sys
import termios
import time

import serial

from send_faces import CHUNK, SIZE, wait_for


BOOT_MARKS = (b"ESP-ROM", b"rst:")


def settle(port):
    """After opening the port: if the XIAO is booting (opening it can reset it, as on pi4-deck
    2026-10-29), wait for "shell ready" so the first #w is not lost. True if it had reset."""
    time.sleep(1.0)
    buf = port.read(port.in_waiting) if port.in_waiting else b""
    if not any(m in buf for m in BOOT_MARKS):
        return False
    if b"shell ready" not in buf:
        buf += wait_for(port, "shell ready", 15)
    print("the XIAO reset when the port opened; waited for its shell")
    return True


def open_port(path):
    port = serial.Serial(path, 115200, timeout=5)
    try:  # do not drop DTR/RTS on close (a line change can reset the XIAO)
        attrs = termios.tcgetattr(port.fd)
        attrs[2] &= ~termios.HUPCL
        termios.tcsetattr(port.fd, termios.TCSANOW, attrs)
    except termios.error:
        pass
    settle(port)
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


def main():
    port = open_port(sys.argv[1])
    scene = int(sys.argv[3])
    faces = [int(f) for f in sys.argv[4:]] or list(range(6))
    for f in faces:
        send(port, scene, f, os.path.join(sys.argv[2], f"face{f}.bin"))


if __name__ == "__main__":
    main()
