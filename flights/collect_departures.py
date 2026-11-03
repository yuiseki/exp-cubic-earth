"""Collect a day of real departures from the large airports, from OpenSky, a little every day.

    python3 -I collect_departures.py [--day YYYY-MM-DD]   (default: yesterday, UTC)

For the cube's planes, which are made up today (#G): a timetable of real flights takes many days
to gather, since OpenSky gives 4,000 flight credits a day and /flights/departure costs 30 for one
airport and one UTC day (2026-11-03: RJTT on 2026-11-02 was 542 departures, the longest 13.6 h).
So each run takes the next airports of airports.txt (the 1,148 large airports with scheduled
service and an ICAO code in OurAirports 2026-08, public domain), until the credits left would drop
below RESERVE, and goes on from there the next day; the list goes round in about nine days.

- Writes OUT/<day>/<ICAO>.json, OpenSky's answer as it is ([] when it had none). A file that is
  there already is not asked for again.
- State (the next airport) in OUT/state.json; a line per run in ~/logs/opensky-departures.log.
- Credentials: ~/Workspaces/.secrets/opensky/credentials.json (clientId, clientSecret), never printed.
"""
import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser("~/Workspaces/tmp/opensky/departures")
LOG = os.path.expanduser("~/logs/opensky-departures.log")
CRED = os.path.expanduser("~/Workspaces/.secrets/opensky/credentials.json")
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api/flights/departure"
COST, RESERVE = 30, 100


def plan(airports, start, credits, cost=COST, reserve=RESERVE):
    """The airports to ask for today: from start, round the list, while credits stay above reserve."""
    n = max(0, min(len(airports), (credits - reserve) // cost))
    return [airports[(start + i) % len(airports)] for i in range(n)]


def next_start(total, start, done):
    return (start + done) % total


def day_window(day):
    b = int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    return b, b + 86400


def token():
    c = json.load(open(CRED))
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": c["clientId"], "client_secret": c["clientSecret"]}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30))["access_token"]


def get(tok, airport, b, e):
    """(status, body, credits left or None)."""
    url = f"{API}?{urllib.parse.urlencode({'airport': airport, 'begin': b, 'end': e})}"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        status, body, hdr = r.status, r.read(), r.headers
    except urllib.error.HTTPError as err:
        status, body, hdr = err.code, err.read(), err.headers
    left = hdr.get("X-Rate-Limit-Remaining")
    return status, body, int(left) if left is not None else None


def log(line):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} {line}\n")
    print(line, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat())
    ap.add_argument("--max", type=int, default=10**6, help="at most this many airports (for a first test)")
    args = ap.parse_args()
    airports = [l.strip() for l in open(os.path.join(HERE, "airports.txt")) if l.strip() and not l.startswith("#")]
    state_path = os.path.join(OUT, "state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"next": 0}
    folder = os.path.join(OUT, args.day)
    os.makedirs(folder, exist_ok=True)
    b, e = day_window(args.day)
    tok = token()
    left = None
    done = asked = flights = 0
    start = state["next"]
    for i in range(min(len(airports), args.max)):
        if left is not None and plan(airports, 0, left) == []:
            break
        icao = airports[(start + i) % len(airports)]
        path = os.path.join(folder, f"{icao}.json")
        if not os.path.exists(path):
            status, body, l = get(tok, icao, b, e)
            left = l if l is not None else left
            if status == 404:
                body = b"[]"  # OpenSky: no flights in the window
            elif status == 401:
                tok = token()
                status, body, l = get(tok, icao, b, e)
                left = l if l is not None else left
            if status == 429:
                log(f"{args.day} rate limited at {icao} (done {done})")
                break
            if status not in (200, 404):
                log(f"{args.day} {icao} HTTP {status}: {body[:120]!r}")
                break
            open(path, "wb").write(body)
            asked += 1
            flights += len(json.loads(body))
            time.sleep(1)
        done += 1
    state["next"] = next_start(len(airports), start, done)
    json.dump(state, open(state_path, "w"))
    log(f"{args.day} airports {airports[start]}..{airports[(start + done - 1) % len(airports)] if done else '-'} ({done}, asked {asked}), flights {flights}, credits left {left}, next {state['next']}")


if __name__ == "__main__":
    main()
