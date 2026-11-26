"""FastAPI entrypoint. Wires registry, search, openrouter, routes."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .ingest.rss import SourceRegistry
from .llm.openrouter import OpenRouterClient
from .search.client import SearchClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("news-desk")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    registry = SourceRegistry(settings.sources_path)
    search = SearchClient(settings)
    openrouter = OpenRouterClient(settings)

    app.state.registry = registry
    app.state.search = search
    app.state.openrouter = openrouter
    app.state.digest_cache = None
    app.state.digest_lock = asyncio.Lock()

    log.info(
        "boot: sources=%d, search=%s, llm=%s, model=%s",
        len(registry.all),
        search.backend if search.enabled else "off",
        "on" if openrouter.configured else "off",
        settings.openrouter_model,
    )
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Local News Desk", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            f"http://{settings.host}:{settings.port}",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
