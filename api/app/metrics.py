"""Prometheus metrics.

Deliberately hand-rolled and small rather than pulled from a library, so every
metric here is one you can explain. Three kinds are represented on purpose:

  Counter   -- monotonically increasing totals (requests served)
  Histogram -- distribution of a value (request latency, for percentiles)
  Gauge     -- a value that goes up and down (how stale the data is)
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

REQUESTS = Counter(
    "safahawa_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "path", "status"],
)

LATENCY = Histogram(
    "safahawa_http_request_duration_seconds",
    "Request latency in seconds.",
    ["method", "path"],
    # Tuned for this service: most reads land under 50ms, so the default
    # buckets would put almost everything in one bucket and tell us nothing.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

DATA_AGE = Gauge(
    "safahawa_data_age_seconds",
    "Age of the newest reading in the database. Alert when this climbs.",
)

READINGS_TOTAL = Gauge(
    "safahawa_readings_total",
    "Total rows in the readings table.",
)


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started

    # Use the *route template* ("/api/v1/stations/{slug}/readings"), never the
    # raw URL. Labelling by raw path would create a new time series per station
    # and eventually take down Prometheus. This is the cardinality trap.
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")

    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    LATENCY.labels(request.method, path).observe(elapsed)
    return response


def render_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
