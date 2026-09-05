"""Test fixtures.

These tests talk to a real Postgres. Not a mock, not SQLite -- the queries use
DISTINCT ON, date_trunc with a timezone, and an ON CONFLICT constraint, none of
which SQLite implements the same way. A test suite that passes against SQLite
and fails against Postgres is worse than no test suite.

In CI this means the job needs a Postgres service container. That is the price
of testing what actually ships.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://hawa:hawa@localhost:5432/safahawa")
TEST_DB = "safahawa_test"
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Create a throwaway database, migrate it, drop it at the end."""
    admin = create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()

    os.environ["DATABASE_URL"] = TEST_URL

    from alembic import command
    from alembic.config import Config

    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg = Config(ini_path)
    cfg.set_main_option("script_location", script_dir)
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")

    yield TEST_URL

    admin = create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def engine(test_database):
    return create_engine(test_database, future=True)


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s


@pytest.fixture()
def clean_readings(engine):
    """Each test starts with an empty readings table but the seeded stations."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE readings, poll_runs RESTART IDENTITY"))
    yield


@pytest.fixture()
def client(test_database, clean_readings, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", test_database)

    # Rebind the app's engine to the test database. Import order matters:
    # app.config already read the env var at import time.
    from app import db
    from app.config import settings

    settings.database_url = test_database
    db.engine.dispose()
    db.engine = create_engine(test_database, future=True)
    db.SessionLocal.configure(bind=db.engine)

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded_readings(engine, clean_readings):
    """24 hours of readings at Kalanki, ending at the top of the current hour."""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = []
    for hours_ago in range(23, -1, -1):
        observed = now - timedelta(hours=hours_ago)
        pm25 = 20.0 + hours_ago  # deterministic, ascending into the past
        rows.append({"observed_at": observed, "pm2_5": pm25, "pm10": pm25 * 2})

    with engine.begin() as conn:
        station_id = conn.execute(
            text("SELECT id FROM stations WHERE slug = 'kalanki'")
        ).scalar_one()
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO readings (station_id, observed_at, pm2_5, pm10, us_aqi) "
                    "VALUES (:sid, :observed_at, :pm2_5, :pm10, NULL)"
                ),
                {"sid": station_id, **row},
            )
    return rows
