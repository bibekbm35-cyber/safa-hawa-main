"""Pydantic response models -- the API's public contract."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    district: str
    latitude: float
    longitude: float
    elevation_m: int | None = None


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observed_at: datetime
    pm2_5: float | None = None
    pm10: float | None = None
    us_aqi: int | None = None
    nitrogen_dioxide: float | None = None
    ozone: float | None = None
    band: str | None = Field(None, description="AQI category key, e.g. 'moderate'")


class LatestOut(BaseModel):
    station: StationOut
    reading: ReadingOut | None
    band_label: str | None = None
    advice: str | None = None
    age_minutes: int | None = Field(
        None, description="How old this reading is. The UI warns above 180."
    )


class DailySummaryOut(BaseModel):
    day: str
    avg_aqi: int | None
    max_aqi: int | None
    min_aqi: int | None
    avg_pm2_5: float | None
    hours_recorded: int
    band: str | None = None


class IngestStatusOut(BaseModel):
    last_run_at: datetime | None
    last_run_status: str | None
    last_success_at: datetime | None
    rows_inserted_last_run: int | None
    newest_reading_at: datetime | None
    data_age_minutes: int | None
    stale: bool
    total_readings: int


class HealthOut(BaseModel):
    status: str
    checks: dict[str, str] = {}
