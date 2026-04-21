import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.fetch_router import router as fetch_router, _get_service
from src.client.camoufox_html_fetcher import CamoufoxHtmlFetcher
from src.client.curl_cffi_client import CurlCffiClient
from src.service.fetch_service import FetchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    curl_client = CurlCffiClient()
    camoufox_html_fetcher = CamoufoxHtmlFetcher()
    await camoufox_html_fetcher.start(headless=True)

    service = FetchService(curl_client, camoufox_html_fetcher)

    # Wire the service into the dependency injection system.
    app.dependency_overrides[_get_service] = lambda: service

    logger.info("html-fetcher service ready")
    yield

    # --- Shutdown ---
    await camoufox_html_fetcher.stop()
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


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok"}
