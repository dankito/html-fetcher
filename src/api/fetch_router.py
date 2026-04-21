import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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

# returns the fetched HTML directly
@router.get(
    "",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}, "description": "Raw HTML of the fetched page"}},
    summary="Fetch HTML — returns raw HTML",
    operation_id="fetch_html_get",
)
async def fetch_get_html(
    url: str = Query(...),
    timeout: Optional[float] = Query(default=None, gt=0),
    user_agent: Optional[str] = Query(default=None),
    follow_redirects: bool = Query(default=True),
    cookies: Optional[list[str]] = Query(default=None, description="Cookies as 'name:value' pairs"),
    service: FetchService = Depends(_get_service),
) -> HTMLResponse:
    result = await _do_fetch(service, url, timeout, user_agent, follow_redirects, _parse_cookie_pairs(cookies))
    return HTMLResponse(content=result.html)


# returns the fetched HTML as JSON object of type FetchResponse
@router.get(
    "",
    response_model=FetchResponse,
    summary="Fetch HTML — returns JSON envelope",
    operation_id="fetch_json_get",
)
async def fetch_get_json(
    url: str = Query(...),
    timeout: Optional[float] = Query(default=None, gt=0),
    user_agent: Optional[str] = Query(default=None),
    follow_redirects: bool = Query(default=True),
    cookies: Optional[list[str]] = Query(default=None, description="Cookies as 'name:value' pairs"),
    service: FetchService = Depends(_get_service),
) -> FetchResponse:
    result = await _do_fetch(service, url, timeout, user_agent, follow_redirects, _parse_cookie_pairs(cookies))
    return FetchResponse(
        html=result.html,
        status_code=result.status_code,
        final_url=result.final_url,
        strategy=result.strategy.value,
    )


# ---------------------------------------------------------------------------
# POST /fetch   body: FetchRequest JSON
# ---------------------------------------------------------------------------

# returns the fetched HTML directly
@router.post(
    "",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}, "description": "Raw HTML of the fetched page"}},
    summary="Fetch HTML — returns raw HTML",
    operation_id="fetch_html",
)
async def fetch_post_html(
    body: FetchRequest,
    service: FetchService = Depends(_get_service),
) -> HTMLResponse:
    result = await _do_fetch(service, str(body.url), body.timeout, body.user_agent, body.follow_redirects, body.cookies)
    return HTMLResponse(content=result.html)


# returns the fetched HTML as JSON object of type FetchResponse
@router.post(
    "",
    response_model=FetchResponse,
    summary="Fetch HTML — returns JSON envelope",
    operation_id="fetch_json",
)
async def fetch_post_json(
    body: FetchRequest,
    service: FetchService = Depends(_get_service),
) -> FetchResponse:
    result = await _do_fetch(service, str(body.url), body.timeout, body.user_agent, body.follow_redirects, body.cookies)
    return FetchResponse(
        html=result.html,
        status_code=result.status_code,
        final_url=result.final_url,
        strategy=result.strategy.value,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _parse_cookie_pairs(pairs: Optional[list[str]]) -> Optional[dict[str, str]]:
    """Parse ['name:value', ...] query param style into a dict."""
    if not pairs:
        return None
    result = {}
    for pair in (pairs or []):
        if ":" not in pair:
            raise HTTPException(status_code=422, detail=f"Cookie '{pair}' must be in 'name:value' format")
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
):
    try:
        return await service.fetch(
            url,
            timeout=timeout,
            user_agent=user_agent,
            follow_redirects=follow_redirects,
            cookies=cookies,
        )
    except Exception as exc:
        logger.exception("Fetch failed for %s", url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc