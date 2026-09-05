"""Poller entrypoint.

Runs in one of two modes, and which one you pick is a real design decision you
should be able to defend:

    python -m poller.run --once
        Do a single poll and exit 0/1. This is the shape a Kubernetes CronJob
        wants: the scheduler owns the timing, a crash is visible as a failed
        Job, and nothing is running between polls.

    python -m poller.run
        Poll forever on an internal timer. This is the shape a Deployment
        wants: one long-lived pod, no per-run container startup cost, but you
        own the scheduling and a wedged process looks alive to Kubernetes.

    python -m poller.run --backfill-days 30
        One-off historical load. Used to seed a fresh database so the charts
        are not empty on day one.
"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from poller.client import UpstreamError, fetch_raw, parse_block
from poller.config import settings
from poller.metrics import (
    POLL_DURATION_SECONDS,
    POLL_LAST_SUCCESS_TIMESTAMP,
    POLL_ROWS_INSERTED_TOTAL,
    POLL_ROWS_SKIPPED_TOTAL,
    POLL_RUNS_TOTAL,
    maybe_push_metrics,
    start_metrics_exporter,
)
from poller.store import connect, finish_run, load_stations, save_observations, start_run

logging.basicConfig(
    level=settings.log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("safahawa.poller")


def poll_once(past_days: int | None = None) -> tuple[int, int]:
    """Run one complete poll cycle. Returns (inserted, skipped)."""
    started = time.perf_counter()
    past_days = past_days if past_days is not None else max(1, settings.lookback_hours // 24)

    with connect() as conn:
        stations = load_stations(conn)
        if not stations:
            raise RuntimeError(
                "No active stations in the database. Did the migrations run?"
            )

        run_id = start_run(conn)
        try:
            blocks = fetch_raw(
                [s.latitude for s in stations],
                [s.longitude for s in stations],
                past_days=past_days,
            )

            if len(blocks) != len(stations):
                raise UpstreamError(
                    f"asked for {len(stations)} locations, upstream returned {len(blocks)}"
                )

            now = datetime.now(UTC)
            observations = []
            # Open-Meteo preserves request order, so block N is station N.
            for station, block in zip(stations, blocks, strict=True):
                observations.extend(parse_block(block, station.slug, now=now))

            station_ids = {s.slug: s.id for s in stations}
            inserted, skipped = save_observations(conn, station_ids, observations)

            duration_s = time.perf_counter() - started
            duration_ms = int(duration_s * 1000)
            finish_run(
                conn,
                run_id,
                status="ok",
                stations_polled=len(stations),
                rows_inserted=inserted,
                rows_skipped=skipped,
                duration_ms=duration_ms,
            )
            # Record Prometheus metrics
            POLL_RUNS_TOTAL.labels(status="ok").inc()
            POLL_DURATION_SECONDS.observe(duration_s)
            POLL_ROWS_INSERTED_TOTAL.inc(inserted)
            POLL_ROWS_SKIPPED_TOTAL.inc(skipped)
            POLL_LAST_SUCCESS_TIMESTAMP.set_to_current_time()
            maybe_push_metrics(settings.pushgateway_url)

            log.info(
                "poll ok: %s stations, %s inserted, %s already present, %sms",
                len(stations),
                inserted,
                skipped,
                duration_ms,
            )
            return inserted, skipped

        except Exception as exc:
            duration_s = time.perf_counter() - started
            duration_ms = int(duration_s * 1000)
            finish_run(
                conn,
                run_id,
                status="failed",
                stations_polled=len(stations),
                duration_ms=duration_ms,
                error=str(exc),
            )
            # Record failure in Prometheus metrics
            POLL_RUNS_TOTAL.labels(status="failed").inc()
            POLL_DURATION_SECONDS.observe(duration_s)
            maybe_push_metrics(settings.pushgateway_url)

            log.error("poll failed: %s", exc)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description="safa Hawa air quality poller")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="load this many days of history and exit (max 92 upstream)",
    )
    args = parser.parse_args()

    if args.backfill_days:
        days = min(args.backfill_days, 92)
        log.info("backfilling %s days of history", days)
        inserted, skipped = poll_once(past_days=days)
        log.info("backfill complete: %s new rows, %s already present", inserted, skipped)
        return 0

    if args.once:
        try:
            poll_once()
            return 0
        except Exception:
            # Non-zero exit is how a CronJob reports failure. Do not swallow it.
            return 1

    # Loop mode (Deployment) -- start Prometheus metrics server
    start_metrics_exporter(settings.metrics_port)
    log.info("starting poll loop, every %s minutes", settings.poll_interval_minutes)
    while True:
        try:
            poll_once()
        except Exception:
            # In loop mode a failure must NOT kill the process -- the next tick
            # may well succeed. The failure is already recorded in poll_runs
            # and will show up as rising data age in Prometheus.
            log.exception("poll cycle failed, continuing")
        time.sleep(settings.poll_interval_minutes * 60)


if __name__ == "__main__":
    sys.exit(main())
