"""Unit tests for the AQI maths.

These are the tests worth talking about in a review: they encode the EPA
specification, they run in milliseconds, and they need no database, no network
and no fixtures. Every other test in this project is slower and less certain
than these.
"""

import pytest
from app.aqi import aqi_from_pm25, band_for, band_key_for


class TestAqiFromPm25:
    def test_none_in_none_out(self):
        assert aqi_from_pm25(None) is None

    def test_negative_concentration_is_rejected(self):
        with pytest.raises(ValueError):
            aqi_from_pm25(-1.0)

    @pytest.mark.parametrize(
        ("pm25", "expected"),
        [
            (0.0, 0),  # bottom of the scale
            (9.0, 50),  # top of Good -- the 2024 revised boundary
            (9.1, 51),  # first Moderate value
            (35.4, 100),  # top of Moderate
            (35.5, 101),  # first Unhealthy-for-sensitive-groups value
            (55.5, 151),
            (125.5, 201),
            (225.5, 301),
            (325.4, 500),  # top of the published table
        ],
    )
    def test_breakpoint_boundaries(self, pm25, expected):
        """Every boundary in the EPA table, checked exactly.

        Off-by-one at a boundary is the most common bug in AQI code and the
        least likely to be noticed in production, because the number still
        looks plausible.
        """
        assert aqi_from_pm25(pm25) == expected

    def test_concentration_is_truncated_not_rounded(self):
        """EPA truncates to one decimal before the calculation.

        35.49 must be treated as 35.4 (AQI 100, Moderate), not rounded up to
        35.5 (AQI 101, Unhealthy for sensitive groups). One digit changes the
        public health advice.
        """
        assert aqi_from_pm25(35.49) == 100
        assert aqi_from_pm25(35.5) == 101

    def test_above_table_clamps_to_500(self):
        assert aqi_from_pm25(900.0) == 500

    def test_midpoint_interpolates_linearly(self):
        # Halfway through the Good band by concentration is halfway by AQI.
        assert aqi_from_pm25(4.5) == 25


class TestBands:
    @pytest.mark.parametrize(
        ("aqi", "key"),
        [
            (0, "good"),
            (50, "good"),
            (51, "moderate"),
            (100, "moderate"),
            (101, "unhealthy_sensitive"),
            (150, "unhealthy_sensitive"),
            (151, "unhealthy"),
            (200, "unhealthy"),
            (201, "very_unhealthy"),
            (300, "very_unhealthy"),
            (301, "hazardous"),
        ],
    )
    def test_classification(self, aqi, key):
        assert band_key_for(aqi) == key

    def test_none_is_not_a_band(self):
        assert band_for(None) is None

    def test_above_500_still_hazardous(self):
        assert band_key_for(750) == "hazardous"

    def test_every_band_has_advice(self):
        """A band with no advice would render as a blank line in the UI."""
        for aqi in (25, 75, 125, 175, 250, 400):
            band = band_for(aqi)
            assert band is not None
            assert band.advice.strip()


def test_kathmandu_winter_morning_is_unhealthy():
    """A regression test written in domain language.

    A January morning in the valley routinely sits near 90 ug/m3. If a refactor
    ever makes that read as 'Moderate', this test says so in words a
    non-programmer can check.
    """
    aqi = aqi_from_pm25(90.0)
    assert band_key_for(aqi) == "unhealthy"
