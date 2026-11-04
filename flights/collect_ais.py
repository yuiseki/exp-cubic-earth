"""Every hour: listen to aisstream.io worldwide for a few minutes and keep where the moving ships are.

Ships move about 0.25 degrees an hour, so one short window an hour is enough for the cube
(daily_ships.py turns a day of these into ships.bin). A moving class A ship reports every 2 to
10 s and class B every 30 s, so 5 minutes catches nearly all of them that a receiver hears.
Name and type come in ShipStaticData only every 6 minutes, so they are kept across windows
in static.json.

Coverage is that of the volunteers' shore receivers: Europe dominates, the open ocean is thin.

Writes ROOT/<UTC day>/<UTC hour>.json = {"t": start, "messages": n, "rows": [[lat, lon, cog,
"<MMSI>", type or null, 0], ...]} (the row layout of globe_snapshots.py).
The key is AISSTREAM_API_KEY in ~/Workspaces/.env; it is never printed.

Usage: python -I collect_ais.py [--sec 300]
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path("/sata_hdd_24tb/ais")
LOG = pathlib.Path.home() / "logs" / "ais-hourly.log"
ENV = pathlib.Path.home() / "Workspaces" / ".env"
URL = "wss://stream.aisstream.io/v0/stream"
POSITIONS = ("PositionReport", "StandardClassBPositionReport")
MIN_KN, MAX_KN = 2.0, 40.0  # below: moored or drifting; above: not a ship (102.3 = not available)


def position(m):
    """-> (mmsi, lat, lon, cog) for a moving ship's position report, else None."""
    kind = m.get("MessageType")
    if kind not in POSITIONS:
        return None
    mmsi = m["MetaData"]["MMSI"]
    if not 200000000 <= mmsi < 800000000:  # ships only (111: SAR aircraft, 99: aids to navigation, 970: SART)
        return None
    p = m["Message"][kind]
    lat, lon, sog = p["Latitude"], p["Longitude"], p["Sog"]
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and MIN_KN <= sog <= MAX_KN):
        return None
    return mmsi, lat, lon, p["Cog"]


def static(m):
    """-> (mmsi, name, type) from ShipStaticData, else None."""
    if m.get("MessageType") != "ShipStaticData":
        return None
    s = m["Message"]["ShipStaticData"]
    return m["MetaData"]["MMSI"], s["Name"].strip(), s["Type"]


class Window:
    def __init__(self):
        self.ships, self.names, self.messages, self.breaks = {}, {}, 0, 0

    def add(self, m):
        self.messages += 1
        p = position(m)
        if p:
            self.ships[p[0]] = p[1:]
            return
        s = static(m)
        if s:
            self.names[s[0]] = s[1:]


def rows(ships, names):
    return [[lat, lon, cog, str(k), names.get(k, (None, None))[1], 0] for k, (lat, lon, cog) in ships.items()]


def log(msg):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def api_key():
    for line in ENV.read_text().splitlines():
        if line.startswith("AISSTREAM_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return None


async def listen(key, until, w):
    """Add messages to w until time.monotonic() reaches until."""
    import websockets
    # No keepalive pings: aisstream answered them late under load and the client closed a busy stream (2026-11-04)
    async with websockets.connect(URL, max_size=1 << 22, open_timeout=30, ping_interval=None) as ws:
        await ws.send(json.dumps({"APIKey": key, "BoundingBoxes": [[[-90, -180], [90, 180]]],
                                  "FilterMessageTypes": [*POSITIONS, "ShipStaticData"]}))
        while (left := until - time.monotonic()) > 0:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=left)
            except asyncio.TimeoutError:
                break
            w.add(json.loads(raw))


def collect(key, sec, w, listen=listen, now=time.monotonic, tries=5):
    """Listen for sec seconds, connecting again (up to tries times) when the stream breaks."""
    until = now() + sec
    for _ in range(tries):
        if now() >= until:
            return
        try:
            asyncio.run(listen(key, until, w))
            return
        except Exception as e:  # keep what arrived before the break
            w.breaks += 1
            log(f"stream broke after {w.messages} messages: {type(e).__name__}: {e}")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".new")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sec", type=int, default=300)
    a = ap.parse_args()
    key = api_key()
    if not key:
        log("AISSTREAM_API_KEY missing")
        return 1
    start = dt.datetime.now(dt.timezone.utc)
    w = Window()
    collect(key, a.sec, w)
    if not w.ships:
        log(f"no ships ({w.messages} messages)")
        return 1
    cache = ROOT / "static.json"
    names = {int(k): tuple(v) for k, v in json.loads(cache.read_text()).items()} if cache.exists() else {}
    names.update(w.names)
    write_json(cache, {str(k): v for k, v in names.items()})
    out = ROOT / start.date().isoformat() / f"{start.hour:02d}.json"
    write_json(out, {"t": int(start.timestamp()), "messages": w.messages, "rows": rows(w.ships, names)})
    typed = sum(1 for k in w.ships if k in names)
    log(f"{out.parent.name}/{out.name}: {len(w.ships)} moving ships ({typed} with type), {w.messages} messages in {a.sec} s, {w.breaks} breaks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
