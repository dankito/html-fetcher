import pytest
from unittest.mock import AsyncMock, MagicMock
from src.client.camoufox_html_fetcher import CamoufoxHtmlFetcher
from src.client.curl_cffi_html_fetcher import CurlCffiHtmlFetcher
from src.client.zendriver_html_fetcher import ZendriverHtmlFetcher
from src.service.fetch_service import FetchService
from src.model.fetch_result import FetchResult, FetchStrategy


@pytest.fixture
def mock_curl_client() -> CurlCffiHtmlFetcher:
    return MagicMock(spec=CurlCffiHtmlFetcher)

@pytest.fixture
def mock_camoufox_html_fetcher() -> CamoufoxHtmlFetcher:
    return MagicMock(spec=CamoufoxHtmlFetcher)

@pytest.fixture
def mock_zendriver_html_fetcher() -> ZendriverHtmlFetcher:
    return MagicMock(spec=ZendriverHtmlFetcher)


@pytest.fixture
def service(
    mock_curl_client, mock_camoufox_html_fetcher, mock_zendriver_html_fetcher
) -> FetchService:
    return FetchService(mock_curl_client, mock_camoufox_html_fetcher, mock_zendriver_html_fetcher)


def make_result(
    html: str = "<html><body>OK</body></html>",
    status_code: int = 200,
    final_url: str = "https://example.com",
    strategy: FetchStrategy = FetchStrategy.CURL_CFFI,
) -> FetchResult:
    return FetchResult(
        html=html,
        status_code=status_code,
        final_url=final_url,
        strategy=strategy,
    )
