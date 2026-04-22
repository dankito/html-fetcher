"""
Live integration tests — hit real URLs over the network.

Run with:
    uv run pytest -m live -v

Skipped in normal CI runs (no -m live flag).
"""
import pytest
from pydantic import HttpUrl

from src.api.dto.fetch_dto import FetchRequest
from src.client.camoufox_html_fetcher import CamoufoxHtmlFetcher
from src.client.curl_cffi_html_fetcher import CurlCffiHtmlFetcher
from src.client.zendriver_html_fetcher import ZendriverHtmlFetcher
from src.service.fetch_service import FetchService
from src.model.fetch_result import FetchStrategy

# -----------------------------------------------------------------
# Sites that should pass curl_cffi (no Camoufox needed)
# -----------------------------------------------------------------
EASY_URLS = [
    "https://example.com",
    "https://httpbin.org/get",
]

# -----------------------------------------------------------------
# Sites protected by DataDome or similar — may need Camoufox
# -----------------------------------------------------------------
PROTECTED_URLS = [
    "https://www.reisereporter.de/reiseziele/europa/deutschland/bayern/geheimtipps-fuer-bayern-diese-ausflugsziele-sind-nicht-ueberlaufen-YWCKDMYKDVI5LI7GGKVIY3DWRU.html",
]


@pytest.fixture(scope="module")
async def live_service():
    curl_client = CurlCffiHtmlFetcher()
    camoufox = CamoufoxHtmlFetcher()
    await camoufox.start(headless=True)
    zendriver = ZendriverHtmlFetcher()
    await zendriver.start()

    svc = FetchService(curl_client, camoufox, zendriver)
    yield svc

    await camoufox.stop()
    await zendriver.stop()


@pytest.mark.live
@pytest.mark.parametrize("url", EASY_URLS)
async def test_easy_url_succeeds_with_curl(url, live_service):
    result = await live_service.fetch(_request(url))

    assert result.status_code == 200
    assert len(result.html) > 100
    assert result.strategy == FetchStrategy.CURL_CFFI


@pytest.mark.live
@pytest.mark.parametrize("url", PROTECTED_URLS)
async def test_protected_url_returns_html(url, live_service):
    """
    The primary assertion is that we receive actual article HTML — not a
    bot-challenge page. We check for a meaningful content length and the
    absence of known DataDome / bot-wall markers.
    """
    result = await live_service.fetch(_request(url))

    assert result.status_code == 200, (
        f"Expected 200 but got {result.status_code}. "
        f"Strategy used: {result.strategy}. "
        f"HTML snippet: {result.html[:500]}"
    )
    assert len(result.html) > 5_000, "Response too short — likely a bot-wall page"

    html_lower = result.html.lower()
    assert "datadome" not in html_lower or "geheimtipp" in html_lower, (
        "Response looks like a DataDome challenge page"
    )
    assert "access denied" not in html_lower
    assert "blocked" not in html_lower[:2_000]


@pytest.mark.live
async def test_reisereporter_contains_article_content(live_service):
    """Spot-check that the actual article body is present in the fetched HTML."""
    url = PROTECTED_URLS[0]
    result = await live_service.fetch(_request(url))

    html_lower = result.html.lower()
    # The article is about Bavarian day-trip destinations — these words should appear.
    assert any(
        keyword in html_lower
        for keyword in ["bayern", "ausflug", "geheimtipp", "reise"]
    ), f"Expected article keywords not found. Strategy: {result.strategy}. Snippet: {result.html[:1000]}"


@pytest.mark.live
async def test_redirect_is_followed_and_final_url_captured(live_service):
    # http:// → https:// redirect
    result = await live_service.fetch(_request("http://example.com"))

    assert result.status_code == 200
    assert result.final_url.startswith("https://")


@pytest.mark.live
async def test_timeout_is_respected(live_service):
    """A very short timeout should raise rather than hang."""
    with pytest.raises(Exception):
        await live_service.fetch(_request("https://httpbin.org/delay/5", timeout=1.0))


def _request(url: str | HttpUrl, timeout: float = 15.0) -> FetchRequest:
    return FetchRequest(
        url=url if isinstance(url, HttpUrl) else HttpUrl(url),
        timeout=timeout,
    )