"""ORM models.

Schema ownership note: the API owns the schema. The poller is a *dumb writer* --
it inserts rows with plain SQL and knows nothing about migrations. That means
migrations must run before the poller starts, which is a real deployment
ordering problem you have to solve in Kubernetes.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Station(Base):
    """A monitoring point in the Kathmandu Valley."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    readings: Mapped[list["Reading"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class Reading(Base):
    """One hourly observation for one station.

    The (station_id, observed_at) unique constraint is the whole idempotency
    story: the poller re-fetches overlapping windows every run, and the database
    -- not the application -- is what guarantees we never store the same hour
    twice.
    """

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    pm2_5: Mapped[float | None] = mapped_column(Float)
    pm10: Mapped[float | None] = mapped_column(Float)
    us_aqi: Mapped[int | None] = mapped_column(Integer)
    nitrogen_dioxide: Mapped[float | None] = mapped_column(Float)
    ozone: Mapped[float | None] = mapped_column(Float)
    carbon_monoxide: Mapped[float | None] = mapped_column(Float)
    sulphur_dioxide: Mapped[float | None] = mapped_column(Float)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    station: Mapped[Station] = relationship(back_populates="readings")

    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_reading_station_hour"),
        Index("ix_readings_station_observed", "station_id", "observed_at"),
    )


class PollRun(Base):
    """An audit row per poller execution.

    This is what turns 'is the poller working?' from a guess into a query, and
    it is what /api/v1/ingest/status and the freshness metric are built on.
    """

    __tablename__ = "poll_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok|partial|failed
    stations_polled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
