"""Send the flip-book frames (b<board>-<frame>.bin from clouds_hourly.py) to lt7680_multi's #R.

    python send_frames.py PORT DIR BOARDS FRAMES

Needs pyserial (pi5-deck: ~/.venv-esptool/bin/python). Each frame goes
straight into that board's display RAM; play them with #M<ms>.
"""
import os
import sys
import time

import serial

from send_faces import CHUNK, SIZE, wait_for


def send(port, board, frame, path):
    data = open(path, "rb").read()
    assert len(data) == SIZE, (path, len(data))
    port.reset_input_buffer()
    port.write(f"#R{board},{frame}\n".encode())
    wait_for(port, "R ready", 5)
    for i in range(0, SIZE, CHUNK):
        port.write(data[i:i + CHUNK])
        c = port.read(1)
        while c in (b"\r", b"\n"):
            c = port.read(1)
        if c != b"k":
            raise SystemExit(f"board {board} frame {frame}: no ack after byte {i} (got {c!r})")
    wait_for(port, f"R done {board} {frame}", 10)


def main():
    port = serial.Serial(sys.argv[1], 115200, timeout=5)
    boards, frames = int(sys.argv[3]), int(sys.argv[4])
    t0 = time.time()
    for k in range(frames):
        for b in range(boards):
            send(port, b, k, os.path.join(sys.argv[2], f"b{b}-{k:02d}.bin"))
        print(f"frame {k} sent ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
