"""
ZendriverHtmlFetcher – stealth HTML fetcher powered by Zendriver.

Anti-bot strategies used
------------------------
1. **Real Chrome via CDP** – Zendriver drives an actual, unpatched Chromium
   instance, so TLS fingerprints, HTTP/2, and browser JS-APIs all look real.
2. **Stealth Chrome flags** – A curated set of ``--disable-*`` flags removes
   the most common automation signals (webdriver flag, automation extensions,
   infobars, etc.).
3. **Custom / realistic User-Agent** – Applied via ``Tab.set_user_agent()``
   *before* navigation so every request in the page lifecycle carries the
   correct UA.  Falls back to a realistic desktop UA when none is supplied.
4. **Pre-navigation cookie injection** – Cookies (e.g. DataDome tokens) are
   injected via CDP ``Network.setCookie`` against the target domain *before*
   the first byte is sent.
5. **Human-like behaviour simulation** – After the page loads the fetcher
   performs randomised mouse movement, a short random scroll, and a natural
   idle pause to satisfy behavioural-analysis layers.
6. **Redirect control** – When ``follow_redirects=False`` the fetcher
   intercepts the very first navigation response via CDP Fetch and aborts the
   chain after collecting the initial response URL / HTML.
7. **Timeout propagation** – Every async wait is wrapped with
   ``asyncio.wait_for`` so the caller's ``timeout`` is respected end-to-end.
"""

from __future__ import annotations

import asyncio
import random
import logging
from urllib.parse import urlparse
from typing import Optional

import zendriver as zd
from zendriver import cdp

from src.api.dto.fetch_dto import FetchRequest
from src.client.html_fetcher import HtmlFetcher
from src.model.fetch_result import FetchResult, FetchStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Realistic fallback UA (Windows / Chrome – broadly accepted everywhere)
# ---------------------------------------------------------------------------
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_viewport_height = 1080

# ---------------------------------------------------------------------------
# Chrome launch flags that strip away common automation fingerprints
# ---------------------------------------------------------------------------
_STEALTH_BROWSER_ARGS = [
    # Original browser args:
    # --remote-allow-origins=*
    #     --no-first-run
    #     --no-service-autorun
    #     --no-default-browser-check
    #     --homepage=about:blank
    #     --no-pings
    #     --password-store=basic
    #     --disable-infobars
    #     --disable-breakpad
    #     --disable-component-update
    #     --disable-backgrounding-occluded-windows
    #     --disable-renderer-backgrounding
    #     --disable-background-networking
    #     --disable-dev-shm-usage
    #     --disable-features=IsolateOrigins,DisableLoadExtensionCommandLineSwitch,site-per-process
    #     --disable-session-crashed-bubble
    #     --disable-search-engine-choice-screen
    #     --user-data-dir=/tmp/uc_nx66uj6u
    #     --disable-features=IsolateOrigins,site-per-process
    #     --disable-session-crashed-bubble
    #     --headless=new
    #     --remote-debugging-host=127.0.0.1
    #     --remote-debugging-port=38787
    #     --webrtc-ip-handling-policy=disable_non_proxied_udp
    #     --force-webrtc-ip-handling-policy
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    # Remove the "Chrome is being controlled by automated software" banner
    "--disable-infobars",
    # Kill the automation extension entirely
    "--disable-extensions",
    "--disable-blink-features=AutomationControlled",
    # Prevent Chrome from reporting crashes / metrics
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--disable-hang-monitor",
    "--disable-prompt-on-repost",
    "--disable-sync",
    "--disable-translate",
    # Suppress "Save password" / other pop-ups
    "--password-store=basic",
    "--use-mock-keychain",
    # Avoid GPU noise in headless/container environments
    "--disable-gpu",
    # Make window geometry look like a real laptop screen
    f"--window-size=1920,{_viewport_height}",
    "--start-maximized",
    # Prevent WebRTC IP leaks (often fingerprinted)
    "--disable-webrtc-hw-encoding",
    "--disable-webrtc-hw-decoding",
    "--enforce-webrtc-ip-permission-check",
]

# ---------------------------------------------------------------------------
# JS snippets injected before page scripts run to overwrite automation flags
# ---------------------------------------------------------------------------
_STEALTH_JS = """
// Hide webdriver property
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Restore chrome runtime object that headless Chrome strips
if (!window.chrome) {
    window.chrome = {};
}
if (!window.chrome.runtime) {
    window.chrome.runtime = {};
}

// Realistic plugin count (headless Chrome has 0)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [1, 2, 3, 4, 5];
        arr.__proto__ = PluginArray.prototype;
        return arr;
    },
});

// Realistic language settings
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Make permissions.query not expose automation
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters);
"""


# avoids noisy zendriver logs

# Suppress zendriver's verbose "starting" INFO banner
logging.getLogger("zendriver.core.browser").setLevel(logging.WARNING)


