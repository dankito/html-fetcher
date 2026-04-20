"""
Unit tests for FetchService — no network calls, everything mocked.
"""
import pytest
from unittest.mock import AsyncMock

from src.model.fetch_result import FetchStrategy
from tests.conftest import make_result

URL = "https://www.reisereporter.de/reiseziele/europa/deutschland/bayern/geheimtipps-fuer-bayern-diese-ausflugsziele-sind-nicht-ueberlaufen-YWCKDMYKDVI5LI7GGKVIY3DWRU.html"


class TestFetchServiceEscalation:
    async def test_returns_curl_result_on_200(self, service, mock_curl_client, mock_playwright_client):
        mock_curl_client.fetch = AsyncMock(return_value=make_result(status_code=200))

        result = await service.fetch(URL)

        assert result.strategy == FetchStrategy.CURL_CFFI
        mock_playwright_client.fetch.assert_not_called()

    @pytest.mark.parametrize("rejection_code", [401, 403, 407, 429])
    async def test_escalates_to_playwright_on_rejection_status(
        self, rejection_code, service, mock_curl_client, mock_playwright_client
    ):
        mock_curl_client.fetch = AsyncMock(
            return_value=make_result(status_code=rejection_code)
        )
        mock_playwright_client.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.PLAYWRIGHT)
        )

        result = await service.fetch(URL)

        assert result.strategy == FetchStrategy.PLAYWRIGHT
        mock_playwright_client.fetch.assert_called_once()

    async def test_escalates_to_playwright_on_curl_exception(
        self, service, mock_curl_client, mock_playwright_client
    ):
        mock_curl_client.fetch = AsyncMock(side_effect=ConnectionError("TLS failure"))
        mock_playwright_client.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.PLAYWRIGHT)
        )

        result = await service.fetch(URL)

        assert result.strategy == FetchStrategy.PLAYWRIGHT

    async def test_passes_parameters_through_to_curl(self, service, mock_curl_client):
        mock_curl_client.fetch = AsyncMock(return_value=make_result())

        await service.fetch(URL, timeout=10.0, user_agent="TestAgent/1.0", follow_redirects=False)

        mock_curl_client.fetch.assert_called_once_with(
            URL,
            timeout=10.0,
            user_agent="TestAgent/1.0",
            follow_redirects=False,
        )

    async def test_passes_parameters_through_to_playwright_on_escalation(
        self, service, mock_curl_client, mock_playwright_client
    ):
        mock_curl_client.fetch = AsyncMock(return_value=make_result(status_code=403))
        mock_playwright_client.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.PLAYWRIGHT)
        )

        await service.fetch(URL, timeout=5.0, user_agent="Bot/2.0", follow_redirects=True)

        mock_playwright_client.fetch.assert_called_once_with(
            URL,
            timeout=5.0,
            user_agent="Bot/2.0",
            follow_redirects=True,
        )

    async def test_html_content_is_returned(self, service, mock_curl_client):
        expected_html = "<html><body><h1>Geheimtipps Bayern</h1></body></html>"
        mock_curl_client.fetch = AsyncMock(return_value=make_result(html=expected_html))

        result = await service.fetch(URL)

        assert result.html == expected_html

    async def test_final_url_after_redirect_is_preserved(self, service, mock_curl_client):
        redirected_to = "https://www.reisereporter.de/canonical-url"
        mock_curl_client.fetch = AsyncMock(
            return_value=make_result(final_url=redirected_to)
        )

        result = await service.fetch(URL)

        assert result.final_url == redirected_to
