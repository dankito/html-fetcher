import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

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
@router.get("", response_model=FetchResponse, summary="Fetch HTML (GET)")
async def fetch_get(
    url: str = Query(..., description="URL to fetch"),
    timeout: Optional[float] = Query(
        default=None, gt=0, description="Timeout in seconds (omit for no timeout)"
    ),
    user_agent: Optional[str] = Query(
        default=None, description="Override User-Agent (omit to use built-in browser UA)"
    ),
    follow_redirects: bool = Query(
        default=True, description="Follow HTTP redirects"
    ),
    service: FetchService = Depends(_get_service),
) -> FetchResponse:
    return await _do_fetch(service, url, timeout, user_agent, follow_redirects)


# ---------------------------------------------------------------------------
# POST /fetch   body: FetchRequest JSON
# ---------------------------------------------------------------------------
@router.post("", response_model=FetchResponse, summary="Fetch HTML (POST)")
async def fetch_post(
    body: FetchRequest,
    service: FetchService = Depends(_get_service),
) -> FetchResponse:
    return await _do_fetch(
        service,
        str(body.url),
        body.timeout,
        body.user_agent,
        body.follow_redirects,
    )


# ---------------------------------------------------------------------------
# Shared logic
# ---------------------------------------------------------------------------
async def _do_fetch(
    service: FetchService,
    url: str,
    timeout: Optional[float],
    user_agent: Optional[str],
    follow_redirects: bool,
) -> FetchResponse:
    try:
        result = await service.fetch(
            url,
            timeout=timeout,
            user_agent=user_agent,
            follow_redirects=follow_redirects,
        )
    except Exception as exc:
        logger.exception("Fetch failed for %s", url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FetchResponse(
        html=result.html,
        status_code=result.status_code,
        final_url=result.final_url,
        strategy=result.strategy.value,
    )