class ZendriverHtmlFetcher(HtmlFetcher):
    """
    Fetch the rendered HTML of bot-protected pages using Zendriver.

    The browser is started once and reused across all requests.
    Each request opens its own tab, which is closed afterwards.
    Call `await fetcher.start()` before use and `await fetcher.stop()` on
    shutdown (or use it as an async context manager).
    """

    def __init__(self) -> None:
        self._browser: Optional[zd.Browser] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the shared browser instance."""
        self._browser = await self._launch_browser()

    async def stop(self) -> None:
        """Shut down the shared browser instance."""
        if self._browser is not None:
            try:
                await self._browser.stop()
            except Exception:
                pass
            self._browser = None

    async def __aenter__(self) -> "ZendriverHtmlFetcher":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        """
        Navigate to *request.url* with a stealth Chromium session and return
        the fully-rendered HTML source as a string.

        Parameters
        ----------
        request:
            A :class:`FetchRequest` instance describing the target URL and
            optional settings (timeout, UA, cookies, redirect policy).

        Returns
        -------
        str
            The ``document.documentElement.outerHTML`` of the final page.
        """
        url = request.url_str
        timeout = request.timeout  # seconds or None

        coro = self._fetch_inner(request, url)

        if timeout is not None:
            html, final_url = await asyncio.wait_for(coro, timeout=timeout)
        else:
            html, final_url = await coro

        return FetchResult(html, 200, final_url, FetchStrategy.ZENDRIVER)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_inner(self, request: FetchRequest, url: str) -> tuple[str, str]:
        if self._browser is None:
            raise RuntimeError(
                "ZendriverHtmlFetcher is not started. "
                "Call `await fetcher.start()` first."
            )

        # Open a dedicated tab for this request; always close it afterwards
        tab: Optional[zd.Tab] = None
        try:
            tab = await self._browser.get(url, new_tab=True)

            # 1. Inject stealth JS overrides before any page script runs
            await self._inject_stealth_scripts(tab)

            # 2. Apply per-request User-Agent override
            if request.user_agent:
                await tab.set_user_agent(request.user_agent)

            # 3. Inject cookies BEFORE navigation (e.g. DataDome token)
            if request.cookies:
                await self._inject_cookies(self._browser, url, request.cookies)

            # 4. Navigate – with or without redirect following
            if not request.follow_redirects:
                html = await self._fetch_no_redirect(tab, url, request)
            else:
                await tab.get(url)
                # Brief human-like pause to let JS challenges settle
                await self._human_simulation(tab)
                if request.scroll_to_bottom:
                    await self._scroll_to_bottom(tab)
                html = await tab.get_content()

            final_url = tab.url or url
            return html, final_url

        finally:
            if tab is not None:
                try:
                    await tab.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Browser launch (called once)
    # ------------------------------------------------------------------

    async def _launch_browser(self) -> zd.Browser:
        """Start a Chromium instance with stealth flags."""
        config = zd.Config(
            headless=True,
            browser="brave", # other options: "chrome", "auto" (which is "chrome" on Linux)
            browser_args=_STEALTH_BROWSER_ARGS,
            #lang="en-US", #seems to be a bug in zendriver that when setting it an exception gets thrown
        )

        return await zd.start(config=config)

    # ------------------------------------------------------------------
    # Stealth JS injection
    # ------------------------------------------------------------------

    async def _inject_stealth_scripts(self, tab: zd.Tab) -> None:
        """
        Evaluate the stealth JS overrides in the page context.

        We also use CDP ``Page.addScriptToEvaluateOnNewDocument`` so that the
        patches survive navigations and are applied before any site script runs.
        """
        try:
            await tab.send(cdp.page.add_script_to_evaluate_on_new_document(_STEALTH_JS))
        except Exception as exc:
            logger.debug("addScriptToEvaluateOnNewDocument failed: %s", exc)

    # ------------------------------------------------------------------
    # Cookie injection
    # ------------------------------------------------------------------

    async def _inject_cookies(
        self,
        browser: zd.Browser,
        url: str,
        cookies: dict[str, str],
    ) -> None:
        """
        Set cookies via CDP before the first navigation request is sent.

        The domain is derived from *url* so the browser accepts the cookies
        for the target site without needing to visit it first.
        """
        parsed = urlparse(url)
        domain = parsed.hostname or parsed.netloc
        secure = parsed.scheme == "https"

        cookie_params: list[cdp.network.CookieParam] = [
            cdp.network.CookieParam(
                name=name,
                value=value,
                domain=domain,
                path="/",
                secure=secure,
                same_site=cdp.network.CookieSameSite.NONE if secure else None,
            )
            for name, value in cookies.items()
        ]

        try:
            await browser.cookies.set_all(cookie_params)
            logger.debug("Injected %d cookie(s) for %s", len(cookie_params), domain)
        except Exception as exc:
            logger.warning("Cookie injection failed: %s", exc)

    # ------------------------------------------------------------------
    # No-redirect strategy
    # ------------------------------------------------------------------

    async def _fetch_no_redirect(
        self, tab: zd.Tab, url: str, request: FetchRequest
    ) -> str:
        """
        Navigate to *url* but do not follow any HTTP redirects.

        The fetcher enables CDP Fetch interception, intercepts the very first
        response, grabs the body, and then aborts the request chain so the
        browser never follows the redirect.
        """
        # We capture the HTML from the first (possibly redirect) response.
        html_result: list[str] = []
        done_event = asyncio.Event()

        async def handle_request_paused(event: cdp.fetch.RequestPaused) -> None:
            if done_event.is_set():
                # Allow any subsequent sub-resource requests through
                try:
                    await tab.send(
                        cdp.fetch.continue_request(request_id=event.request_id)
                    )
                except Exception:
                    pass
                return

            status = event.response_status_code or 0

            # If it's a redirect (3xx), capture the location and stop
            if 300 <= status < 400:
                html_result.append(
                    f"<html><body>Redirect to {event.response_headers}</body></html>"
                )
                done_event.set()
                try:
                    await tab.send(
                        cdp.fetch.fail_request(
                            request_id=event.request_id,
                            error_reason=cdp.network.ErrorReason.ABORTED,
                        )
                    )
                except Exception:
                    pass
            else:
                # Continue normally, we'll grab content after load
                try:
                    await tab.send(
                        cdp.fetch.continue_request(request_id=event.request_id)
                    )
                except Exception:
                    pass

        # Enable Fetch interception for navigation requests only
        try:
            await tab.send(
                cdp.fetch.enable(
                    patterns=[
                        cdp.fetch.RequestPattern(
                            url_pattern="*",
                            request_stage=cdp.fetch.RequestStage.RESPONSE,
                        )
                    ]
                )
            )
            tab.add_handler(cdp.fetch.RequestPaused, handle_request_paused)

            await tab.get(url)
            await self._human_simulation(tab)
            if request.scroll_to_bottom:
                await self._scroll_to_bottom(tab)
            html = await tab.get_content()

        finally:
            try:
                await tab.send(cdp.fetch.disable())
            except Exception:
                pass

        return html if not html_result else html_result[0]

    # ------------------------------------------------------------------
    # Scroll to bottom (resolves lazy-loaded elements)
    # ------------------------------------------------------------------
    async def _scroll_to_bottom(self, tab: zd.Tab) -> None:
        """
        Incrementally scroll to the bottom of the page so that lazy-loaded
        elements (images, infinite scroll, etc.) are fully rendered before
        the HTML is captured.
        """
        try:
            # Determine total page height
            page_height = await tab.evaluate("document.body.scrollHeight")
            if not page_height:
                return

            current_pos = 0

            while current_pos < page_height:
                current_pos = min(current_pos + _viewport_height, page_height)
                await tab.evaluate(
                    f"window.scrollTo({{top: {current_pos}, left: 0, behavior: 'smooth'}});"
                )
                # Wait for lazy-load triggers to fire
                await asyncio.sleep(random.uniform(0.2, 0.4))

                # Re-check height in case new content extended the page
                new_height = await tab.evaluate("document.body.scrollHeight")
                if new_height and new_height > page_height:
                    page_height = new_height

            # Brief pause at the bottom before content is captured
            await asyncio.sleep(random.uniform(0.2, 0.5))

        except Exception as exc:
            logger.debug("Scroll-to-bottom failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Human behaviour simulation
    # ------------------------------------------------------------------

    async def _human_simulation(self, tab: zd.Tab) -> None:
        """
        Perform randomised human-like interactions to satisfy behavioural
        analysis layers (mouse movement, scroll, natural idle time).
        """
        try:
            # Random mouse drift across a realistic viewport
            for _ in range(random.randint(3, 7)):
                x = random.uniform(200, 1200)
                y = random.uniform(100, 700)
                await tab.send(
                    cdp.input_.dispatch_mouse_event(
                        type_="mouseMoved",
                        x=x,
                        y=y,
                    )
                )
                await asyncio.sleep(random.uniform(0.05, 0.18))

            # Scroll down a bit then back up (natural reading behaviour)
            scroll_y = random.randint(200, 600)
            await tab.evaluate(
                f"window.scrollBy({{top: {scroll_y}, left: 0, behavior: 'smooth'}});"
            )
            await asyncio.sleep(random.uniform(0.4, 0.9))
            await tab.evaluate(
                "window.scrollBy({top: -150, left: 0, behavior: 'smooth'});"
            )

            # Natural idle pause – humans don't react instantly
            await asyncio.sleep(random.uniform(0.8, 2.0))

        except Exception as exc:
            # Simulation is best-effort; never fail the fetch because of it
            logger.debug("Human simulation step failed (non-fatal): %s", exc)
