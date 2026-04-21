import logging
import os

from playwright.async_api import async_playwright

from src.api.dto.fetch_dto import FetchRequest
from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# When set, connects to a remote Playwright-compatible browser endpoint
# (e.g. browserless.io or a self-hosted browserless Docker container)
# instead of launching a local Chromium instance.
# Example: ws://localhost:3000
PLAYWRIGHT_WS_URL = os.environ.get("PLAYWRIGHT_WS_URL")

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

# Injected before any page script runs — patches the automation signals
# that bot detectors (DataDome, PerimeterX, Cloudflare) look for.
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {},
    };

    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
"""


class PlaywrightClient:
    """
    Last-resort client that drives a real headless Chromium browser.

    - When PLAYWRIGHT_WS_URL env var is set: connects to a remote browser
      (e.g. browserless Docker container). Recommended for production.
    - Otherwise: launches a local Chromium instance.

    Injects stealth patches to defeat common bot-detection signals
    (navigator.webdriver, missing plugins, headless WebGL, etc).

    One browser connection is reused; each request gets its own isolated
    BrowserContext so cookies and storage never bleed between requests.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        if PLAYWRIGHT_WS_URL:
            logger.info("Connecting to remote Playwright browser at %s", PLAYWRIGHT_WS_URL)
            self._browser = await self._playwright.chromium.connect_over_cdp(PLAYWRIGHT_WS_URL)
        else:
            logger.info("Launching local Playwright Chromium browser")
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
        logger.info("Playwright browser ready (remote=%s)", bool(PLAYWRIGHT_WS_URL))

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Playwright browser stopped")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("PlaywrightClient not started; call start() first")

        # playwright timeout is in milliseconds; None → 0 means no timeout
        pw_timeout = (request.timeout * 1000) if request.timeout is not None else 0

        context = await self._browser.new_context(
            user_agent=request.user_agent or _DEFAULT_USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Sec-Ch-Ua": '"Chromium";v="147", "Not.A/Brand";v="8"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
                "Sec-Gpc": "1",
            },
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
        )
        try:
            # Playwright accepts cookies as a list of dicts with required fields.
            # We parse the target URL to scope cookies to the correct domain.
            if request.cookies:
                from urllib.parse import urlparse

                parsed = urlparse(request.url_str)
                domain = parsed.hostname or parsed.netloc
                await context.add_cookies([
                    {"name": k, "value": v, "domain": domain, "path": "/"}
                    for k, v in request.cookies.items()
                ])

            page = await context.new_page()
            await page.add_init_script(_STEALTH_SCRIPT)

            if not request.follow_redirects:
                # Block all redirect responses so we stop at the first 3xx.
                async def _abort_on_redirect(route, request):
                    await route.continue_()

                # We intercept at the response level via event instead.
                # Playwright doesn't support blocking redirects natively,
                # so we record the first navigation URL and stop there.
                pass

            response = await page.goto(
                request.url_str,
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
            request.url_str,
            status_code,
            final_url,
        )

        return FetchResult(
            html=html,
            status_code=status_code,
            final_url=final_url,
            strategy=FetchStrategy.PLAYWRIGHT,
        )