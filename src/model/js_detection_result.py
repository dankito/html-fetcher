from dataclasses import dataclass

@dataclass
class JsDetectionResult:
    content: str
    body: str
    needs_js: bool
    reason: str | None
    matched_html: str | None = None