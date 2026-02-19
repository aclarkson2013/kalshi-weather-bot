"""Tests for backend.weather.cli_parser -- NWS CLI text parsing.

The CLI (Daily Climate Report) contains the official observed high temperature
used by Kalshi for weather market settlement. This module tests the parser
that extracts structured data from the plain-text CLI product.

Bracket label formats used in settlement:
    "53-54F"   -> standard bracket
    "<=52F"    -> bottom catch-all
    ">=57F"    -> top catch-all
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.weather.cli_parser import CLIReport, parse_cli_text
from backend.weather.exceptions import ParseError

# ─── Realistic CLI Report Text Fixtures ───

STANDARD_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY
300 AM EST THU FEB 19 2026

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 54          72 (1999)
  MINIMUM                 38          11 (1967)
  AVERAGE                 46          AVG: 37

PRECIPITATION (INCHES)
                       YESTERDAY     RECORD
  WATER EQUIVALENT        0.00        1.23 (2004)
  SNOW/ICE                0.0         8.2 (1979)

HEATING DEGREE DAYS
  YESTERDAY               19
  SEASON TOTAL           2847
"""

NEGATIVE_TEMP_CLI_TEXT = """\
000
SXUS71 KLOT 190800
CLICHI

CLIMATE REPORT
NATIONAL WEATHER SERVICE CHICAGO IL
200 AM CST THU FEB 19 2026

...CHICAGO MIDWAY (KMDW)...

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 -5          52 (2001)
  MINIMUM                -18          -11 (1958)
  AVERAGE                -12          AVG: 28

PRECIPITATION (INCHES)
  WATER EQUIVALENT        T           1.50 (1990)
"""

MISSING_HIGH_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 M           72 (1999)
  MINIMUM                 38          11 (1967)
"""

MISSING_LOW_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 54          72 (1999)
  MINIMUM                 M           11 (1967)
"""

NO_TEMP_SECTION_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

PRECIPITATION (INCHES)
  WATER EQUIVALENT        0.00        1.23 (2004)
"""

SINGLE_DIGIT_TEMP_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 9           42 (2003)
  MINIMUM                 2           -5 (1967)
"""

TRIPLE_DIGIT_TEMP_CLI_TEXT = """\
000
SXUS71 KEWX 190800
CLIAUS

CLIMATE REPORT
NATIONAL WEATHER SERVICE AUSTIN TX

...AUSTIN BERGSTROM (KAUS)...

              07/15/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                102          110 (1954)
  MINIMUM                 78          54 (1999)
"""

MONTH_NAME_DATE_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              FEBRUARY 18 2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 54          72 (1999)
  MINIMUM                 38          11 (1967)
"""

EXTRA_WHITESPACE_CLI_TEXT = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

...NEW YORK CENTRAL PARK (KNYC)...

              02/18/2026

TEMPERATURE  (F)
                       YESTERDAY     RECORD
  MAXIMUM                  54           72 (1999)
  MINIMUM                  38           11 (1967)
"""

CLI_WITHOUT_PARENTHESIZED_STATION = """\
000
SXUS71 KOKX 190800
CLINYC

CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK NY

              02/18/2026

TEMPERATURE (F)
                       YESTERDAY     RECORD
  MAXIMUM                 54          72 (1999)
  MINIMUM                 38          11 (1967)
"""


# ─── TestParseCliText ───


