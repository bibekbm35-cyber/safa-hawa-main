"""Database writes.

The poller uses raw psycopg rather than the API's SQLAlchemy models. That is a
deliberate boundary: the API owns the schema, the poller is a dumb writer. It
keeps the poller image small and its dependency list short, and it means the
poller can never accidentally run a migration.

The consequence is a deployment ordering requirement -- migrations must have
run before the poller starts -- which is a real problem you have to solve, not
one to hide.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from poller.client import Observation
from poller.config import settings

log = logging.getLogger("safahawa.poller.store")

INSERT_SQL = """
INSERT INTO readings (
    station_id, observed_at, pm2_5, pm10, us_aqi,
    nitrogen_dioxide, ozone, carbon_monoxide, sulphur_dioxide
)
VALUES (
    %(station_id)s, %(observed_at)s, %(pm2_5)s, %(pm10)s, %(us_aqi)s,
    %(nitrogen_dioxide)s, %(ozone)s, %(carbon_monoxide)s, %(sulphur_dioxide)s
)
ON CONFLICT (station_id, observed_at) DO NOTHING
"""


@dataclass
class Station:
    id: int
    slug: str
    latitude: float
    longitude: float


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.dsn, row_factory=dict_row)


def load_stations(conn: psycopg.Connection) -> list[Station]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, slug, latitude, longitude FROM stations WHERE active ORDER BY id")
        return [Station(**row) for row in cur.fetchall()]


def save_observations(
    conn: psycopg.Connection, station_ids: dict[str, int], observations: list[Observation]
) -> tuple[int, int]:
    """Insert observations, skipping ones we already have.

    Returns (inserted, skipped). The skip count is not a warning -- it is the
    expected outcome for most rows, because every poll deliberately re-requests
    an overlapping window.
    """
    if not observations:
        return 0, 0

    payload = [
        {
            "station_id": station_ids[o.station_slug],
            "observed_at": o.observed_at,
            "pm2_5": o.pm2_5,
            "pm10": o.pm10,
            "us_aqi": o.us_aqi,
            "nitrogen_dioxide": o.nitrogen_dioxide,
            "ozone": o.ozone,
            "carbon_monoxide": o.carbon_monoxide,
            "sulphur_dioxide": o.sulphur_dioxide,
        }
        for o in observations
        if o.station_slug in station_ids
    ]

    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, payload)
        inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()

    return inserted, len(payload) - inserted


def start_run(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO poll_runs (started_at, status) VALUES (%s, %s) RETURNING id",
            (datetime.now(UTC), "running"),
        )
        run_id = cur.fetchone()["id"]
    conn.commit()
    return run_id


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    stations_polled: int = 0,
    rows_inserted: int = 0,
    rows_skipped: int = 0,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE poll_runs
               SET finished_at = %s, status = %s, stations_polled = %s,
                   rows_inserted = %s, rows_skipped = %s, duration_ms = %s,
                   error = %s
             WHERE id = %s
            """,
            (
                datetime.now(UTC),
                status,
                stations_polled,
                rows_inserted,
                rows_skipped,
                duration_ms,
                error[:2000] if error else None,
                run_id,
            ),
        )
    conn.commit()
