"""Watch a battery-powered cube over ESP-NOW until it stops answering.

    python battery_watch.py PORT MAC LOG.csv [--period 60] [--show 40] [--until 2026-10-29T10:00]

PORT is espnow_bridge's serial port, MAC the cube's XIAO. Every PERIOD
seconds it sends "#G<SHOW>,1,30" (planes and ships for SHOW seconds, then
the scene stays) and, once that has run, "#p" (the cube broadcasts a ping).
Both go as unicasts, so the bridge reports whether the XIAO's radio sent an
ACK; the ping coming back shows the firmware itself is running. One CSV row
per cycle: time, ACK for #G, ACK for #p, ping received. Needs pyserial
(pi5-deck: ~/.venv-esptool/bin/python).
"""
import argparse
import csv
import datetime as dt
import sys
import time

import serial


def send(port, mac, cmd, wait):
    """Unicast cmd; return (acked, lines read within wait seconds)."""
    port.reset_input_buffer()
    port.write(f"!{mac} {cmd}\n".encode())
    buf, t0 = b"", time.time()
    while time.time() - t0 < wait:
        buf += port.read(port.in_waiting or 1)
    lines = buf.decode(errors="replace").splitlines()
    return any(l.startswith("delivered ok") for l in lines), lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("mac")
    ap.add_argument("log")
    ap.add_argument("--period", type=float, default=60)
    ap.add_argument("--show", type=int, default=40, help="seconds of planes and ships per cycle")
    ap.add_argument("--until", help="stop at this local time (ISO), default: run until killed")
    args = ap.parse_args()
    until = dt.datetime.fromisoformat(args.until) if args.until else None
    port = serial.Serial(args.port, 115200, timeout=0.2)
    time.sleep(1)
    with open(args.log, "a", newline="") as f:
        out = csv.writer(f)
        if f.tell() == 0:
            out.writerow(["time", "ack_G", "ack_p", "ping"])
        while until is None or dt.datetime.now() < until:
            t0 = time.time()
            now = dt.datetime.now().isoformat(timespec="seconds")
            ack_g, _ = send(port, args.mac, f"#G{args.show},1,30", 2)
            time.sleep(max(0.0, args.show + 6 - (time.time() - t0)))  # #G sets up for about 4.3 s, then runs SHOW s
            ack_p, lines = send(port, args.mac, "#p", 3)
            ping = any("ping from the cube" in l for l in lines)
            out.writerow([now, int(ack_g), int(ack_p), int(ping)])
            f.flush()
            print(now, ack_g, ack_p, ping, flush=True)
            time.sleep(max(0.0, args.period - (time.time() - t0)))


if __name__ == "__main__":
    sys.exit(main())
