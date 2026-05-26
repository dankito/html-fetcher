from dataclasses import dataclass

@dataclass
class JsDetectionResult:
    content: str
    needs_js: bool
    reason: str | None