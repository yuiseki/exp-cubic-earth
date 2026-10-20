"""Send face<k>.bin (from clouds.py) to lt7680_multi's #U, one face at a time.

    python send_faces.py PORT DIR [FACE ...]     (default faces: 0 1 2 3 4 5)

Needs pyserial (pi5-deck: ~/.venv-esptool/bin/python). Waits for the
firmware's "k" after every 4096 bytes; sent faster, the USB receive buffer
overflows.
"""
import os
import sys
import time

import serial

CHUNK = 4096
SIZE = 480 * 480 * 2


def wait_for(port, text, timeout):
    buf, t0 = b"", time.time()
    while time.time() - t0 < timeout:
        buf += port.read(port.in_waiting or 1)
        if text.encode() in buf:
            return buf
    raise SystemExit(f"no {text!r} within {timeout} s; got {buf[-200:]!r}")


def send(port, face, path):
    data = open(path, "rb").read()
    assert len(data) == SIZE, (path, len(data))
    port.reset_input_buffer()
    port.write(f"#U{face}\n".encode())
    wait_for(port, "U ready", 5)
    t0 = time.time()
    for i in range(0, SIZE, CHUNK):
        port.write(data[i:i + CHUNK])
        c = port.read(1)
        while c in (b"\r", b"\n"):  # the end of the "U ready" line
            c = port.read(1)
        if c != b"k":
            raise SystemExit(f"face {face}: no ack after byte {i} (got {c!r})")
    out = wait_for(port, f"U done {face}", 10)
    print(f"face {face}: {SIZE} bytes in {time.time() - t0:.1f} s; " + out.decode(errors="replace").strip().splitlines()[-2])


def main():
    port = serial.Serial(sys.argv[1], 115200, timeout=5)
    faces = [int(f) for f in sys.argv[3:]] or list(range(6))
    for f in faces:
        send(port, f, os.path.join(sys.argv[2], f"face{f}.bin"))


if __name__ == "__main__":
    main()
