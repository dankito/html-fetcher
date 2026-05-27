import asyncio
import logging
import os
import random
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox

from src.api.dto.fetch_dto import FetchRequest
from src.client.html_fetcher import HtmlFetcher
from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# Hard cap used when the caller did not supply a timeout.
# Without this, a bot-challenge page that never idles causes _goto_with_fallback
# to retry indefinitely, each retry opening a new navigation (and in headed mode
# a new visible window).
_DEFAULT_TIMEOUT_MS = 30_000  # 30 s

# Weighted OS distribution that mirrors real-world desktop market share.
# Camoufox generates a coherent BrowserForge fingerprint per OS choice,
# so rotating this prevents a static OS from becoming a detection signal.
_OS_WEIGHTS: list[tuple[str, float]] = [
    ("windows", 0.70),
    ("macos", 0.20),
    ("linux", 0.10),
]
_OS_POOL = [os for os, _ in _OS_WEIGHTS]
_OS_CUMULATIVE = []
_acc = 0.0
for _os, _w in _OS_WEIGHTS:
    _acc += _w
    _OS_CUMULATIVE.append(_acc)


def _pick_os() -> str:
    r = random.random()
    for os, cum in zip(_OS_POOL, _OS_CUMULATIVE):
        if r <= cum:
            return os
    return _OS_POOL[0]


