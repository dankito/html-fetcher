"""
Unit tests for FetchService — no network calls, everything mocked.
"""

import pytest
from unittest.mock import AsyncMock
from pydantic import HttpUrl

from src.api.dto.fetch_dto import FetchRequest
from src.model.fetch_result import FetchStrategy
from tests.conftest import make_result

URL = HttpUrl(
    "https://www.reisereporter.de/reiseziele/europa/deutschland/bayern/geheimtipps-fuer-bayern-diese-ausflugsziele-sind-nicht-ueberlaufen-YWCKDMYKDVI5LI7GGKVIY3DWRU.html"
)


class TestFetchServiceEscalation:
    async def test_returns_curl_result_on_200(
        self, service, mock_curl_client, mock_camoufox_html_fetcher
    ):
        mock_curl_client.fetch = AsyncMock(return_value=make_result(status_code=200))
        request = FetchRequest(url=URL)

        result = await service.fetch(request)

        assert result.strategy == FetchStrategy.CURL_CFFI
        mock_camoufox_html_fetcher.fetch.assert_not_called()

    @pytest.mark.parametrize("rejection_code", [401, 403, 407, 429])
    async def test_escalates_to_camoufox_on_rejection_status(
        self, rejection_code, service, mock_curl_client, mock_camoufox_html_fetcher,):
        mock_curl_client.fetch = AsyncMock(
            return_value=make_result(status_code=rejection_code)
        )
        mock_camoufox_html_fetcher.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.CAMOUFOX)
        )
        request = FetchRequest(url=URL)

        result = await service.fetch(request)

        assert result.strategy == FetchStrategy.CAMOUFOX
        mock_camoufox_html_fetcher.fetch.assert_called_once_with(request)

    async def test_escalates_to_camoufox_on_curl_exception(
        self, service, mock_curl_client, mock_camoufox_html_fetcher
    ):
        mock_curl_client.fetch = AsyncMock(side_effect=ConnectionError("TLS failure"))
        mock_camoufox_html_fetcher.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.CAMOUFOX)
        )
        request = FetchRequest(url=URL)

        result = await service.fetch(request)

        assert result.strategy == FetchStrategy.CAMOUFOX

    async def test_passes_parameters_through_to_curl(self, service, mock_curl_client):
        mock_curl_client.fetch = AsyncMock(return_value=make_result())
        request = FetchRequest(
            url=URL, timeout=10.0, user_agent="TestAgent/1.0", follow_redirects=False
        )

        await service.fetch(request)

        mock_curl_client.fetch.assert_called_once_with(request)

    async def test_passes_parameters_through_to_camoufox_on_escalation(
        self, service, mock_curl_client, mock_camoufox_html_fetcher
    ):
        mock_curl_client.fetch = AsyncMock(return_value=make_result(status_code=403))
        mock_camoufox_html_fetcher.fetch = AsyncMock(
            return_value=make_result(status_code=200, strategy=FetchStrategy.CAMOUFOX)
        )
        request = FetchRequest(
            url=URL, timeout=5.0, user_agent="Bot/2.0", follow_redirects=True
        )

        await service.fetch(request)

        mock_camoufox_html_fetcher.fetch.assert_called_once_with(request)

    async def test_html_content_is_returned(self, service, mock_curl_client):
        expected_html = "<html><body><h1>Geheimtipps Bayern</h1></body></html>"
        mock_curl_client.fetch = AsyncMock(return_value=make_result(html=expected_html))
        request = FetchRequest(url=URL)

        result = await service.fetch(request)

        assert result.html == expected_html

    async def test_final_url_after_redirect_is_preserved(
        self, service, mock_curl_client
    ):
        redirected_to = "https://www.reisereporter.de/canonical-url"
        mock_curl_client.fetch = AsyncMock(
            return_value=make_result(final_url=redirected_to)
        )
        request = FetchRequest(url=URL)

        result = await service.fetch(request)

        assert result.final_url == redirected_to