class TestParseCliText:
    """Test parse_cli_text() — the main parser entry point."""

    def test_parses_standard_report(self) -> None:
        """Standard CLI text → correct high and low temperatures."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.high_f == 54.0
        assert report.low_f == 38.0

    def test_parses_negative_temps(self) -> None:
        """Negative temperatures (e.g., -5°F) parsed correctly."""
        report = parse_cli_text(NEGATIVE_TEMP_CLI_TEXT)
        assert report.high_f == -5.0
        assert report.low_f == -18.0

    def test_parses_single_digit_temps(self) -> None:
        """Single digit temps (e.g., 9°F) parsed correctly."""
        report = parse_cli_text(SINGLE_DIGIT_TEMP_CLI_TEXT)
        assert report.high_f == 9.0
        assert report.low_f == 2.0

    def test_parses_triple_digit_temps(self) -> None:
        """Triple digit temps (e.g., 102°F) parsed correctly."""
        report = parse_cli_text(TRIPLE_DIGIT_TEMP_CLI_TEXT)
        assert report.high_f == 102.0
        assert report.low_f == 78.0

    def test_missing_temp_raises_error(self) -> None:
        """'M' in the MAXIMUM field → ParseError."""
        with pytest.raises(ParseError, match="missing"):
            parse_cli_text(MISSING_HIGH_CLI_TEXT)

    def test_missing_entire_section_raises_error(self) -> None:
        """No TEMPERATURE section at all → ParseError."""
        with pytest.raises(ParseError, match="TEMPERATURE"):
            parse_cli_text(NO_TEMP_SECTION_CLI_TEXT)

    def test_extracts_station_from_header(self) -> None:
        """Station ID (KNYC) extracted from parenthesized header."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.station == "KNYC"

    def test_extracts_report_date(self) -> None:
        """Date 02/18/2026 extracted correctly."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.report_date == date(2026, 2, 18)

    def test_handles_extra_whitespace(self) -> None:
        """Irregular spacing between columns still parses correctly."""
        report = parse_cli_text(EXTRA_WHITESPACE_CLI_TEXT)
        assert report.high_f == 54.0
        assert report.low_f == 38.0

    def test_handles_record_values_in_same_line(self) -> None:
        """Doesn't confuse record temp (72) with actual temp (54)."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.high_f == 54.0  # NOT 72 (the record)

    def test_low_temperature_extracted(self) -> None:
        """MINIMUM value correctly extracted alongside MAXIMUM."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.low_f == 38.0

    def test_empty_text_raises_error(self) -> None:
        """Empty string → ParseError."""
        with pytest.raises(ParseError, match="Empty"):
            parse_cli_text("")

    def test_whitespace_only_raises_error(self) -> None:
        """Whitespace-only string → ParseError."""
        with pytest.raises(ParseError, match="Empty"):
            parse_cli_text("   \n  \t  ")


# ─── TestCLIReport ───


class TestCLIReport:
    """Test the CLIReport dataclass."""

    def test_cli_report_fields_accessible(self) -> None:
        """All fields can be accessed on a CLIReport instance."""
        report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text="test",
        )
        assert report.high_f == 54.0
        assert report.low_f == 38.0
        assert report.station == "KNYC"
        assert report.report_date == date(2026, 2, 18)
        assert report.raw_text == "test"

    def test_cli_report_is_frozen(self) -> None:
        """CLIReport is immutable (frozen dataclass)."""
        report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text="test",
        )
        with pytest.raises(AttributeError):
            report.high_f = 99.0  # type: ignore[misc]


# ─── TestEdgeCases ───


class TestEdgeCases:
    """Test edge cases and unusual CLI formats."""

    def test_trace_precipitation_ignored(self) -> None:
        """'T' (trace) in precipitation section doesn't affect temp parsing."""
        report = parse_cli_text(NEGATIVE_TEMP_CLI_TEXT)
        # The PRECIPITATION section has 'T' but temps should still parse
        assert report.high_f == -5.0

    def test_report_with_missing_low(self) -> None:
        """High present but low is 'M' → low_f is None, no error."""
        report = parse_cli_text(MISSING_LOW_CLI_TEXT)
        assert report.high_f == 54.0
        assert report.low_f is None

    def test_month_name_date_format(self) -> None:
        """'FEBRUARY 18 2026' date format parsed correctly."""
        report = parse_cli_text(MONTH_NAME_DATE_CLI_TEXT)
        assert report.report_date == date(2026, 2, 18)

    def test_fallback_station_extraction(self) -> None:
        """When no (KNYC) present, falls back to CLI product ID."""
        report = parse_cli_text(CLI_WITHOUT_PARENTHESIZED_STATION)
        # Falls back to CLINYC → KNYC
        assert report.station == "KNYC"

    def test_raw_text_preserved(self) -> None:
        """Full CLI text is preserved in raw_text field."""
        report = parse_cli_text(STANDARD_CLI_TEXT)
        assert report.raw_text == STANDARD_CLI_TEXT

    def test_different_cities_parse(self) -> None:
        """CLI reports from different cities (CHI, AUS) parse correctly."""
        chi_report = parse_cli_text(NEGATIVE_TEMP_CLI_TEXT)
        assert chi_report.station == "KMDW"

        aus_report = parse_cli_text(TRIPLE_DIGIT_TEMP_CLI_TEXT)
        assert aus_report.station == "KAUS"
