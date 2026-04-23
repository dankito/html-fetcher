import http
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from src.api.fetch_router import router as fetch_router, _get_service
from src.service.app_config_parser import AppConfigParser
from src.service.fetch_service import FetchService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

config = AppConfigParser().parse_app_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    service = await FetchService.from_config(config)

    # Wire the service into the dependency injection system.
    app.dependency_overrides[_get_service] = lambda: service

    logger.info("html-fetcher service ready (port=%d, root_path=%s, version=%s, commit_id=%s)", config.port, config.root_path, config.version, config.commit_id)
    yield

    # --- Shutdown ---
    await service.stop()
    logger.info("html-fetcher service stopped")


app = FastAPI(
    title="html-fetcher",
    description=(
        "Fetches a URL's HTML using a two-tier strategy: "
        "curl_cffi (Chrome TLS impersonation) first, "
        "Camoufox headless/headed browser as last resort."
    ),
    version=config.version,
    lifespan=lifespan,
    root_path=config.root_path,
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
