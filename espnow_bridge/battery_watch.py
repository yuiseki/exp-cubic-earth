"""Watch battery-powered cube modules over ESP-NOW until they stop answering.

    python battery_watch.py PORT LOG.csv MAC [MAC ...] [--period 60] [--show 40] [--until 2026-10-29T10:00]

PORT is espnow_bridge's serial port, each MAC a module's XIAO. Every PERIOD
seconds it sends a drawing load to every module one right after the other
(--loads: picked at random each cycle from t #t<SHOW> real planes and ships,
G #G<SHOW>,1,30 made-up ones, v #v Shikisai scenes from the microSD, j #j
web pictures over Wi-Fi; default G), and, once that has run, "#p" (each
module broadcasts a ping; it also stops a #v loop). Both go as unicasts, so the
bridge reports per module whether the XIAO's radio sent an ACK
("delivered ok to <MAC>"); the ping coming back ("rx <MAC>: ping from the
cube") shows the firmware itself is running. One CSV row per cycle: the
time, the load, then ACK for the load, ACK for #p and ping received for each module
(columns named by the MAC's last 4 hex digits). Needs pyserial
(~/.venv-esptool/bin/python).
"""
import argparse
import csv
import datetime as dt
import sys
import random
import time

import serial


def acked(lines, mac):
    return f"delivered ok to {mac.upper()}" in lines


def pinged(lines, mac):
    return any(l.startswith(f"rx {mac.upper()}:") and "ping from the cube" in l for l in lines)


V_MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-10"]


def pick_load(rng, show, kinds="tGvj"):
    """One drawing load for a cycle, picked at random from kinds: (kind, command).
    t: real planes and ships (#t, the heaviest, 72-81 ms a frame), G: made-up planes and ships,
    v: Shikisai scenes from the microSD every 3 s from a random month (the next #p stops it),
    j: the web pictures over Wi-Fi (#j). Each runs about show seconds or less."""
    k = rng.choice(kinds)
    if k == "t":
        return k, f"#t{show}"
    if k == "G":
        return k, f"#G{show},1,30"
    if k == "v":
        return k, f"#vshikisai-lst,{rng.choice(V_MONTHS)},2026-10,3"
    return k, "#j"


def header(macs, load=False):
    cols = ["time"] + (["load"] if load else [])
    for m in macs:
        tag = m.replace(":", "").upper()[-4:]
        cols += [f"ack_G_{tag}", f"ack_p_{tag}", f"ping_{tag}"]
    return cols


def read_for(port, wait):
    buf, t0 = b"", time.time()
    while time.time() - t0 < wait:
        buf += port.read(port.in_waiting or 1)
    return [l.strip() for l in buf.decode(errors="replace").splitlines()]


def send_all(port, macs, cmd, wait):
    """Unicast cmd to every module; return the lines read within wait seconds after the last one."""
    port.reset_input_buffer()
    lines = []
    for m in macs:
        port.write(f"!{m.upper()} {cmd}\n".encode())
        lines += read_for(port, 0.3)  # the ACK report for this one
    return lines + read_for(port, wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("log")
    ap.add_argument("macs", nargs="+")
    ap.add_argument("--period", type=float, default=60)
    ap.add_argument("--show", type=int, default=40, help="seconds of planes and ships per cycle")
    ap.add_argument("--until", help="stop at this local time (ISO), default: run until killed")
    ap.add_argument("--loads", default="G", help="kinds to pick from at random each cycle: t G v j (default G, as before)")
    ap.add_argument("--seed", type=int, help="random seed (default: from the clock)")
    args = ap.parse_args()
    until = dt.datetime.fromisoformat(args.until) if args.until else None
    rng = random.Random(args.seed)
    port = serial.Serial(args.port, 115200, timeout=0.2)
    time.sleep(2)  # the bridge may reset when the port opens
    with open(args.log, "a", newline="") as f:
        out = csv.writer(f)
        if f.tell() == 0:
            out.writerow(header(args.macs, load=True))
        while until is None or dt.datetime.now() < until:
            t0 = time.time()
            now = dt.datetime.now().isoformat(timespec="seconds")
            kind, cmd = pick_load(rng, args.show, args.loads)
            g = send_all(port, args.macs, cmd, 1.5)
            time.sleep(max(0.0, args.show + 6 - (time.time() - t0)))  # #G and #t set up for 2-4.3 s, then run SHOW s
            p = send_all(port, args.macs, "#p", 3)
            row = [now, kind]
            for m in args.macs:
                row += [int(acked(g, m)), int(acked(p, m)), int(pinged(p, m))]
            out.writerow(row)
            f.flush()
            print(*row, flush=True)
            time.sleep(max(0.0, args.period - (time.time() - t0)))


if __name__ == "__main__":
    sys.exit(main())
