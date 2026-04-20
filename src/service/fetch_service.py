import logging
from typing import Optional

from src.client.curl_cffi_client import CurlCffiClient
from src.client.playwright_client import PlaywrightClient
from src.model.fetch_result import FetchResult

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the server actively rejected us —
# worth retrying with a stronger strategy.
_REJECTION_CODES = {403, 401, 407, 429}


class FetchService:
    """
    Implements a two-tier fetch strategy:

    1. curl_cffi  — fast, impersonates Chrome TLS/HTTP2 fingerprint.
                    Handles the vast majority of protected sites.
    2. Playwright — full headless browser; last resort for JS-rendered pages
                    or sites that fingerprint at the JS/browser layer.

    Playwright is only launched when curl_cffi gets a rejection status code
    or raises a network-level exception.
    """

    def __init__(
        self,
        curl_client: CurlCffiClient,
        playwright_client: PlaywrightClient,
    ) -> None:
        self._curl = curl_client
        self._playwright = playwright_client

    async def fetch(
        self,
        url: str,
        *,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
        follow_redirects: bool = True,
        cookies: Optional[dict[str, str]] = None,
    ) -> FetchResult:
        kwargs = dict(
            timeout=timeout,
            user_agent=user_agent,
            follow_redirects=follow_redirects,
            cookies=cookies,
        )

        # --- Tier 1: curl_cffi ---
        try:
            result = await self._curl.fetch(url, **kwargs)
            if result.status_code not in _REJECTION_CODES:
                return result
            logger.warning(
                "curl_cffi got rejection status %d for %s; escalating to Playwright",
                result.status_code,
                url,
            )
        except Exception as exc:
            logger.warning(
                "curl_cffi failed for %s (%s); escalating to Playwright",
                url,
                exc,
            )

        # --- Tier 2: Playwright ---
        return await self._playwright.fetch(url, **kwargs)