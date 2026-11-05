"""Play microSD scenes first..last as a flip-book through the ESP-NOW bridge (both modules at once).

    python play_scenes.py BRIDGE_PORT FIRST LAST [--sec 5] [--loops 1]

Sends "#s<k>" for each scene, one every --sec seconds. A switch takes about 2.7 s on the cube (each
board reads its face from the microSD, about 0.3 s, then draws it, about 0.6 s), so --sec below 3
queues lines faster than the cube draws them. lst_year.py's 24 half-months live in scenes 101..124:
    python play_scenes.py /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_68:EE:8F:4B:1E:84-if00 101 124
"""
import argparse
import time


def lines(first, last, loops=1):
    one = [f"#s{k}" for k in range(first, last + 1)]
    return one if first == last else one * loops


def play(ls, sec, send, sleep=time.sleep):
    for i, line in enumerate(ls):
        if i:
            sleep(sec)
        send(line)


def main():
    import serial

    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("first", type=int)
    ap.add_argument("last", type=int)
    ap.add_argument("--sec", type=float, default=5.0)
    ap.add_argument("--loops", type=int, default=1)
    a = ap.parse_args()
    p = serial.Serial(a.port, 115200, timeout=0.2)

    def send(line):
        p.write(line.encode() + b"\n")
        print(time.strftime("%H:%M:%S"), line, flush=True)

    play(lines(a.first, a.last, a.loops), a.sec, send)


if __name__ == "__main__":
    main()
