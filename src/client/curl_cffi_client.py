import logging
from typing import Optional

from curl_cffi.requests import AsyncSession

from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# A realistic Chrome UA to fall back to when none is provided.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Full browser-like header set that defeats most header-inspection checks.
_BASE_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
}


class CurlCffiClient:
    """
    HTTP client backed by curl_cffi.
    Impersonates Chrome's TLS + HTTP/2 fingerprint, which defeats
    Cloudflare and similar WAF bot-detection at the transport layer.
    """

    async def fetch(
        self,
        url: str,
        *,
        timeout: Optional[float],
        user_agent: Optional[str],
        follow_redirects: bool,
    ) -> FetchResult:
        headers = {
            **_BASE_HEADERS,
            "User-Agent": user_agent or _DEFAULT_USER_AGENT,
        }

        async with AsyncSession() as session:
            response = await session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=follow_redirects,
                # impersonate Chrome's exact TLS + HTTP/2 fingerprint
                impersonate="chrome124",
            )

        logger.info(
            "curl_cffi fetched %s -> status=%d final_url=%s",
            url,
            response.status_code,
            response.url,
        )

        return FetchResult(
            html=response.text,
            status_code=response.status_code,
            final_url=str(response.url),
            strategy=FetchStrategy.CURL_CFFI,
        )
