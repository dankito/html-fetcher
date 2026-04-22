from pydantic import BaseModel, HttpUrl, Field, computed_field, field_validator
from typing import Optional, Union

from src.model.fetch_result import FetchStrategy


class FetchRequest(BaseModel):
    url: HttpUrl
    timeout: Optional[float] = Field(
        default=None,
        description="Timeout in seconds. Unset means no timeout.",
        gt=0,
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Custom User-Agent header. Unset means a browser UA is used.",
    )
    follow_redirects: bool = Field(
        default=True,
        description="Whether to follow HTTP redirects.",
    )
    cookies: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Cookies to send with the request. "
            "Useful for passing pre-solved bot-detection cookies such as 'datadome'. "
            'Example: {"datadome": "<token>"}'
        ),
    )
    strategies: Optional[list[FetchStrategy]] = Field(
        default=None,
        description=(
            "Custom fetch strategies to use in order. "
            "If not provided, uses the default order (curl_cffi -> camoufox -> zendriver). "
            "Valid: curl, curl-cffi, curl_cffi, camoufox, zendriver (all case-insensitive; curl is a shortcut for curl_cffi). "
            'Example: ["camoufox", "zendriver"]'
        ),
    )
    load_lazy_content: bool = Field(
        default=False,
        description="Whether to scroll to the bottom before capturing HTML (resolves lazy-loaded elements).",
    )

    @field_validator("strategies", mode="before")
    @classmethod
    def parse_strategies(
        cls, v: Optional[Union[str, list[str]]]
    ) -> Optional[list[FetchStrategy]]:
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        result = [parse_strategy_value(s) for s in v]
        return result if result else None

    @computed_field
    @property
    def url_str(self) -> str:
        return str(self.url)


class FetchResponse(BaseModel):
    html: str
    status_code: int
    final_url: str
    strategy: str


def parse_strategy_value(value: str) -> FetchStrategy:
    normalized = value.lower().replace("-", "_").replace(" ", "_")
    if normalized == "curl" or normalized == "curl_cffi":
        return FetchStrategy.CURL_CFFI
    elif normalized == "camoufox":
        return FetchStrategy.CAMOUFOX
    elif normalized == "zendriver":
        return FetchStrategy.ZENDRIVER
    raise ValueError(f"Invalid strategy '{value}'. Valid: curl, curl-cffi, curl_cffi, camoufox, zendriver (all case-insensitive; curl is a shortcut for curl_cffi)")
