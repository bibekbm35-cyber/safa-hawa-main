"""Prometheus metrics for the poller service.

Exposes run counts, run duration, rows inserted/skipped, and last success timestamp.
Supports both:
1. In loop mode (Deployment): a lightweight HTTP server on `metrics_port` for Prometheus scraping.
2. In once mode (CronJob): optional push to Prometheus Pushgateway.
"""

import logging

from prometheus_client import Counter, Gauge, Histogram, push_to_gateway, start_http_server

log = logging.getLogger("safahawa.poller.metrics")

POLL_RUNS_TOTAL = Counter(
    "safahawa_poller_runs_total",
    "Total poll runs executed",
    labelnames=["status"],
)

POLL_DURATION_SECONDS = Histogram(
    "safahawa_poller_duration_seconds",
    "Time taken for a poll cycle in seconds",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

POLL_ROWS_INSERTED_TOTAL = Counter(
    "safahawa_poller_rows_inserted_total",
    "Total air quality observation rows newly inserted",
)

POLL_ROWS_SKIPPED_TOTAL = Counter(
    "safahawa_poller_rows_skipped_total",
    "Total duplicate air quality observation rows skipped",
)

POLL_LAST_SUCCESS_TIMESTAMP = Gauge(
    "safahawa_poller_last_success_timestamp",
    "Unix timestamp of the last successful poll run",
)


def start_metrics_exporter(port: int = 8001) -> None:
    """Start an HTTP server exposing /metrics for Prometheus scrapers."""
    try:
        start_http_server(port)
        log.info("Prometheus metrics server started on :%s", port)
    except Exception as exc:
        log.warning("Could not start metrics server on :%s: %s", port, exc)


def maybe_push_metrics(pushgateway_url: str | None, job: str = "safahawa_poller") -> None:
    """Push metrics to Prometheus Pushgateway if configured (useful for CronJobs)."""
    if not pushgateway_url:
        return
    try:
        push_to_gateway(pushgateway_url, job=job)
        log.info("Pushed metrics to Pushgateway at %s", pushgateway_url)
    except Exception as exc:
        log.warning("Failed to push metrics to Pushgateway: %s", exc)
