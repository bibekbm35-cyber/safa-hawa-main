"""Upstream client for the Open-Meteo air quality API.

Two things make this more than `requests.get`:

* **Retry with exponential backoff and jitter.** A free upstream will time out
  and 503 sometimes. Retrying immediately in a tight loop is how you get
  rate-limited; retrying with jitter is how a fleet of clients avoids all
  waking up at the same instant after an outage.
* **Retrying only what is worth retrying.** A 404 or a 400 will never succeed
  on the second attempt -- retrying those wastes time and hides a real bug.
"""

import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from poller.config import settings

log = logging.getLogger("safahawa.poller.client")

HOURLY_VARIABLES = [
    "pm10",
    "pm2_5",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "carbon_monoxide",
    "us_aqi",
]

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class UpstreamError(RuntimeError):
    """Upstream did not give us usable data after every attempt."""


@dataclass(frozen=True)
class Observation:
    station_slug: str
    observed_at: datetime
    pm2_5: float | None
    pm10: float | None
    us_aqi: int | None
    nitrogen_dioxide: float | None
    ozone: float | None
    carbon_monoxide: float | None
    sulphur_dioxide: float | None


def _sleep_for(attempt: int) -> float:
    """Exponential backoff with full jitter: 2s, 4s, 8s -- each randomised."""
    ceiling = settings.backoff_base_seconds * (2 ** (attempt - 1))
    return random.uniform(0, ceiling)


def fetch_raw(
    latitudes: list[float],
    longitudes: list[float],
    past_days: int = 1,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch every station in one request and return the raw per-location blocks."""
    params = {
        "latitude": ",".join(str(v) for v in latitudes),
        "longitude": ",".join(str(v) for v in longitudes),
        "hourly": ",".join(HOURLY_VARIABLES),
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "UTC",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=settings.request_timeout_seconds)

    try:
        last_error: Exception | None = None
        for attempt in range(1, settings.max_attempts + 1):
            try:
                response = client.get(settings.upstream_url, params=params)
                if response.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                # A single coordinate returns an object; several return a list.
                # Normalising here keeps the rest of the code from caring.
                return payload if isinstance(payload, list) else [payload]

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise UpstreamError(
                        f"upstream refused the request: {exc.response.status_code} "
                        f"{exc.response.text[:200]}"
                    ) from exc
                last_error = exc

            if attempt < settings.max_attempts:
                delay = _sleep_for(attempt)
                log.warning(
                    "upstream attempt %s/%s failed (%s), retrying in %.1fs",
                    attempt,
                    settings.max_attempts,
                    type(last_error).__name__,
                    delay,
                )
                time.sleep(delay)

        raise UpstreamError(
            f"upstream unreachable after {settings.max_attempts} attempts: {last_error}"
        )
    finally:
        if owns_client:
            client.close()


def parse_block(block: dict, station_slug: str, now: datetime | None = None) -> list[Observation]:
    """Turn one location's hourly arrays into Observation rows.

    Two filters matter here:

    * We drop hours in the future. The upstream mixes forecast into the same
      arrays, and storing a forecast as an observation would make "current air
      quality" a prediction -- which is a lie the UI has no way to detect.
    * We drop hours where every pollutant is null. Those are gaps in the
      upstream model, not zero pollution.
    """
    now = now or datetime.now(UTC)
    hourly = block.get("hourly") or {}
    times = hourly.get("time") or []

    observations: list[Observation] = []
    for i, raw_time in enumerate(times):
        observed_at = datetime.fromisoformat(raw_time).replace(tzinfo=UTC)
        if observed_at > now:
            continue

        def value(key: str, idx: int = i):
            series = hourly.get(key) or []
            return series[idx] if idx < len(series) else None

        pm2_5 = value("pm2_5")
        pm10 = value("pm10")
        us_aqi = value("us_aqi")

        if pm2_5 is None and pm10 is None and us_aqi is None:
            continue

        observations.append(
            Observation(
                station_slug=station_slug,
                observed_at=observed_at,
                pm2_5=pm2_5,
                pm10=pm10,
                us_aqi=int(us_aqi) if us_aqi is not None else None,
                nitrogen_dioxide=value("nitrogen_dioxide"),
                ozone=value("ozone"),
                carbon_monoxide=value("carbon_monoxide"),
                sulphur_dioxide=value("sulphur_dioxide"),
            )
        )
    return observations
