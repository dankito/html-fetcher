import logging

from curl_cffi.requests import AsyncSession

from src.api.dto.fetch_dto import FetchRequest
from src.client.html_fetcher import HtmlFetcher
from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# A realistic Chrome UA to fall back to when none is provided.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

# Full browser-like header set matching a real Chromium 147 request.
# Header order matters for fingerprinting — keep it consistent with Chrome's ordering.
_BASE_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Sec-Ch-Ua": '"Chromium";v="147", "Not.A/Brand";v="8"',
    "Sec-Ch-Ua-Arch": '"x86"',
    "Sec-Ch-Ua-Full-Version-List": '"Chromium";v="147.0.0.0", "Not.A/Brand";v="8.0.0.0"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Model": '""',
    "Sec-Ch-Ua-Platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",  # overridden per-request when Referer is set
    "Sec-Fetch-User": "?1",
    "Sec-Gpc": "1",
    "Upgrade-Insecure-Requests": "1",
}


class CurlCffiHtmlFetcher(HtmlFetcher):
    """
    HTTP client backed by curl_cffi.
    Impersonates Chrome's TLS + HTTP/2 fingerprint, which defeats
    Cloudflare and similar WAF bot-detection at the transport layer.
    """

    async def fetch(self, request: FetchRequest) -> FetchResult:
        headers = {
            **_BASE_HEADERS,
            "User-Agent": request.user_agent or _DEFAULT_USER_AGENT,
        }

        async with AsyncSession(impersonate="chrome131") as session:
            response = await session.get(
                request.url_str,
                headers=headers,
                timeout=request.timeout,
                allow_redirects=request.follow_redirects,
                cookies=request.cookies or {},
            )

        logger.info(
            "curl_cffi fetched %s -> status=%d final_url=%s",
            request.url_str,
            response.status_code,
            response.url,
        )

        return FetchResult(
            html=response.text,
            status_code=response.status_code,
            final_url=str(response.url),
            strategy=FetchStrategy.CURL_CFFI,
        )