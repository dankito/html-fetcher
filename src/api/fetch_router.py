import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dto.fetch_dto import FetchRequest, FetchResponse
from src.service.fetch_service import FetchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fetch", tags=["fetch"])


def _get_service() -> FetchService:
    """Resolved by the app-level dependency override at startup."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# GET  /fetch?url=...&timeout=...&user_agent=...&follow_redirects=...
# ---------------------------------------------------------------------------
@router.get("", summary="Fetch HTML (GET)")
async def fetch_get(
    url: str = Query(..., description="URL to fetch"),
    timeout: Optional[float] = Query(
        default=None, gt=0, description="Timeout in seconds (omit for no timeout)"
    ),
    user_agent: Optional[str] = Query(
        default=None, description="Override User-Agent (omit to use built-in browser UA)"
    ),
    follow_redirects: bool = Query(default=True),
    # Cookies as repeated query params: ?cookies=name:value&cookies=name2:value2
    cookies: Optional[list[str]] = Query(
        default=None,
        description="Cookies as 'name:value' pairs. Repeat for multiple.",
    ),
    accept: Optional[str] = Header(default=None),
    service: FetchService = Depends(_get_service),
):
    parsed_cookies = _parse_cookie_pairs(cookies)
    return await _do_fetch(service, url, timeout, user_agent, follow_redirects, parsed_cookies, accept)


# ---------------------------------------------------------------------------
# POST /fetch   body: FetchRequest JSON
# ---------------------------------------------------------------------------
@router.post("", summary="Fetch HTML (POST)")
async def fetch_post(
    body: FetchRequest,
    accept: Optional[str] = Header(default=None),
    service: FetchService = Depends(_get_service),
):
    return await _do_fetch(
        service,
        str(body.url),
        body.timeout,
        body.user_agent,
        body.follow_redirects,
        body.cookies,
        accept,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _parse_cookie_pairs(pairs: Optional[list[str]]) -> Optional[dict[str, str]]:
    """Parse ['name:value', ...] query param style into a dict."""
    if not pairs:
        return None
    result = {}
    for pair in pairs:
        if ":" not in pair:
            raise HTTPException(
                status_code=422,
                detail=f"Cookie '{pair}' must be in 'name:value' format",
            )
        name, _, value = pair.partition(":")
        result[name.strip()] = value.strip()
    return result or None



# ---------------------------------------------------------------------------
# Shared logic
# ---------------------------------------------------------------------------
async def _do_fetch(
    service: FetchService,
    url: str,
    timeout: Optional[float],
    user_agent: Optional[str],
    follow_redirects: bool,
    cookies: Optional[dict[str, str]],
    accept: Optional[str],
):
    try:
        result = await service.fetch(
            url,
            timeout=timeout,
            user_agent=user_agent,
            follow_redirects=follow_redirects,
            cookies=cookies,
        )
    except Exception as exc:
        logger.exception("Fetch failed for %s", url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Content negotiation: bare "text/html" accept → return raw HTML directly.
    # Anything else (application/json, */*, unset) → return JSON envelope.
    if accept and "text/html" in accept and "application/json" not in accept:
        return HTMLResponse(content=result.html, status_code=200)

    return JSONResponse(
        content=FetchResponse(
            html=result.html,
            status_code=result.status_code,
            final_url=result.final_url,
            strategy=result.strategy.value,
        ).model_dump()
    )