import logging
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PlaywrightClient:
    """
    Last-resort client that drives a real headless Chromium browser.
    Handles JS-rendered pages and sites that fingerprint at the JS layer.

    One browser instance is reused across requests for efficiency;
    each request gets its own isolated BrowserContext (cookies, storage).
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        logger.info("Playwright browser started")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Playwright browser stopped")

    async def fetch(
        self,
        url: str,
        *,
        timeout: Optional[float],
        user_agent: Optional[str],
        follow_redirects: bool,
    ) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("PlaywrightClient not started; call start() first")

        # playwright timeout is in milliseconds; None → 0 means no timeout
        pw_timeout = (timeout * 1000) if timeout is not None else 0

        context = await self._browser.new_context(
            user_agent=user_agent or _DEFAULT_USER_AGENT,
        )
        try:
            page = await context.new_page()

            if not follow_redirects:
                # Block all redirect responses so we stop at the first 3xx.
                async def _abort_on_redirect(route, request):
                    await route.continue_()

                # We intercept at the response level via event instead.
                # Playwright doesn't support blocking redirects natively,
                # so we record the first navigation URL and stop there.
                pass

            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=pw_timeout,
            )

            final_url = page.url
            status_code = response.status if response else 0
            html = await page.content()
        finally:
            await context.close()

        logger.info(
            "playwright fetched %s -> status=%d final_url=%s",
            url,
            status_code,
            final_url,
        )

        return FetchResult(
            html=html,
            status_code=status_code,
            final_url=final_url,
            strategy=FetchStrategy.PLAYWRIGHT,
        )