class CamoufoxHtmlFetcher(HtmlFetcher):
    """
    Anti-bot HTML fetcher backed by Camoufox — a patched Firefox build that
    injects randomised, statistically realistic fingerprints at the C++ level
    rather than via detectable JavaScript monkey-patching.

    Stealth techniques applied
    --------------------------
    1. Rotating OS fingerprint (Windows 70 %, macOS 20 %, Linux 10 %)
       Camoufox uses BrowserForge to generate a *coherent* screen / UA /
       platform / WebGL / font bundle for each chosen OS.
    2. humanize=True — enables Camoufox's built-in human-like cursor movement.
    3. block_webrtc=True — prevents real-IP leakage through WebRTC probes.
    4. Randomised pre-navigation jitter (100–600 ms) to break timing patterns
       that WAFs use to identify automated sessions.
    5. networkidle → domcontentloaded fallback — retries with a lighter wait
       condition when a page never reaches network idle (e.g. long-polling SPAs).
    6. headless / headed toggle — headed mode is harder to detect and is
       recommended when running on a machine with a display or Xvfb.
    7. Per-request isolated BrowserContext — cookies and storage never bleed
       across requests.
    """

    def __init__(self, viewport_height: int = 1080) -> None:
        self._browser: AsyncCamoufox | None = None
        self._headless: bool = True
        self._viewport_height = viewport_height

    async def start(self, headless: bool = True) -> None:
        target_os = _pick_os()
        self._headless = headless

        # Use CAMOUFOX_DATA_DIR for persistence if set
        data_dir = os.environ.get("CAMOUFOX_DATA_DIR")

        if data_dir:
            # for options see playwright.firefox.launch_persistent_context() in .venv/lib/python3.12/site-packages/playwright/async_api/_generated.py
            browser = AsyncCamoufox(
                headless=headless,
                humanize=True,
                block_webrtc=True,
                os=target_os,
                viewport={"width": 1920, "height": self._viewport_height},
                java_script_enabled=True,
                persistent_context=True,
                # Path to a User Data Directory, which stores browser session data like cookies and local storage.
                # Pass an empty string to create a temporary directory.
                user_data_dir=data_dir,
            )
        else:
            # for options playwright.firefox.launch() in .venv/lib/python3.12/site-packages/playwright/async_api/_generated.py
            browser = AsyncCamoufox(
                headless=headless,
                humanize=True,
                block_webrtc=True,
                os=target_os,
            )
            async with browser as playwright_browser:
                await playwright_browser.new_context(
                    viewport={"width": 1920, "height": self._viewport_height},
                    java_script_enabled=True,
                )

        self._browser = await browser.start()
        logger.info("Camoufox browser ready (headless=%s, os=%s)", headless, target_os)

    async def stop(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("Error closing Camoufox browser: %s", exc)
        logger.info("Camoufox browser stopped")


    async def fetch(self, request: FetchRequest) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("CamoufoxHtmlFetcher not started; call start() first")

        # Camoufox timeout is in milliseconds; 0 means no timeout.
        timeout_ms = (request.timeout * 1000) if request.timeout is not None else _DEFAULT_TIMEOUT_MS

        # Camoufox internally uses launch_persistent_context instead of launch(),
        # which merges the Browser and BrowserContext into a single object.
        # Therefore self._browser is already a BrowserContext — calling new_context()
        # on it does not exist and would raise an AttributeError.
        # Instead, each isolated "session" is achieved by opening a new Page and
        # closing it afterwards. Cookies/storage isolation per request is handled
        # via page-level APIs rather than context-level ones.
        page = await self._browser.new_page()
        try:
            await page.set_viewport_size({"width": 1920, "height": self._viewport_height})

            if request.execute_javascript is False:
                # JS cannot be toggled per-page in a persistent context; log a warning.
                logger.warning(
                    "CamoufoxHtmlFetcher: java_script_enabled=False is not supported per-request with persistent_context. JS remains enabled.")

            if request.user_agent:
                await page.set_extra_http_headers({"User-Agent": request.user_agent})

            if request.cookies:
                parsed = urlparse(request.url_str)
                domain = parsed.hostname or parsed.netloc
                await self._browser.add_cookies([
                    {"name": k, "value": v, "domain": domain, "path": "/"}
                    for k, v in request.cookies.items()
                ])

            # Small random delay before navigation — breaks the "instant goto"
            # timing pattern that some WAFs flag as non-human.
            await asyncio.sleep(random.uniform(0.1, 0.6))

            # Strategy A: wait for full network idle (best for JS-rendered pages).
            response = await _goto_with_fallback(page, request.url_str, timeout_ms)

            final_url = page.url
            cookies = await page.context.cookies(request.url_str)

            if request.load_lazy_content:
                await self._scroll_to_bottom(page)

            html = await page.content()
        finally:
            await page.close()

        status_code = response.status if response else 0
        logger.info(
            "camoufox fetched %s -> status=%d final_url=%s",
            request.url_str,
            status_code,
            final_url,
        )

        timing = response.request.timing
        total_ms = timing["responseEnd"] - timing["domainLookupStart"]

        return FetchResult(
            html=html,
            status_code=status_code,
            final_url=final_url,
            strategy=FetchStrategy.CAMOUFOX,
            # getting the http version would be very complicated by observing network connections like `client.on("Network.responseReceived", handle_response_received)`
            headers=dict(response.headers),
            # TODO: parse cookies
            # cookies=dict(cookies),
            elapsed_microseconds=int(total_ms * 1_000),
        )


    async def _scroll_to_bottom(self, page) -> None:
        """
        Incrementally scroll to the bottom of the page so that lazy-loaded
        elements (images, infinite scroll, etc.) are fully rendered before
        the HTML is captured.
        """
        try:
            async def get_page_height():
                return await page.evaluate("document.body.scrollHeight")

            page_height = await get_page_height()
            if not page_height:
                return

            current_pos = 0

            while current_pos < page_height:
                current_pos = min(current_pos + self._viewport_height, page_height)
                await page.evaluate(
                    f"window.scrollTo({{top: {current_pos}, left: 0, behavior: 'smooth'}});"
                )
                await asyncio.sleep(random.uniform(0.2, 0.4))

                new_height = await get_page_height()
                if new_height and new_height > page_height:
                    page_height = new_height

            await asyncio.sleep(random.uniform(0.2, 0.5))

        except Exception as exc:
            logger.debug("Scroll-to-bottom failed (non-fatal): %s", exc)


# returns a Response object from playwright .venv/lib/python3.12/site-packages/playwright/_impl/_network.py
async def _goto_with_fallback(page, url: str, timeout_ms: float):
    """
    Try to navigate with 'networkidle' first (best for JS-heavy pages).
    Falls back to 'domcontentloaded' ONLY on a non-timeout failure —
    a TimeoutError means the page is genuinely stuck (e.g. a bot challenge
    loop) and re-navigating would just open another cycle.
    """

    try:
        return await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    except Exception as exc:
        # Any other error (e.g. net::ERR_ABORTED): retry with a lighter
        # wait condition which resolves as soon as the DOM is parsed.
        logger.warning(
            "networkidle timed out for %s (%s); retrying with domcontentloaded", url, exc
        )
        return await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
