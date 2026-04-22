import logging

from src.api.dto.fetch_dto import FetchRequest
from src.client.camoufox_html_fetcher import CamoufoxHtmlFetcher
from src.client.curl_cffi_html_fetcher import CurlCffiHtmlFetcher
from src.client.html_fetcher import HtmlFetcher
from src.client.zendriver_html_fetcher import ZendriverHtmlFetcher
from src.model.app_config import AppConfig
from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the server actively rejected us —
# worth retrying with a stronger strategy.
_REJECTION_CODES = {403, 401, 407, 429}


class FetchService(HtmlFetcher):
    """
    Implements a two-tier fetch strategy:

    1. curl_cffi  — fast, impersonates Chrome TLS/HTTP2 fingerprint.
                    Handles the vast majority of protected sites.
    2. Camoufox   — Firefox-based stealth browser; last resort for JS-rendered pages
                    or sites that fingerprint at the JS/browser layer.

    Browser-based tiers are only launched when curl_cffi gets a rejection
    status code or raises a network-level exception.

    If request.strategies is provided and not empty, uses that custom order
    (e.g., [FetchStrategy.CAMOUFOX, FetchStrategy.CURL_CFFI]).
    Otherwise, uses the default order (curl_cffi, then camoufox).
    """

    @classmethod
    async def from_config(cls, config: AppConfig) -> "FetchService":
        curl = CurlCffiHtmlFetcher()
        camoufox = CamoufoxHtmlFetcher()
        await camoufox.start(headless=True)

        zendriver = None
        if config.use_zendriver:
            zendriver = ZendriverHtmlFetcher()
            await zendriver.start()
        else:
            logger.info("Zendriver disabled via USE_ZENDRIVER")

        return cls(curl, camoufox, zendriver)

    def __init__(
        self,
        curl_client: CurlCffiHtmlFetcher,
        camoufox_html_fetcher: CamoufoxHtmlFetcher,
        zendriver_html_fetcher: ZendriverHtmlFetcher | None = None,
    ) -> None:
        self._curl = curl_client
        self._camoufox = camoufox_html_fetcher
        self._zendriver = zendriver_html_fetcher

    async def stop(self) -> None:
        await self._camoufox.stop()
        if self._zendriver is not None:
            await self._zendriver.stop()


    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.strategies is None or len(request.strategies) == 0:
            return await self._fetch_with_default_strategy(request)
        else:
            return await self._fetch_with_custom_strategies_order(request, request.strategies)

    def _should_skip_curl_cffi(self, request: FetchRequest) -> bool:
        return request.execute_javascript is True

    async def _fetch_with_default_strategy(self, request: FetchRequest) -> FetchResult:
        # --- Tier 1: curl_cffi (if executing JavaScript is not required) ---
        if not self._should_skip_curl_cffi(request):
            try:
                result = await self._curl.fetch(request)
                if result.status_code not in _REJECTION_CODES:
                    return result

                logger.warning("curl_cffi got rejection status %d for %s; escalating to Camoufox", result.status_code, request.url_str)
            except Exception as exc:
                logger.warning("curl_cffi failed for %s (%s); escalating to Camoufox", request.url_str, exc)

        # --- Tier 2: Camoufox ---
        try:
            result = await self._camoufox.fetch(request)
            if result.status_code not in _REJECTION_CODES:
                return result

            logger.warning("Camoufox got rejection status %d for %s; escalating to Zendriver", result.status_code, request.url_str)
        except Exception as exc:
            logger.warning("Camoufox failed for %s (%s); escalating to Zendriver", request.url_str, exc)

        # --- Tier 3: Zendriver (if enabled) ---
        if self._zendriver is None:
            raise ValueError("Camoufox failed and Zendriver is disabled")

        return await self._zendriver.fetch(request)

    async def _fetch_with_custom_strategies_order(self, request: FetchRequest, strategies: list[FetchStrategy]) -> FetchResult:
        for strategy in strategies:
            try:
                if strategy == FetchStrategy.CURL_CFFI:
                    if self._should_skip_curl_cffi(request):
                        logger.warning("Skipping curl_cffi because execute_javascript=True")
                        continue
                    result = await self._curl.fetch(request)
                elif strategy == FetchStrategy.CAMOUFOX:
                    result = await self._camoufox.fetch(request)
                elif strategy == FetchStrategy.ZENDRIVER:
                    if self._zendriver is None:
                        logger.warning("Zendriver requested but disabled, skipping")
                        continue
                    result = await self._zendriver.fetch(request)
                else:
                    continue

                if result.status_code not in _REJECTION_CODES:
                    return result

                logger.warning(
                    "%s got rejection status %d for %s; escalating to next strategy",
                    strategy.value,
                    result.status_code,
                    request.url_str,
                )
            except Exception as exc:
                logger.exception(
                    "%s failed for %s (%s); escalating to next strategy",
                    strategy.value,
                    request.url_str,
                    exc,
                )

        raise ValueError("All fetch strategies failed")
