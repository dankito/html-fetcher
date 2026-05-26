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
        r"<body[^>]*>\s*</body>",
        r"<body[^>]*>\s*<script",
        r"<body[^>]*>\s*<noscript",
        r'<div[^>]+id=["\']app["\'][^>]*>\s*</div>',
        r'<div[^>]+id=["\']root["\'][^>]*>\s*</div>',
        r'<div[^>]+id=["\']main["\'][^>]*>\s*</div>',
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


    def needs_javascript(self, html: str) -> JsDetectionResult:
        """
        Analyse a web response and decide whether JS enabled browsers like Camoufox or Zendriver should take over.
        Returns a JsDetectionResult with needs_js=True and a human-readable reason if so.
        """

        body = self._extract_body(html)
        lower_html = html.lower()

        # 1. Suspiciously small payload
        if len(html.strip()) < 512:
            return JsDetectionResult(html, body, True, "Payload too small")

        # 2. JS-required phrases — noscript blocks + title only, NOT full body text
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).lower() if title_m else ""
        noscript_blocks = re.findall(r"<noscript[^>]*>(.*?)</noscript>", body, re.IGNORECASE | re.DOTALL)
        lower_noscript = " ".join(noscript_blocks).lower()
        for phrase in self.JS_REQUIRED_PHRASES:
            if phrase in title or phrase in lower_noscript:
                return JsDetectionResult(html, body, True, f"JS-required phrase: '{phrase}'")

        # 3. <noscript> redirect REMOVED — too broad, GTM/analytics use this pattern legitimately

        # 4. Known bot-challenge / JS-challenge fingerprints — whole HTML
        for pattern in self.JS_CHALLENGE_PATTERNS:
            match = re.search(pattern, lower_html)
            if match:
                return JsDetectionResult(html, body, True, f"JS challenge: '{pattern}'")

        # 5. Empty shell SPA containers — empty #app/#root divs only, spinner class REMOVED
        for pattern in self.EMPTY_SHELL_PATTERNS:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return JsDetectionResult(html, body, True, f"Empty shell: '{pattern}'")

        # 6. Text/HTML ratio — raised threshold, only fires when extremely low
        ratio = self._text_content_ratio(body)
        if ratio < 0.02:
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