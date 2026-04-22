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
