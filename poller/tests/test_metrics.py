"""Tests for poller Prometheus metrics."""

from poller.metrics import (
    POLL_DURATION_SECONDS,
    POLL_LAST_SUCCESS_TIMESTAMP,
    POLL_ROWS_INSERTED_TOTAL,
    POLL_ROWS_SKIPPED_TOTAL,
    POLL_RUNS_TOTAL,
    maybe_push_metrics,
)


def test_poller_metrics_recording():
    """Verify that poller metrics record counters, histograms, and gauges without error."""
    before_ok = POLL_RUNS_TOTAL.labels(status="ok")._value.get()
    POLL_RUNS_TOTAL.labels(status="ok").inc()
    assert POLL_RUNS_TOTAL.labels(status="ok")._value.get() == before_ok + 1

    before_inserted = POLL_ROWS_INSERTED_TOTAL._value.get()
    POLL_ROWS_INSERTED_TOTAL.inc(10)
    assert POLL_ROWS_INSERTED_TOTAL._value.get() == before_inserted + 10

    before_skipped = POLL_ROWS_SKIPPED_TOTAL._value.get()
    POLL_ROWS_SKIPPED_TOTAL.inc(5)
    assert POLL_ROWS_SKIPPED_TOTAL._value.get() == before_skipped + 5

    POLL_DURATION_SECONDS.observe(1.23)
    POLL_LAST_SUCCESS_TIMESTAMP.set_to_current_time()
    assert POLL_LAST_SUCCESS_TIMESTAMP._value.get() > 0


def test_maybe_push_metrics_noop_when_url_empty():
    """Verify push is a safe no-op when URL is None."""
    maybe_push_metrics(None)
