"""US EPA Air Quality Index maths.

This module is the only place in the codebase with non-trivial domain logic,
which makes it the natural home for real unit tests.

Two things happen here:

1. `aqi_from_pm25` converts a raw PM2.5 concentration into an AQI value using
   the EPA's piecewise-linear breakpoint table. The upstream feed usually gives
   us `us_aqi` directly, but it is occasionally null -- when that happens we
   derive it ourselves rather than dropping the reading.

2. `band_for` classifies an AQI number into the six named categories. The
   frontend colours everything from this, so the definition lives server-side
   to keep one source of truth.

Breakpoints are the revised table the EPA adopted in 2024, which lowered the
Good/Moderate boundary from 12.0 to 9.0 ug/m3.
"""

from dataclasses import dataclass

# (concentration_low, concentration_high, aqi_low, aqi_high)
PM25_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]

BAND_ORDER = [
    "good",
    "moderate",
    "unhealthy_sensitive",
    "unhealthy",
    "very_unhealthy",
    "hazardous",
]


@dataclass(frozen=True)
class Band:
    key: str
    label: str
    advice: str
    lower: int
    upper: int


BANDS: list[Band] = [
    Band("good", "Good", "Air quality is fine. Go outside.", 0, 50),
    Band(
        "moderate",
        "Moderate",
        "Fine for most people. Unusually sensitive people may notice it.",
        51,
        100,
    ),
    Band(
        "unhealthy_sensitive",
        "Unhealthy for sensitive groups",
        "Children, older adults and people with asthma should limit long outdoor effort.",
        101,
        150,
    ),
    Band(
        "unhealthy",
        "Unhealthy",
        "Everyone should cut back on outdoor exertion. Wear a mask on the road.",
        151,
        200,
    ),
    Band(
        "very_unhealthy",
        "Very unhealthy",
        "Stay indoors where you can. Close windows and run a purifier if you have one.",
        201,
        300,
    ),
    Band("hazardous", "Hazardous", "Avoid all outdoor activity.", 301, 500),
]

_BAND_BY_KEY = {b.key: b for b in BANDS}


def aqi_from_pm25(pm25: float | None) -> int | None:
    """Convert a PM2.5 concentration (ug/m3) to a US AQI value.

    Returns None for missing input. Concentrations above the top of the table
    are clamped to 500, which is what the EPA's own reporting does.
    """
    if pm25 is None:
        return None
    if pm25 < 0:
        raise ValueError("PM2.5 concentration cannot be negative")

    # EPA truncates the concentration to one decimal place *before* the maths.
    # Skipping this is the classic off-by-a-little bug in AQI implementations.
    c = int(pm25 * 10) / 10

    for c_low, c_high, aqi_low, aqi_high in PM25_BREAKPOINTS:
        if c_low <= c <= c_high:
            slope = (aqi_high - aqi_low) / (c_high - c_low)
            return round(slope * (c - c_low) + aqi_low)

    return 500  # beyond the published table


def band_for(aqi: int | None) -> Band | None:
    """Classify an AQI value into its named category."""
    if aqi is None:
        return None
    if aqi < 0:
        raise ValueError("AQI cannot be negative")
    for band in BANDS:
        if band.lower <= aqi <= band.upper:
            return band
    return _BAND_BY_KEY["hazardous"]


def band_key_for(aqi: int | None) -> str | None:
    band = band_for(aqi)
    return band.key if band else None
