from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Union


class FetchRequest(BaseModel):
    url: Union[str, HttpUrl]
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


class FetchResponse(BaseModel):
    html: str
    status_code: int
    final_url: str
    strategy: str