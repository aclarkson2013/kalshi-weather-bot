"""Tests for NWS CLI fetch and settlement record creation.

Tests cover:
- fetch_nws_cli: Fetches CLI text from NWS for a city
- build_cli_url: Builds correct URL for each city
- _fetch_cli_reports_async: Full pipeline — fetch → parse → Settlement record
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.weather.cli_parser import CLIReport
from backend.weather.exceptions import FetchError, ParseError
from backend.weather.nws import build_cli_url
from backend.weather.stations import STATION_CONFIGS

# ─── Sample CLI Text for Mocking ───

SAMPLE_CLI_NYC = """\
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
  WATER EQUIVALENT        0.00        1.23 (2004)

HEATING DEGREE DAYS
  YESTERDAY               19
"""


# ─── TestBuildCliUrl ───


class TestBuildCliUrl:
    """Test build_cli_url() — URL construction for CLI product."""

    def test_nyc_url_contains_correct_params(self) -> None:
        """NYC URL uses OKX office and KNYC station."""
        url = build_cli_url("NYC")
        assert "site=OKX" in url
        assert "issuedby=KNYC" in url
        assert "product=CLI" in url
        assert "format=txt" in url

    def test_chi_url_contains_correct_params(self) -> None:
        """CHI URL uses LOT office and KMDW station."""
        url = build_cli_url("CHI")
        assert "site=LOT" in url
        assert "issuedby=KMDW" in url

    def test_mia_url_contains_correct_params(self) -> None:
        """MIA URL uses MFL office and KMIA station."""
        url = build_cli_url("MIA")
        assert "site=MFL" in url
        assert "issuedby=KMIA" in url

    def test_aus_url_contains_correct_params(self) -> None:
        """AUS URL uses EWX office and KAUS station."""
        url = build_cli_url("AUS")
        assert "site=EWX" in url
        assert "issuedby=KAUS" in url

    def test_all_cities_have_valid_urls(self) -> None:
        """Every city in STATION_CONFIGS produces a valid CLI URL."""
        for city in STATION_CONFIGS:
            url = build_cli_url(city)
            assert url.startswith("https://forecast.weather.gov/product.php")

    def test_invalid_city_raises_key_error(self) -> None:
        """Unknown city code → KeyError."""
        with pytest.raises(KeyError):
            build_cli_url("INVALID")


# ─── TestFetchNwsCli ───


class TestFetchNwsCli:
    """Test fetch_nws_cli() — fetches CLI text from NWS."""

    @pytest.mark.asyncio
    async def test_returns_text_response(self) -> None:
        """Mock httpx returns text → function returns that text."""
        from backend.weather.nws import fetch_nws_cli

        with patch(
            "backend.weather.nws.fetch_text_with_retry",
            new_callable=AsyncMock,
            return_value=SAMPLE_CLI_NYC,
        ):
            result = await fetch_nws_cli("NYC")

        assert "TEMPERATURE" in result
        assert "MAXIMUM" in result

    @pytest.mark.asyncio
    async def test_passes_correct_url_to_fetcher(self) -> None:
        """The CLI URL built from STATION_CONFIGS is passed to fetch_text_with_retry."""
        from backend.weather.nws import fetch_nws_cli

        mock_fetch = AsyncMock(return_value=SAMPLE_CLI_NYC)
        with patch("backend.weather.nws.fetch_text_with_retry", mock_fetch):
            await fetch_nws_cli("NYC")

        call_url = mock_fetch.call_args[0][0]
        assert "site=OKX" in call_url
        assert "issuedby=KNYC" in call_url

    @pytest.mark.asyncio
    async def test_raises_fetch_error_on_failure(self) -> None:
        """FetchError propagates from fetch_text_with_retry."""
        from backend.weather.nws import fetch_nws_cli

        with (
            patch(
                "backend.weather.nws.fetch_text_with_retry",
                new_callable=AsyncMock,
                side_effect=FetchError("HTTP 500"),
            ),
            pytest.raises(FetchError, match="500"),
        ):
            await fetch_nws_cli("NYC")


# ─── TestFetchCliReportsAsync ───


def _make_mock_session(has_existing: bool = False) -> AsyncMock:
    """Create a mock async DB session for settlement tests.

    Args:
        has_existing: If True, simulate an existing Settlement record.
    """
    session = AsyncMock()
    session.add = MagicMock()

    # Mock the execute() for duplicate check
    mock_result = MagicMock()
    if has_existing:
        mock_result.scalar_one_or_none.return_value = MagicMock()  # existing record
    else:
        mock_result.scalar_one_or_none.return_value = None  # no duplicate
    session.execute.return_value = mock_result

    return session


class TestFetchCliReportsAsync:
    """Test _fetch_cli_reports_async — full CLI fetch → Settlement creation pipeline."""

    @pytest.mark.asyncio
    async def test_creates_settlement_record(self) -> None:
        """Valid CLI text → Settlement record added to DB and committed."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_session = _make_mock_session(has_existing=False)
        mock_report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text=SAMPLE_CLI_NYC,
        )

        with (
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                return_value=SAMPLE_CLI_NYC,
            ),
            patch(
                "backend.weather.scheduler.parse_cli_text",
                return_value=mock_report,
            ),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        # Settlement added for each city (4 cities)
        assert mock_session.add.call_count == 4
        assert mock_session.commit.await_count == 4

    @pytest.mark.asyncio
    async def test_skips_duplicate_settlement(self) -> None:
        """Same city+date already exists → no new record added."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_session = _make_mock_session(has_existing=True)
        mock_report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text=SAMPLE_CLI_NYC,
        )

        with (
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                return_value=SAMPLE_CLI_NYC,
            ),
            patch(
                "backend.weather.scheduler.parse_cli_text",
                return_value=mock_report,
            ),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        # No records added — all skipped as duplicates
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_parse_failure_gracefully(self) -> None:
        """Bad CLI text → ParseError caught, continues to next city."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        with (
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                return_value="GARBAGE TEXT",
            ),
            patch(
                "backend.weather.scheduler.parse_cli_text",
                side_effect=ParseError("No TEMPERATURE section"),
            ),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
            ),
        ):
            # Should NOT raise — error is caught per-city
            await _fetch_cli_reports_async()

    @pytest.mark.asyncio
    async def test_handles_fetch_failure_gracefully(self) -> None:
        """HTTP error → FetchError caught, continues to next city."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        with (
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                side_effect=FetchError("HTTP 503"),
            ),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
            ),
        ):
            # Should NOT raise
            await _fetch_cli_reports_async()

    @pytest.mark.asyncio
    async def test_processes_all_cities(self) -> None:
        """fetch_nws_cli is called once per city in VALID_CITIES."""
        from backend.weather.scheduler import _fetch_cli_reports_async
        from backend.weather.stations import VALID_CITIES

        mock_fetch = AsyncMock(return_value=SAMPLE_CLI_NYC)
        mock_report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text=SAMPLE_CLI_NYC,
        )

        with (
            patch("backend.weather.scheduler.fetch_nws_cli", mock_fetch),
            patch("backend.weather.scheduler.parse_cli_text", return_value=mock_report),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=_make_mock_session(has_existing=False),
            ),
        ):
            await _fetch_cli_reports_async()

        assert mock_fetch.call_count == len(VALID_CITIES)
        # Verify each city was called
        called_cities = [call.args[0] for call in mock_fetch.call_args_list]
        assert set(called_cities) == set(VALID_CITIES)

    @pytest.mark.asyncio
    async def test_settlement_has_correct_fields(self) -> None:
        """The Settlement ORM object has correct city, date, high_f, source."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_session = _make_mock_session(has_existing=False)
        mock_report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text="test text",
        )

        # Only process NYC by patching VALID_CITIES
        with (
            patch("backend.weather.scheduler.VALID_CITIES", ["NYC"]),
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                return_value=SAMPLE_CLI_NYC,
            ),
            patch("backend.weather.scheduler.parse_cli_text", return_value=mock_report),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        # Inspect the Settlement ORM object added to session
        mock_session.add.assert_called_once()
        settlement = mock_session.add.call_args[0][0]
        assert settlement.city.value == "NYC"
        assert settlement.actual_high_f == 54.0
        assert settlement.actual_low_f == 38.0
        assert settlement.source == "NWS_CLI"
        assert settlement.raw_data["station"] == "KNYC"

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self) -> None:
        """First city fetch fails, rest succeed → only successful cities get records."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_report = CLIReport(
            high_f=54.0,
            low_f=38.0,
            station="KNYC",
            report_date=date(2026, 2, 18),
            raw_text=SAMPLE_CLI_NYC,
        )

        # Fail for first call, succeed for rest
        mock_fetch = AsyncMock(
            side_effect=[
                FetchError("NYC down"),
                SAMPLE_CLI_NYC,
                SAMPLE_CLI_NYC,
                SAMPLE_CLI_NYC,
            ]
        )

        mock_session = _make_mock_session(has_existing=False)

        with (
            patch("backend.weather.scheduler.fetch_nws_cli", mock_fetch),
            patch("backend.weather.scheduler.parse_cli_text", return_value=mock_report),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        assert mock_fetch.call_count == 4
        # Only 3 cities created settlements (NYC failed)
        assert mock_session.add.call_count == 3


# ─── TestFetchTextWithRetry ───


class TestFetchTextWithRetry:
    """Test fetch_text_with_retry() — text variant of fetch_with_retry."""

    @pytest.mark.asyncio
    async def test_returns_text_on_success(self) -> None:
        """Successful HTTP request → returns response.text."""
        from backend.weather.nws import fetch_text_with_retry

        mock_response = MagicMock()
        mock_response.text = "CLI report text"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = mock_response

        with (
            patch("backend.weather.nws.httpx.AsyncClient", return_value=mock_client),
            patch("backend.weather.nws.nws_limiter.acquire", new_callable=AsyncMock),
        ):
            result = await fetch_text_with_retry("https://example.com/cli")

        assert result == "CLI report text"

    @pytest.mark.asyncio
    async def test_raises_fetch_error_after_retries(self) -> None:
        """All retries exhausted → FetchError raised."""
        import httpx as httpx_module

        from backend.weather.nws import fetch_text_with_retry

        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = httpx_module.HTTPStatusError(
            "Server Error", request=mock_request, response=mock_response
        )

        with (
            patch("backend.weather.nws.httpx.AsyncClient", return_value=mock_client),
            patch("backend.weather.nws.nws_limiter.acquire", new_callable=AsyncMock),
            patch("backend.weather.nws.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(FetchError),
        ):
            await fetch_text_with_retry("https://example.com/cli", max_retries=2)
