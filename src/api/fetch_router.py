import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import HttpUrl

from src.model.fetch_result import FetchResult, FetchStrategy
from src.api.dto.fetch_dto import FetchRequest, FetchResponse, parse_strategy_value
from src.service.fetch_service import FetchService
from src.service.html_sanitizer_service import HtmlSanitizerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fetch", tags=["fetch"])


def _get_service() -> FetchService:
    """Resolved by the app-level dependency override at startup."""
    raise NotImplementedError

htmlSanitizer = HtmlSanitizerService()


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
    url: HttpUrl = Query(...),
    timeout: Optional[float] = Query(default=None, gt=0),
    user_agent: Optional[str] = Query(default=None),
    follow_redirects: bool = Query(default=True),
    cookies: Optional[list[str]] = Query(default=None, description="Cookies as 'name:value' pairs"),
    strategies: Optional[list[str]] = Query( default=None, description="Overwrite the default order ('curl-cffi,camoufox,zendriver') which fetch strategies to use like 'camoufox'"),
    load_lazy_content: bool = Query(default=False, description="Whether to scroll to the bottom before capturing HTML (resolves lazy-loaded elements)."),
    execute_javascript: Optional[bool] = Query(default=None, description="Whether to execute JavaScript (None=default, True=skip curl-cffi, False=disable JS in browsers)."),
    service: FetchService = Depends(_get_service),
) -> HTMLResponse:
    request = FetchRequest(
        url=url,
        timeout=timeout,
        user_agent=user_agent,
        follow_redirects=follow_redirects,
        cookies=_parse_cookie_pairs(cookies),
        strategies=_parse_strategies(strategies),
        load_lazy_content=load_lazy_content,
        execute_javascript=execute_javascript,
    )
    result = await _do_fetch(service, request)
    return _to_html_response(result)


# returns the fetched HTML as JSON object of type FetchResponse
@router.get(
    "",
    response_model=FetchResponse,
    summary="Fetch HTML — returns JSON envelope",
    operation_id="fetch_json_get",
)
async def fetch_get_json(
    url: HttpUrl = Query(...),
    timeout: Optional[float] = Query(default=None, gt=0),
    user_agent: Optional[str] = Query(default=None),
    follow_redirects: bool = Query(default=True),
    cookies: Optional[list[str]] = Query(default=None, description="Cookies as 'name:value' pairs"),
    strategies: Optional[list[str]] = Query( default=None, description="Overwrite the default order ('curl-cffi,camoufox,zendriver') which fetch strategies to use like 'camoufox'"),
    load_lazy_content: bool = Query(default=False, description="Whether to scroll to the bottom before capturing HTML (resolves lazy-loaded elements)."),
    execute_javascript: Optional[bool] = Query(default=None, description="Whether to execute JavaScript (None=default, True=skip curl-cffi, False=disable JS in browsers)."),
    service: FetchService = Depends(_get_service),
) -> FetchResponse:
    request = FetchRequest(
        url=url,
        timeout=timeout,
        user_agent=user_agent,
        follow_redirects=follow_redirects,
        cookies=_parse_cookie_pairs(cookies),
        strategies=_parse_strategies(strategies),
        load_lazy_content=load_lazy_content,
        execute_javascript=execute_javascript,
    )
    result = await _do_fetch(service, request)
    return _to_fetch_response(result)


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
    result = await _do_fetch(service, body)
    return _to_html_response(result)


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
    result = await _do_fetch(service, body)
    return _to_fetch_response(result)


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


def _parse_strategies(strategies: Optional[list[str]]) -> Optional[list[FetchStrategy]]:
    """Parse strategy strings (case-insensitive, handle '-' vs '_', 'curl' shortcut)."""
    if not strategies:
        return None
    result = []
    for s in strategies:
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                result.append(parse_strategy_value(part))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
    return result if result else None


# ---------------------------------------------------------------------------
# Shared logic
# ---------------------------------------------------------------------------
async def _do_fetch(service: FetchService, request: FetchRequest):
    try:
        return await service.fetch(request)
    except Exception as exc:
        logger.exception("Fetch failed for %s", request.url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

def _to_html_response(result: FetchResult) -> HTMLResponse:
    return HTMLResponse(content=htmlSanitizer.clean_html(result))

def _to_fetch_response(result: FetchResult) -> FetchResponse:
    return FetchResponse(
        html=htmlSanitizer.clean_html(result),
        status_code=result.status_code,
        final_url=result.final_url,
        strategy=result.strategy.value,
    )
