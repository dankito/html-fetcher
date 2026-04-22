import http
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from src.api.fetch_router import router as fetch_router, _get_service
from src.client.camoufox_html_fetcher import CamoufoxHtmlFetcher
from src.client.curl_cffi_html_fetcher import CurlCffiHtmlFetcher
from src.client.zendriver_html_fetcher import ZendriverHtmlFetcher
from src.service.fetch_service import FetchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    curl_client = CurlCffiHtmlFetcher()
    camoufox_html_fetcher = CamoufoxHtmlFetcher()
    await camoufox_html_fetcher.start(headless=True)
    zendriver = ZendriverHtmlFetcher()
    await zendriver.start()

    service = FetchService(curl_client, camoufox_html_fetcher, zendriver)

    # Wire the service into the dependency injection system.
    app.dependency_overrides[_get_service] = lambda: service

    logger.info("html-fetcher service ready")
    yield

    # --- Shutdown ---
    await camoufox_html_fetcher.stop()
    await zendriver.stop()
    logger.info("html-fetcher service stopped")


app = FastAPI(
    title="html-fetcher",
    description=(
        "Fetches a URL's HTML using a two-tier strategy: "
        "curl_cffi (Chrome TLS impersonation) first, "
        "Camoufox headless/headed browser as last resort."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(fetch_router)


# ------------------------------------------------------------------
# Silence uvicorn's own access logger – we emit our own below
# ------------------------------------------------------------------
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# ------------------------------------------------------------------
# Custom access-log middleware
# ------------------------------------------------------------------
_access_logger = logging.getLogger("access")

@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    client = f"{request.client.host}:{request.client.port}" if request.client else "-"
    _access_logger.info(
        '%s - "%s %s HTTP/%s" %s %s %.1fms',
        client,
        request.method,
        request.url.path + (f"?{request.url.query}" if request.url.query else ""),
        request.scope.get("http_version", "1.1"),
        response.status_code,
        http.HTTPStatus(response.status_code).phrase,
        duration_ms,
    )

    return response


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok"}
