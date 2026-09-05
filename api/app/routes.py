"""HTTP routes.

Everything is a read except nothing -- this API has no write endpoints at all.
The poller writes; the API reads. Saying that sentence out loud explains most
of the design.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.aqi import aqi_from_pm25, band_for, band_key_for
from app.config import settings
from app.db import get_session
from app.metrics import DATA_AGE, READINGS_TOTAL
from app.models import PollRun, Reading, Station
from app.schemas import (
    DailySummaryOut,
    HealthOut,
    IngestStatusOut,
    LatestOut,
    ReadingOut,
    StationOut,
)

router = APIRouter(prefix="/api/v1", tags=["air quality"])
health_router = APIRouter(tags=["health"])


def _to_reading_out(r: Reading) -> ReadingOut:
    """Fill in a derived AQI when the upstream feed left it null."""
    aqi = r.us_aqi if r.us_aqi is not None else aqi_from_pm25(r.pm2_5)
    return ReadingOut(
        observed_at=r.observed_at,
        pm2_5=r.pm2_5,
        pm10=r.pm10,
        us_aqi=aqi,
        nitrogen_dioxide=r.nitrogen_dioxide,
        ozone=r.ozone,
        band=band_key_for(aqi),
    )


def _age_minutes(when: datetime | None) -> int | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return int((datetime.now(UTC) - when).total_seconds() // 60)


@router.get("/stations", response_model=list[StationOut])
def list_stations(session: Session = Depends(get_session)) -> list[Station]:
    stmt = select(Station).where(Station.active.is_(True)).order_by(Station.name)
    return list(session.scalars(stmt))


@router.get("/latest", response_model=list[LatestOut])
def latest_everywhere(session: Session = Depends(get_session)) -> list[LatestOut]:
    """Newest reading for every active station -- the valley at a glance.

    DISTINCT ON is a Postgres extension. The portable alternative is a window
    function or a correlated subquery; this is faster and reads better, at the
    cost of tying us to Postgres. That trade is fine here -- we are tied to
    Postgres anyway.
    """
    rows = (
        session.execute(
            text(
                """
            SELECT DISTINCT ON (r.station_id) r.*
            FROM readings r
            JOIN stations s ON s.id = r.station_id
            WHERE s.active
            ORDER BY r.station_id, r.observed_at DESC
            """
            )
        )
        .mappings()
        .all()
    )

    by_station = {row["station_id"]: row for row in rows}
    stations = session.scalars(
        select(Station).where(Station.active.is_(True)).order_by(Station.name)
    )

    out: list[LatestOut] = []
    for station in stations:
        row = by_station.get(station.id)
        if row is None:
            out.append(LatestOut(station=StationOut.model_validate(station), reading=None))
            continue

        aqi = row["us_aqi"] if row["us_aqi"] is not None else aqi_from_pm25(row["pm2_5"])
        band = band_for(aqi)
        out.append(
            LatestOut(
                station=StationOut.model_validate(station),
                reading=ReadingOut(
                    observed_at=row["observed_at"],
                    pm2_5=row["pm2_5"],
                    pm10=row["pm10"],
                    us_aqi=aqi,
                    nitrogen_dioxide=row["nitrogen_dioxide"],
                    ozone=row["ozone"],
                    band=band.key if band else None,
                ),
                band_label=band.label if band else None,
                advice=band.advice if band else None,
                age_minutes=_age_minutes(row["observed_at"]),
            )
        )
    return out


@router.get("/worst", response_model=LatestOut)
def worst_station(session: Session = Depends(get_session)) -> LatestOut:
    """The valley's worst station right now -- highest US AQI.

    Instead of forcing the frontend to download all stations and sort them client-side,
    this endpoint answers 'who has it worst right now?' in a single lightweight query.
    """
    all_latest = latest_everywhere(session=session)
    if not all_latest:
        raise HTTPException(status_code=404, detail="No active stations found")

    readings_with_aqi = [
        item for item in all_latest if item.reading is not None and item.reading.us_aqi is not None
    ]
    if readings_with_aqi:
        return max(readings_with_aqi, key=lambda x: x.reading.us_aqi)  # type: ignore[union-attr]

    return all_latest[0]


@router.get("/stations/{slug}/readings", response_model=list[ReadingOut])
def station_readings(
    slug: str,
    hours: int = Query(24, ge=1, le=720, description="Look-back window in hours."),
    limit: int = Query(
        168,
        ge=1,
        le=720,
        description="Maximum readings to return (default 168 = 7 days). Caps JSON response size.",
    ),
    offset: int = Query(0, ge=0, description="Number of readings to skip for pagination."),
    session: Session = Depends(get_session),
) -> list[ReadingOut]:
    station = session.scalar(select(Station).where(Station.slug == slug))
    if station is None:
        raise HTTPException(status_code=404, detail=f"No station with slug '{slug}'")

    since = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(Reading)
        .where(Reading.station_id == station.id, Reading.observed_at >= since)
        .order_by(Reading.observed_at)
        .offset(offset)
        .limit(limit)
    )
    return [_to_reading_out(r) for r in session.scalars(stmt)]


@router.get("/stations/{slug}/summary", response_model=list[DailySummaryOut])
def station_summary(
    slug: str,
    days: int = Query(7, ge=1, le=90),
    session: Session = Depends(get_session),
) -> list[DailySummaryOut]:
    """Daily rollup, in Nepal local time.

    Note what is aggregated: **concentrations, not AQI values.** AQI is a
    piecewise-linear transform of concentration, so the average of AQI values
    is not the AQI of the average -- the two disagree by up to ~15 points
    across a band boundary. The EPA computes a daily AQI from the daily mean
    concentration, so that is what we do: average PM2.5 in SQL, then convert
    once in Python.

    This is also the expensive query in the app: it scans a date range and
    aggregates. If this service ever needs a cache, this endpoint is where it
    goes.
    """
    station = session.scalar(select(Station).where(Station.slug == slug))
    if station is None:
        raise HTTPException(status_code=404, detail=f"No station with slug '{slug}'")

    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        session.execute(
            text(
                """
            SELECT date_trunc('day', observed_at AT TIME ZONE 'Asia/Kathmandu') AS day,
                   AVG(pm2_5)  AS avg_pm2_5,
                   MAX(pm2_5)  AS max_pm2_5,
                   MIN(pm2_5)  AS min_pm2_5,
                   COUNT(*)    AS hours_recorded
            FROM readings
            WHERE station_id = :sid AND observed_at >= :since
            GROUP BY 1
            ORDER BY 1
            """
            ),
            {"sid": station.id, "since": since},
        )
        .mappings()
        .all()
    )

    out = []
    for row in rows:
        avg_pm = float(row["avg_pm2_5"]) if row["avg_pm2_5"] is not None else None
        max_pm = float(row["max_pm2_5"]) if row["max_pm2_5"] is not None else None
        min_pm = float(row["min_pm2_5"]) if row["min_pm2_5"] is not None else None

        avg_aqi = aqi_from_pm25(avg_pm)
        out.append(
            DailySummaryOut(
                day=row["day"].strftime("%Y-%m-%d"),
                avg_aqi=avg_aqi,
                max_aqi=aqi_from_pm25(max_pm),
                min_aqi=aqi_from_pm25(min_pm),
                avg_pm2_5=round(avg_pm, 1) if avg_pm is not None else None,
                hours_recorded=row["hours_recorded"],
                band=band_key_for(avg_aqi),
            )
        )
    return out


@router.get("/ingest/status", response_model=IngestStatusOut)
def ingest_status(session: Session = Depends(get_session)) -> IngestStatusOut:
    """Is the pipeline actually alive?

    The frontend shows this as a banner. Without it a stuck poller looks
    identical to clean air, which is the single most dangerous failure mode
    this system has.
    """
    last_run = session.scalar(select(PollRun).order_by(PollRun.started_at.desc()).limit(1))
    last_ok = session.scalar(
        select(PollRun).where(PollRun.status == "ok").order_by(PollRun.started_at.desc()).limit(1)
    )
    newest = session.scalar(select(func.max(Reading.observed_at)))
    total = session.scalar(select(func.count()).select_from(Reading)) or 0

    age = _age_minutes(newest)
    return IngestStatusOut(
        last_run_at=last_run.started_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
        last_success_at=last_ok.finished_at if last_ok else None,
        rows_inserted_last_run=last_run.rows_inserted if last_run else None,
        newest_reading_at=newest,
        data_age_minutes=age,
        stale=age is None or age > settings.staleness_threshold_minutes,
        total_readings=total,
    )


@health_router.get("/healthz", response_model=HealthOut)
def healthz() -> HealthOut:
    """Liveness: is the process itself wedged?

    Touches nothing external on purpose. If this checked the database, a
    Postgres blip would make Kubernetes kill every healthy API pod at once --
    turning a degraded system into an outage.
    """
    return HealthOut(status="alive")


@health_router.get("/readyz", response_model=HealthOut)
def readyz(session: Session = Depends(get_session)) -> HealthOut:
    """Readiness: should this pod receive traffic right now?

    Checks the dependency it cannot serve without. Returns 503 when the
    database is unreachable, so the Service takes this pod out of rotation
    instead of returning errors to users.
    """
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - we want the reason in the body
        raise HTTPException(
            status_code=503, detail={"status": "not ready", "database": str(exc)[:200]}
        ) from exc
    return HealthOut(status="ready", checks={"database": "ok"})


def refresh_gauges() -> None:
    """Pull current values into the Prometheus gauges at scrape time."""
    from app.db import SessionLocal

    with SessionLocal() as session:
        newest = session.scalar(select(func.max(Reading.observed_at)))
        total = session.scalar(select(func.count()).select_from(Reading)) or 0
        if newest is not None:
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=UTC)
            DATA_AGE.set((datetime.now(UTC) - newest).total_seconds())
        READINGS_TOTAL.set(total)
