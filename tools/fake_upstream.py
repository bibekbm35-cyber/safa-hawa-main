"""A stand-in for the Open-Meteo air quality API.

Why this exists: on presentation day the venue wifi will be bad, or the upstream
will be slow, and a live demo that depends on a third-party API is a demo that
can fail in front of judges. Point UPSTREAM_URL at this instead and the whole
pipeline runs with no internet at all.

It also makes the poller's tests fast and deterministic.

The generated data models the real thing: the Kathmandu valley traps pollution
in a bowl, so PM2.5 peaks around the morning and evening traffic hours and dips
in the early afternoon when the inversion lifts. Winter months are far worse
than monsoon months.

    python tools/fake_upstream.py --port 8555
"""

import argparse
import json
import math
import random
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

VARIABLE_UNITS = {
    "pm10": "\u03bcg/m\u00b3",
    "pm2_5": "\u03bcg/m\u00b3",
    "nitrogen_dioxide": "\u03bcg/m\u00b3",
    "sulphur_dioxide": "\u03bcg/m\u00b3",
    "ozone": "\u03bcg/m\u00b3",
    "carbon_monoxide": "\u03bcg/m\u00b3",
    "us_aqi": "USAQI",
}

PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]


def us_aqi_from_pm25(pm25: float) -> int:
    c = int(pm25 * 10) / 10
    for c_lo, c_hi, a_lo, a_hi in PM25_BREAKPOINTS:
        if c_lo <= c <= c_hi:
            return round((a_hi - a_lo) / (c_hi - c_lo) * (c - c_lo) + a_lo)
    return 500


def pm25_for(when: datetime, lat: float, lon: float) -> float:
    """Plausible PM2.5 for a Kathmandu Valley hour."""
    npt_hour = (when.hour + 5.75) % 24  # Nepal is UTC+5:45

    # Winter inversion: December-February is roughly triple the monsoon.
    month_factor = {
        1: 3.1,
        2: 2.8,
        3: 2.2,
        4: 1.8,
        5: 1.4,
        6: 0.8,
        7: 0.6,
        8: 0.6,
        9: 0.8,
        10: 1.5,
        11: 2.4,
        12: 3.0,
    }[when.month]

    # Twin traffic peaks near 08:00 and 19:00 local.
    morning = 22 * math.exp(-((npt_hour - 8) ** 2) / 8)
    evening = 26 * math.exp(-((npt_hour - 19) ** 2) / 10)
    baseline = 14

    # Low-lying, denser stations sit deeper in the bowl.
    bowl = 1.0 + max(0.0, (27.72 - lat)) * 6 + max(0.0, (85.32 - lon)) * 4

    rng = random.Random(int(when.timestamp()) + int(lat * 1000) + int(lon * 1000))
    noise = rng.uniform(0.82, 1.24)

    return round(max(2.0, (baseline + morning + evening) * month_factor * bowl * noise), 1)


def build_block(
    lat: float, lon: float, variables: list[str], past_days: int, forecast_days: int
) -> dict:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=past_days)).replace(hour=0)
    end = now + timedelta(days=forecast_days)

    times, series = [], {v: [] for v in variables}
    cursor = start
    while cursor <= end:
        times.append(cursor.strftime("%Y-%m-%dT%H:%M"))
        pm25 = pm25_for(cursor, lat, lon)
        rng = random.Random(int(cursor.timestamp()) ^ int(lat * 7919))
        for v in variables:
            if v == "pm2_5":
                series[v].append(pm25)
            elif v == "pm10":
                series[v].append(round(pm25 * rng.uniform(1.5, 2.3), 1))
            elif v == "us_aqi":
                series[v].append(us_aqi_from_pm25(pm25))
            elif v == "nitrogen_dioxide":
                series[v].append(round(pm25 * rng.uniform(0.3, 0.7), 1))
            elif v == "ozone":
                series[v].append(round(rng.uniform(25, 95), 1))
            elif v == "carbon_monoxide":
                series[v].append(round(pm25 * rng.uniform(6, 14), 1))
            elif v == "sulphur_dioxide":
                series[v].append(round(rng.uniform(1, 14), 1))
            else:
                series[v].append(None)
        cursor += timedelta(hours=1)

    return {
        "latitude": lat,
        "longitude": lon,
        "generationtime_ms": 0.4,
        "utc_offset_seconds": 0,
        "timezone": "UTC",
        "timezone_abbreviation": "UTC",
        "hourly_units": {v: VARIABLE_UNITS.get(v, "") for v in variables},
        "hourly": {"time": times, **series},
    }


class Handler(BaseHTTPRequestHandler):
    failure_rate = 0.0

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.endswith("/air-quality"):
            self.send_error(404, "unknown path")
            return

        # Optional chaos: set --failure-rate to prove the poller's backoff works.
        if random.random() < self.failure_rate:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"upstream having a bad day")
            return

        q = parse_qs(parsed.query)
        try:
            lats = [float(v) for v in q.get("latitude", ["27.7"])[0].split(",")]
            lons = [float(v) for v in q.get("longitude", ["85.3"])[0].split(",")]
            variables = q.get("hourly", ["pm2_5"])[0].split(",")
            past_days = int(q.get("past_days", ["1"])[0])
            forecast_days = int(q.get("forecast_days", ["1"])[0])
        except ValueError:
            self.send_error(400, "bad parameters")
            return

        blocks = [
            build_block(lat, lon, variables, past_days, forecast_days)
            for lat, lon in zip(lats, lons, strict=False)
        ]
        body = json.dumps(blocks if len(blocks) > 1 else blocks[0]).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8555)
    parser.add_argument(
        "--failure-rate",
        type=float,
        default=0.0,
        help="fraction of requests to fail with 503, for testing retry behaviour",
    )
    args = parser.parse_args()

    Handler.failure_rate = args.failure_rate
    print(f"fake upstream on http://127.0.0.1:{args.port}/v1/air-quality")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
