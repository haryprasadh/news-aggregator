"""Web search adapter. Tries Tavily first, then Serper; no-key = no results."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from dateutil import parser as dateparser

from ..config import Settings
from ..models import SearchHit


log = logging.getLogger(__name__)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return dateparser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        return None


class SearchClient:
    """Thin async wrapper around Tavily / Serper.

    The class is always constructible. Call `enabled` to know whether any
    backend is configured. `search` returns [] when disabled, never raises.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tavily = settings.tavily_api_key.strip()
        self._serper = settings.serper_api_key.strip()

    @property
    def enabled(self) -> bool:
        return bool(self._tavily or self._serper)

    @property
    def backend(self) -> str:
        if self._tavily:
            return "tavily"
        if self._serper:
            return "serper"
        return "none"

    async def search(
        self, query: str, max_results: int = 8, recency_days: int | None = None
    ) -> list[SearchHit]:
        query = (query or "").strip()
        if not query or not self.enabled:
            return []
        try:
            if self._tavily:
                return await self._tavily_search(query, max_results, recency_days)
            return await self._serper_search(query, max_results, recency_days)
        except Exception as exc:
            log.warning("search failed (%s): %s", self.backend, exc)
            return []

    async def _tavily_search(
        self, query: str, max_results: int, recency_days: int | None
    ) -> list[SearchHit]:
        payload: dict[str, Any] = {
            "api_key": self._tavily,
            "query": query,
            "max_results": min(max_results, 10),
            "search_depth": "basic",
            "include_answer": False,
        }
        if recency_days is not None:
            payload["days"] = recency_days
            payload["topic"] = "news"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
        hits: list[SearchHit] = []
        for item in data.get("results", []):
            hits.append(
                SearchHit(
                    title=str(item.get("title") or "").strip()[:240] or item.get("url", ""),
                    url=item.get("url", ""),
                    snippet=str(item.get("content") or "")[:500],
                    published=_parse_date(item.get("published_date")),
                    source=item.get("source", ""),
                )
            )
        return hits

    async def _serper_search(
        self, query: str, max_results: int, recency_days: int | None
    ) -> list[SearchHit]:
        # Serper has /search and /news. Use /news when caller asked for recency.
        endpoint = (
            "https://google.serper.dev/news"
            if recency_days is not None
            else "https://google.serper.dev/search"
        )
        body: dict[str, Any] = {"q": query, "num": min(max_results, 10), "gl": "in"}
        if recency_days is not None:
            if recency_days <= 1:
                body["tbs"] = "qdr:d"
            elif recency_days <= 7:
                body["tbs"] = "qdr:w"
            else:
                body["tbs"] = "qdr:m"
        headers = {"X-API-KEY": self._serper, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(endpoint, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
        hits: list[SearchHit] = []
        records = data.get("news") if recency_days is not None else data.get("organic")
        for item in records or []:
            hits.append(
                SearchHit(
                    title=str(item.get("title") or "").strip()[:240]
                    or item.get("link", ""),
                    url=item.get("link", ""),
                    snippet=str(item.get("snippet") or "")[:500],
                    published=_parse_date(item.get("date")),
                    source=item.get("source", ""),
                )
            )
        return hits
