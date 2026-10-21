"""Read a page of a board's display RAM through lt7680_multi's #X and save it (460,800 bytes).

    python dump_page.py PORT BOARD PAGE OUT
"""
import sys
import time

import serial

port = serial.Serial(sys.argv[1], 115200, timeout=30)
port.reset_input_buffer()
port.write(f"#{sys.argv[2]}".encode())
time.sleep(0.3)
port.write(f"#X{sys.argv[3]}\n".encode())
buf = b""
while b"X begin\r\n" not in buf:
    buf += port.read(1)
data = b""
while len(data) < 460800:
    chunk = port.read(460800 - len(data))
    if not chunk:
        raise SystemExit(f"timed out after {len(data)} bytes")
    data += chunk
open(sys.argv[4], "wb").write(data)
print("saved", len(data), "bytes")
