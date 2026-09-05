"""API contract tests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text


class TestHealth:
    def test_healthz_does_not_touch_the_database(self, client):
        assert client.get("/healthz").json()["status"] == "alive"

    def test_readyz_reports_the_database(self, client):
        body = client.get("/readyz").json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"


class TestStations:
    def test_seeded_stations_are_listed(self, client):
        stations = client.get("/api/v1/stations").json()
        slugs = {s["slug"] for s in stations}
        assert "kalanki" in slugs
        assert len(stations) == 8

    def test_stations_carry_coordinates(self, client):
        station = client.get("/api/v1/stations").json()[0]
        assert 27 < station["latitude"] < 28
        assert 85 < station["longitude"] < 86


class TestReadings:
    def test_unknown_station_is_404_not_empty_list(self, client):
        """An empty list would let a typo in the UI look like clean air."""
        response = client.get("/api/v1/stations/pokhara/readings")
        assert response.status_code == 404

    def test_window_is_respected(self, client, seeded_readings):
        six = client.get("/api/v1/stations/kalanki/readings?hours=6").json()
        full = client.get("/api/v1/stations/kalanki/readings?hours=24").json()
        assert len(six) < len(full)
        assert len(full) == 24

    def test_readings_are_returned_oldest_first(self, client, seeded_readings):
        rows = client.get("/api/v1/stations/kalanki/readings?hours=24").json()
        times = [r["observed_at"] for r in rows]
        assert times == sorted(times)

    def test_aqi_is_derived_when_upstream_omitted_it(self, client, seeded_readings):
        """The fixture inserts us_aqi as NULL on purpose.

        The API must fill it in from PM2.5 rather than returning null, or the
        chart would show gaps that look like missing data.
        """
        rows = client.get("/api/v1/stations/kalanki/readings?hours=24").json()
        assert all(r["us_aqi"] is not None for r in rows)
        assert all(r["band"] is not None for r in rows)

    def test_hours_parameter_is_bounded(self, client):
        assert client.get("/api/v1/stations/kalanki/readings?hours=0").status_code == 422
        assert client.get("/api/v1/stations/kalanki/readings?hours=99999").status_code == 422

    def test_pagination_limit_and_offset(self, client, seeded_readings):
        page1 = client.get("/api/v1/stations/kalanki/readings?hours=24&limit=5&offset=0").json()
        page2 = client.get("/api/v1/stations/kalanki/readings?hours=24&limit=5&offset=5").json()
        assert len(page1) == 5
        assert len(page2) == 5
        assert page1[0]["observed_at"] != page2[0]["observed_at"]

    def test_pagination_bounds_validation(self, client):
        assert client.get("/api/v1/stations/kalanki/readings?limit=0").status_code == 422
        assert client.get("/api/v1/stations/kalanki/readings?limit=1000").status_code == 422
        assert client.get("/api/v1/stations/kalanki/readings?offset=-1").status_code == 422


class TestWorst:
    def test_worst_station_fallback_when_empty(self, client):
        """When no readings exist, return the first active station with reading=null."""
        res = client.get("/api/v1/worst")
        assert res.status_code == 200
        data = res.json()
        assert "station" in data
        assert data["reading"] is None

    def test_worst_station_picks_highest_aqi(self, client, seeded_readings):
        """Returns the station with the highest AQI."""
        res = client.get("/api/v1/worst")
        assert res.status_code == 200
        data = res.json()
        assert data["station"]["slug"] == "kalanki"
        assert data["reading"]["us_aqi"] is not None


class TestLatest:
    def test_every_station_appears_even_without_data(self, client):
        """A station with no readings must still be listed, with reading=null.

        Silently dropping it would make a broken sensor invisible.
        """
        rows = client.get("/api/v1/latest").json()
        assert len(rows) == 8
        assert all(r["reading"] is None for r in rows)

    def test_returns_the_newest_row_per_station(self, client, seeded_readings):
        rows = {r["station"]["slug"]: r for r in client.get("/api/v1/latest").json()}
        kalanki = rows["kalanki"]
        assert kalanki["reading"] is not None
        # The fixture makes the newest hour the lowest PM2.5 value.
        assert kalanki["reading"]["pm2_5"] == 20.0
        assert kalanki["age_minutes"] is not None
        assert kalanki["advice"]


class TestSummary:
    def test_daily_rollup_counts_hours(self, client, seeded_readings):
        days = client.get("/api/v1/stations/kalanki/summary?days=7").json()
        assert days
        assert sum(d["hours_recorded"] for d in days) == 24
        assert all(d["max_aqi"] >= d["min_aqi"] for d in days)
        # avg AQI is derived from the average concentration, never averaged
        assert all(d["avg_aqi"] is not None for d in days)


class TestIngestStatus:
    def test_empty_database_reports_stale(self, client):
        """No data at all is stale, not fresh. Getting this backwards means a
        pipeline that never started looks healthy."""
        body = client.get("/api/v1/ingest/status").json()
        assert body["stale"] is True
        assert body["total_readings"] == 0

    def test_recent_data_is_not_stale(self, client, seeded_readings):
        body = client.get("/api/v1/ingest/status").json()
        assert body["stale"] is False
        assert body["total_readings"] == 24

    def test_old_data_is_reported_stale(self, client, engine, clean_readings):
        with engine.begin() as conn:
            sid = conn.execute(
                text("SELECT id FROM stations WHERE slug = 'thamel'")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO readings (station_id, observed_at, pm2_5) "
                    "VALUES (:sid, :t, 30.0)"
                ),
                {"sid": sid, "t": datetime.now(UTC) - timedelta(hours=9)},
            )
        body = client.get("/api/v1/ingest/status").json()
        assert body["stale"] is True
        assert body["data_age_minutes"] > 480


class TestMetrics:
    def test_metrics_endpoint_exposes_prometheus_text(self, client):
        client.get("/api/v1/stations")
        body = client.get("/metrics").text
        assert "safahawa_http_requests_total" in body
        assert "safahawa_readings_total" in body

    def test_path_label_uses_the_route_template(self, client, seeded_readings):
        """Guards the cardinality trap: one time series for all stations, not
        one per station slug."""
        client.get("/api/v1/stations/kalanki/readings")
        client.get("/api/v1/stations/thamel/readings")
        body = client.get("/metrics").text
        assert "/api/v1/stations/{slug}/readings" in body
        assert 'path="/api/v1/stations/kalanki/readings"' not in body
