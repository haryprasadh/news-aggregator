"""HTTP routes: health, digest (cached + refresh), chat (SSE)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings
from ..digest.builder import DigestBuilder
from ..ingest.rss import SourceRegistry
from ..llm.chat import resolve_then_stream
from ..llm.openrouter import OpenRouterClient
from ..models import ChatRequest, Digest, HealthInfo
from ..search.client import SearchClient


log = logging.getLogger(__name__)
router = APIRouter()


def _state(request: Request):
    return request.app.state


@router.get("/api/health", response_model=HealthInfo)
async def health(request: Request) -> HealthInfo:
    settings = get_settings()
    registry: SourceRegistry = _state(request).registry
    return HealthInfo(
        ok=True,
        llm_configured=settings.has_llm,
        search_configured=settings.has_search,
        model=settings.openrouter_model,
        digest_model=settings.digest_model,
        sources_count=len(registry.all),
    )


@router.get("/api/digest", response_model=Digest)
async def get_digest(request: Request) -> Digest:
    state = _state(request)
    async with state.digest_lock:
        if state.digest_cache is None:
            state.digest_cache = await _build(request)
        return state.digest_cache


@router.post("/api/digest/refresh", response_model=Digest)
async def refresh_digest(request: Request) -> Digest:
    state = _state(request)
    async with state.digest_lock:
        state.digest_cache = await _build(request)
        return state.digest_cache


async def _build(request: Request) -> Digest:
    settings = get_settings()
    state = _state(request)
    builder = DigestBuilder(
        settings=settings,
        registry=state.registry,
        search=state.search,
        openrouter=state.openrouter,
    )
    started = datetime.now(timezone.utc)
    try:
        digest = await builder.build()
    except Exception as exc:
        log.exception("digest build failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"digest build failed: {exc}")
    log.info(
        "digest built in %.1fs (%d sections)",
        (datetime.now(timezone.utc) - started).total_seconds(),
        len(digest.sections),
    )
    return digest


@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    settings = get_settings()
    state = _state(request)
    if not state.openrouter.configured:
        raise HTTPException(
            status_code=400,
            detail="OpenRouter not configured. Set OPENROUTER_API_KEY in .env.",
        )

    openrouter: OpenRouterClient = state.openrouter
    registry: SourceRegistry = state.registry
    search: SearchClient = state.search

    async def event_stream():
        try:
            async for chunk in resolve_then_stream(
                request=req,
                settings=settings,
                registry=registry,
                search=search,
                openrouter=openrouter,
            ):
                yield {"event": "token", "data": chunk}
                # cooperative cancellation
                await asyncio.sleep(0)
            yield {"event": "done", "data": "[DONE]"}
        except Exception as exc:
            log.exception("chat stream failed: %s", exc)
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_stream())


@router.get("/api/sources")
async def list_sources(request: Request):
    registry: SourceRegistry = _state(request).registry
    return {
        "count": len(registry.all),
        "tags": registry.tags,
        "sources": [
            {"name": s.name, "url": s.url, "tags": list(s.tags)}
            for s in registry.all
        ],
    }
