"""Every day, yesterday's clouds (clouds.py) on the web for the cube: <WEB>/<YYYY-MM-DD>/ and <WEB>/latest.txt.

    uv run -q --no-project --with numpy --with pillow --with pyproj python -I daily_clouds.py [--days 3]

Each day directory holds what clouds.py writes: the NASA GIBS VIIRS (NOAA-20) true-colour mosaic,
the two SSEC RealEarth infrared bands for the poles, face0-5.bin (480x480 RGB565, ready for
send_scene.py) and faces.png. A day counts as done once its faces.png is there; every run fills in
the missing days among the last --days, so a day GIBS or RealEarth refused is tried again tomorrow.
A day is built in a hidden directory and renamed into place, so a half-made day is never public;
a failed build stays hidden and the next try reuses the files it already fetched.
latest.txt names the newest finished day. GIBS adds the last swaths of a day a few hours after it
ends, so a day is wanted only from 05:00 UTC the next day (LAG). Logs to ~/logs/clouds-daily.log.
"""
import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WEB = pathlib.Path("/sata_hdd_24tb/www/html/static/tmp/cubic-earth/clouds")
LOG = pathlib.Path.home() / "logs" / "clouds-daily.log"


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}\n")


LAG = dt.timedelta(hours=5)  # GIBS completes a day's mosaic some hours after the day ends


def wanted_days(now, days):
    """The last `days` UTC days that ended at least LAG ago, newest first."""
    today = (now.astimezone(dt.timezone.utc) - LAG).date()
    return [(today - dt.timedelta(days=k)).isoformat() for k in range(1, days + 1)]


def missing(root, days):
    return [d for d in days if not (pathlib.Path(root) / d / "faces.png").exists()]


def run_clouds(day, out):
    subprocess.run([sys.executable, "-I", str(HERE / "clouds.py"), "--date", day, "--out", str(out)], check=True)


def make_day(root, day, build=run_clouds):
    root = pathlib.Path(root)
    tmp = root / f".{day}.tmp"  # kept when the build fails: the next try reuses what it fetched
    build(day, tmp)
    if (root / day).exists():  # a half-made day from before: set it aside, never delete
        os.replace(root / day, root / f".{day}.old-{int(dt.datetime.now().timestamp())}")
    os.replace(tmp, root / day)
    latest = root / "latest.txt"
    if not latest.exists() or latest.read_text().strip() < day:
        latest.with_suffix(".tmp").write_text(day + "\n")
        os.replace(latest.with_suffix(".tmp"), latest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    args = ap.parse_args()
    WEB.mkdir(parents=True, exist_ok=True)
    for day in missing(WEB, wanted_days(dt.datetime.now(dt.timezone.utc), args.days)):
        try:
            make_day(WEB, day)
            log(f"{day}: published {WEB / day}")
        except Exception as e:  # noqa: BLE001  one bad day must not stop the others
            log(f"{day}: failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
