import re
from typing import NamedTuple

from src.model.js_detection_result import JsDetectionResult


class JsWallDetectorService:

    # --- Heuristic detectors ---

    JS_REQUIRED_PHRASES = [
        "please enable javascript",
        "javascript is required",
        "javascript must be enabled",
        "you need to enable javascript",
        "enable js to continue",
        "requires javascript to function",
        "this site requires javascript",
        "browser does not support javascript",
        "turn on javascript",
    ]

    EMPTY_SHELL_PATTERNS = [
        # Empty or near-empty body
        r"<body[^>]*>\s*</body>",
        r"<body[^>]*>\s*<script",  # body starts immediately with a script
        r"<body[^>]*>\s*<noscript",

        # React / Vue / Angular mount points with nothing inside
        r'<div[^>]+id=["\']app["\'][^>]*>\s*</div>',
        r'<div[^>]+id=["\']root["\'][^>]*>\s*</div>',
        r'<div[^>]+id=["\']main["\'][^>]*>\s*</div>',

        # Loader spinners / skeleton screens
        r'class=["\'][^"\']*(?:loading|spinner|skeleton)[^"\']*["\']',
    ]

    JS_CHALLENGE_PATTERNS = [
        # Cloudflare / bot-protection challenges
        r"window\._cf_chl",
        r"__cf_chl_opt",
        r"cf-browser-verification",
        r"chal-body",  # Cloudflare challenge body id
        r"jschl[-_]answer",  # older Cloudflare JS challenge
        r"DDoS protection by",
        # Datadome, PerimeterX, Akamai
        r"datadome",
        r"px-captcha",
        r"_pxdk",
        r"bmak\.js",  # Akamai bot manager
        # Generic challenge redirects
        r'<meta[^>]+http-equiv=["\']refresh["\']',  # instant meta-refresh = suspicious
    ]

    NOSCRIPT_REDIRECT_PATTERN = re.compile(
        r"<noscript[^>]*>.*?<meta[^>]+(?:refresh|redirect)|<a[^>]+href.*?</noscript>",
        re.IGNORECASE | re.DOTALL,
    )


    def needs_javascript(self, html: str) -> JsDetectionResult:
        """
        Analyse a web response and decide whether JS enabled browsers like Camoufox or Zendriver should take over.
        Returns a JsDetectionResult with needs_js=True and a human-readable reason if so.
        """

        body = self._extract_body(html)
        lower_html = html.lower()
        lower_body = body.lower()

        # 1. Suspiciously small payload
        if len(html.strip()) < 512:
            return JsDetectionResult(html, body, True, f"Payload too small")

        # 2. Explicit "enable JavaScript" message in visible text: body + title (not full head)
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).lower() if title_m else ""
        for phrase in self.JS_REQUIRED_PHRASES:
            if phrase in lower_body or phrase in title:
                return JsDetectionResult(html, body, True, f"JS-required phrase: '{phrase}'")

        # 3. <noscript> block that redirects or replaces the whole page: body only
        noscript_redirect_match = self.NOSCRIPT_REDIRECT_PATTERN.search(body)
        if noscript_redirect_match:
            return JsDetectionResult(html, body, True, "<noscript> redirect detected", noscript_redirect_match.string)

        # 4. Known bot-challenge / JS-challenge fingerprints whole HTML
        for pattern in self.JS_CHALLENGE_PATTERNS:
            match = re.search(pattern, lower_html, re.IGNORECASE)
            if match:
                return JsDetectionResult(html, body, True, f"JS challenge: '{pattern}'", match.string)

        # 5. Empty shell SPA containers: body only
        for pattern in self.EMPTY_SHELL_PATTERNS:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return JsDetectionResult(html, body, True, f"Empty shell: '{pattern}'", match.string)

        # 6. Content-to-markup ratio is very low (lots of tags, almost no text): body only
        ratio = self._text_content_ratio(body)
        if ratio < 0.04:
            return JsDetectionResult(html, body, True, f"Text/HTML ratio too low ({ratio:.2%})")

        return JsDetectionResult(html, body, False, None)


    def _extract_body(self, html: str) -> str:
        """Return content between <body> tags, or full html if not found."""
        m = re.search(r"<body[^>]*>(.*?)</body>", html, re.IGNORECASE | re.DOTALL)
        return m.group(1) if m else html

    def _text_content_ratio(self, html: str) -> float:
        """Rough ratio of visible text to total HTML length."""
        text = re.sub(r"<[^>]+>", "", html)  # strip tags
        text = re.sub(r"\s+", " ", text).strip()
        if not html:
            return 0.0
        return len(text) / len(html)