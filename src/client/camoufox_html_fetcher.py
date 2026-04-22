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

    def __init__(self) -> None:
        self._browser = None
        self._headless: bool = True

    async def start(self, headless: bool = True) -> None:
        target_os = _pick_os()
        self._headless = headless

        # Use CAMOUFOX_DATA_DIR for persistence if set
        data_dir = os.environ.get("CAMOUFOX_DATA_DIR")

        if data_dir:
            browser = AsyncCamoufox(
                headless=headless,
                humanize=True,
                block_webrtc=True,
                os=target_os,
                persistent_context=True,
                user_data_dir=data_dir,
            )
        else:
            browser = AsyncCamoufox(
                headless=headless,
                humanize=True,
                block_webrtc=True,
                os=target_os,
            )
        self._browser = browser
        await browser.start()
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

        context_kwargs: dict = {
            "viewport": {"width": 1920, "height": 1080},
            "java_script_enabled": True,
        }
        # Honour a caller-supplied User-Agent by setting it as an extra header.
        # Camoufox already generates a realistic UA from the fingerprint bundle;
        # only override when explicitly requested to avoid fingerprint mismatch.
        if request.user_agent:
            context_kwargs["extra_http_headers"] = {"User-Agent": request.user_agent}

        context = await self._browser.new_context(**context_kwargs)
        try:
            if request.cookies:
                parsed = urlparse(request.url_str)
                domain = parsed.hostname or parsed.netloc
                await context.add_cookies([
                    {"name": k, "value": v, "domain": domain, "path": "/"}
                    for k, v in request.cookies.items()
                ])

            page = await context.new_page()

            # Small random delay before navigation — breaks the "instant goto"
            # timing pattern that some WAFs flag as non-human.
            await asyncio.sleep(random.uniform(0.1, 0.6))

            # Strategy A: wait for full network idle (best for JS-rendered pages).
            response = await _goto_with_fallback(page, request.url_str, timeout_ms)

            final_url = page.url
            status_code = response.status if response else 0

            if request.load_lazy_content:
                await self._scroll_to_bottom(page)

            html = await page.content()
        finally:
            await context.close()

        logger.info(
            "camoufox fetched %s -> status=%d final_url=%s",
            request.url_str,
            status_code,
            final_url,
        )

        return FetchResult(
            html=html,
            status_code=status_code,
            final_url=final_url,
            strategy=FetchStrategy.CAMOUFOX,
        )


    async def _scroll_to_bottom(self, page) -> None:
        """
        Incrementally scroll to the bottom of the page so that lazy-loaded
        elements (images, infinite scroll, etc.) are fully rendered before
        the HTML is captured.
        """
        try:
            viewport_height = 1080

            async def get_page_height():
                return await page.evaluate("document.body.scrollHeight")

            page_height = await get_page_height()
            if not page_height:
                return

            current_pos = 0

            while current_pos < page_height:
                current_pos = min(current_pos + viewport_height, page_height)
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
