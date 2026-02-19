"""NWS CLI (Daily Climate Report) text parser.

Parses the plain-text CLI product published by NWS weather forecast offices.
The CLI contains the official observed high/low temperatures used by Kalshi
for weather market settlement.

CLI product URL pattern:
    https://forecast.weather.gov/product.php?
        site={office}&issuedby={station}&product=CLI&format=txt

The key section we parse:

    TEMPERATURE (F)
                           YESTERDAY     RECORD
      MAXIMUM                 54          72 (1999)
      MINIMUM                 38          11 (1967)

"MAXIMUM" under "YESTERDAY" is the settlement temperature.

This module is PURE — no I/O, no DB, no external dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from backend.weather.exceptions import ParseError


@dataclass(frozen=True)
class CLIReport:
    """Parsed NWS CLI report data.

    Attributes:
        high_f: Yesterday's maximum temperature in Fahrenheit (settlement value).
        low_f: Yesterday's minimum temperature in Fahrenheit, or None if missing.
        station: NWS station identifier from the report header (e.g., "KNYC").
        report_date: The date the report covers (yesterday's date).
        raw_text: Full CLI text for archival storage.
    """

    high_f: float
    low_f: float | None
    station: str
    report_date: date
    raw_text: str


def parse_cli_text(text: str) -> CLIReport:
    """Parse an NWS CLI report and extract settlement-relevant data.

    Extracts the MAXIMUM (high) and MINIMUM (low) temperatures from the
    TEMPERATURE section, along with the station identifier and report date
    from the header.

    Args:
        text: Raw CLI report text (the full product text).

    Returns:
        CLIReport with parsed fields.

    Raises:
        ParseError: If the text cannot be parsed — missing temperature section,
            missing data ("M"), or unparseable format.
    """
    if not text or not text.strip():
        raise ParseError("Empty CLI report text")

    station = _extract_station(text)
    report_date = _extract_report_date(text)
    high_f = _extract_temperature(text, "MAXIMUM")
    low_f = _extract_temperature(text, "MINIMUM", required=False)

    return CLIReport(
        high_f=high_f,
        low_f=low_f,
        station=station,
        report_date=report_date,
        raw_text=text,
    )


def _extract_station(text: str) -> str:
    """Extract the station identifier from the CLI report header.

    The CLI header typically contains a line like:
        CLIMATE REPORT FOR NEW YORK CENTRAL PARK (KNYC)
    or:
        CLIORD   CLIMATE REPORT FOR CHICAGO MIDWAY

    We look for the 4-character station ID in parentheses first,
    then fall back to the CLI product ID prefix (e.g., "CLINYC").

    Args:
        text: Full CLI text.

    Returns:
        Station identifier string (e.g., "KNYC").

    Raises:
        ParseError: If no station can be identified.
    """
    # Try parenthesized station ID first: (KNYC), (KMIA), etc.
    match = re.search(r"\(([A-Z]{4})\)", text)
    if match:
        return match.group(1)

    # Try the CLI product ID line: "CLINYC" or "CLIMIA"
    match = re.search(r"CLI([A-Z]{3,4})\b", text)
    if match:
        return f"K{match.group(1)}"

    # Try "CLIMATE REPORT FOR ... (station)" pattern more broadly
    match = re.search(r"CLIMATE REPORT FOR\s+[^(]+\((\w+)\)", text, re.IGNORECASE)
    if match:
        return match.group(1)

    raise ParseError("Could not extract station identifier from CLI report header")


def _extract_report_date(text: str) -> date:
    """Extract the report date from the CLI report header.

    The CLI header contains a date line like:
        CLIMATE REPORT FOR ...
        ...
        02/18/2026
    or:
        THE FOLLOWING IS THE CLIMATE REPORT FOR KNYC
        FOR YESTERDAY  02/18/2026

    We look for MM/DD/YYYY or MONTH DD YYYY patterns.

    Args:
        text: Full CLI text.

    Returns:
        The date the report covers.

    Raises:
        ParseError: If no date can be found or parsed.
    """
    # Try MM/DD/YYYY format first (most common in CLI)
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ParseError(f"Invalid date in CLI report: {match.group(0)}") from exc

    # Try "MONTH DD YYYY" format (e.g., "FEBRUARY 18 2026")
    month_names = {
        "JANUARY": 1,
        "FEBRUARY": 2,
        "MARCH": 3,
        "APRIL": 4,
        "MAY": 5,
        "JUNE": 6,
        "JULY": 7,
        "AUGUST": 8,
        "SEPTEMBER": 9,
        "OCTOBER": 10,
        "NOVEMBER": 11,
        "DECEMBER": 12,
    }
    pattern = r"(" + "|".join(month_names.keys()) + r")\s+(\d{1,2})\s+(\d{4})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        month_str = match.group(1).upper()
        day = int(match.group(2))
        year = int(match.group(3))
        try:
            return date(year, month_names[month_str], day)
        except ValueError as exc:
            raise ParseError(f"Invalid date in CLI report: {match.group(0)}") from exc

    raise ParseError("Could not extract report date from CLI report")


def _extract_temperature(text: str, field: str, *, required: bool = True) -> float | None:
    """Extract a temperature value from the TEMPERATURE section.

    Searches for the TEMPERATURE (F) section and then finds the specified
    field (MAXIMUM or MINIMUM) line. The first numeric value on that line
    is the "yesterday" observation.

    Handles:
        - Positive integers: "54"
        - Negative integers: "-5"
        - Missing data: "M" → raises ParseError if required, None otherwise
        - Record values on same line: "54  72 (1999)" → takes first value only

    Args:
        text: Full CLI text.
        field: The field to extract ("MAXIMUM" or "MINIMUM").
        required: If True, raise ParseError when value is missing.
            If False, return None for missing values.

    Returns:
        Temperature in Fahrenheit as a float, or None if not required and missing.

    Raises:
        ParseError: If the TEMPERATURE section or field is missing (when required),
            or if the value is "M" (missing data) and required is True.
    """
    # Find the TEMPERATURE section
    temp_match = re.search(
        r"TEMPERATURE\s*\(?F?\)?.*?\n(.*?)(?=\n\s*\n|\nPRECIPITATION|\nHEATING|\nCOOLING|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not temp_match:
        if required:
            raise ParseError(f"No TEMPERATURE section found in CLI report for {field}")
        return None

    temp_section = temp_match.group(1)

    # Find the field line (MAXIMUM or MINIMUM)
    field_match = re.search(
        rf"{field}\s+([-\dM]+)",
        temp_section,
        re.IGNORECASE,
    )
    if not field_match:
        if required:
            raise ParseError(f"No {field} value found in TEMPERATURE section")
        return None

    value_str = field_match.group(1).strip()

    # Handle missing data marker
    if value_str.upper() == "M":
        if required:
            raise ParseError(f"{field} temperature is missing (M) in CLI report")
        return None

    # Parse the numeric value
    try:
        return float(value_str)
    except ValueError as exc:
        raise ParseError(f"Could not parse {field} temperature value: {value_str!r}") from exc
