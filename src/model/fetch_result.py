from dataclasses import dataclass
from enum import Enum


class FetchStrategy(str, Enum):
    CURL_CFFI = "curl_cffi"
    CAMOUFOX = "camoufox"
    ZENDRIVER = "zendriver"


@dataclass
class FetchResult:
    html: str
    status_code: int
    final_url: str
    strategy: FetchStrategy
    http_version: str | None = None
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    elapsed_microseconds: int | None = None
