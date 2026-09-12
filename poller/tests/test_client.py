"""Poller unit tests.

None of these touch a database or the real internet, so they run in under a
second and never flake. That is deliberate: the poller's risky behaviour is all
in parsing and retrying, and both can be tested in pure memory.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from poller.client import UpstreamError, fetch_raw, parse_block
from poller.config import settings

URL = settings.upstream_url


def block(times: list[str], **series) -> dict:
    return {"hourly": {"time": times, **series}}


class TestParseBlock:
    def test_maps_hourly_arrays_to_rows(self):
        now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        b = block(
            ["2026-01-15T10:00", "2026-01-15T11:00"],
            pm2_5=[80.0, 92.0],
            pm10=[150.0, 170.0],
            us_aqi=[164, 169],
        )
        rows = parse_block(b, "kalanki", now=now)
        assert len(rows) == 2
        assert rows[0].station_slug == "kalanki"
        assert rows[0].pm2_5 == 80.0
        assert rows[1].us_aqi == 169

    def test_future_hours_are_dropped(self):
        """Upstream mixes forecast into the same arrays.

        Storing a forecast as an observation would make the dashboard show a
        prediction as current air quality, and nothing downstream could tell
        the difference.
        """
        now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        b = block(
            ["2026-01-15T11:00", "2026-01-15T12:00", "2026-01-15T15:00"],
            pm2_5=[80.0, 85.0, 90.0],
        )
        rows = parse_block(b, "kalanki", now=now)
        assert [r.observed_at.hour for r in rows] == [11, 12]

    def test_fully_null_hours_are_dropped(self):
        """A gap in the upstream model is missing data, not zero pollution."""
        now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        b = block(
            ["2026-01-15T09:00", "2026-01-15T10:00"],
            pm2_5=[None, 80.0],
            pm10=[None, 150.0],
            us_aqi=[None, 164],
        )
        rows = parse_block(b, "kalanki", now=now)
        assert len(rows) == 1
        assert rows[0].pm2_5 == 80.0

    def test_partial_nulls_are_kept(self):
        """If PM2.5 is present we keep the row even when trace gases are null."""
        now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        b = block(["2026-01-15T10:00"], pm2_5=[80.0], ozone=[None], us_aqi=[None])
        rows = parse_block(b, "kalanki", now=now)
        assert len(rows) == 1
        assert rows[0].ozone is None
        assert rows[0].us_aqi is None

    def test_short_series_does_not_crash(self):
        """Upstream arrays are not guaranteed to be the same length."""
        now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        b = block(["2026-01-15T09:00", "2026-01-15T10:00"], pm2_5=[80.0], pm10=[150.0, 160.0])
        rows = parse_block(b, "kalanki", now=now)
        assert len(rows) == 2
        assert rows[1].pm2_5 is None

    def test_empty_payload_yields_nothing(self):
        assert parse_block({}, "kalanki") == []

    def test_timestamps_are_timezone_aware(self):
        """Naive datetimes silently compare wrong against tz-aware ones."""
        now = datetime.now(UTC)
        b = block([(now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")], pm2_5=[40.0])
        rows = parse_block(b, "thamel", now=now)
        assert rows[0].observed_at.tzinfo is not None


class TestFetchRetry:
    @respx.mock
    def test_single_location_response_is_normalised_to_a_list(self):
        respx.get(URL).mock(return_value=httpx.Response(200, json={"hourly": {"time": []}}))
        assert isinstance(fetch_raw([27.7], [85.3]), list)

    @respx.mock
    def test_retries_a_503_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(settings, "backoff_base_seconds", 0.001)
        route = respx.get(URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json=[{"hourly": {"time": []}}]),
            ]
        )
        result = fetch_raw([27.7], [85.3])
        assert route.call_count == 3
        assert result == [{"hourly": {"time": []}}]

    @respx.mock
    def test_retries_a_timeout(self, monkeypatch):
        monkeypatch.setattr(settings, "backoff_base_seconds", 0.001)
        route = respx.get(URL).mock(
            side_effect=[
                httpx.TimeoutException("too slow"),
                httpx.Response(200, json=[{"hourly": {"time": []}}]),
            ]
        )
        fetch_raw([27.7], [85.3])
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_a_400(self, monkeypatch):
        """A malformed request will never succeed on attempt two.

        Retrying it wastes 15 seconds and buries the real cause -- a bug in our
        query parameters -- under a generic timeout message.
        """
        monkeypatch.setattr(settings, "backoff_base_seconds", 0.001)
        route = respx.get(URL).mock(return_value=httpx.Response(400, text="bad param"))
        with pytest.raises(UpstreamError, match="refused"):
            fetch_raw([27.7], [85.3])
        assert route.call_count == 1

    @respx.mock
    def test_gives_up_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr(settings, "backoff_base_seconds", 0.001)
        route = respx.get(URL).mock(return_value=httpx.Response(503))
        with pytest.raises(UpstreamError, match="after 4 attempts"):
            fetch_raw([27.7], [85.3])
        assert route.call_count == settings.max_attempts

    @respx.mock
    def test_all_stations_go_in_one_request(self):
        """Eight stations must cost one HTTP call, not eight.

        The upstream is a free service; hammering it eight times per poll is
        both rude and slower.
        """
        route = respx.get(URL).mock(return_value=httpx.Response(200, json=[]))
        fetch_raw([27.7, 27.6, 27.5], [85.3, 85.2, 85.1])
        assert route.call_count == 1
        params = route.calls[0].request.url.params
        assert params["latitude"] == "27.7,27.6,27.5"
