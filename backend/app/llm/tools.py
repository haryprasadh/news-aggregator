"""Tool schemas + server-side dispatch for the chat tool loop."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
from ..ingest.rss import SourceRegistry, fetch_pack
from ..models import FeedItem, SearchHit
from ..search.client import SearchClient


log = logging.getLogger(__name__)


def tool_schemas(*, search_enabled: bool, available_tags: list[str]) -> list[dict[str, Any]]:
    """OpenAI-format tool definitions exposed to the model."""
    tags_doc = ", ".join(available_tags) or "(none)"
    schemas: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "fetch_rss_pack",
                "description": (
                    "Fetch fresh items from the user's curated RSS source packs. "
                    "Always prefer this for grounded, trusted news. "
                    f"Available tags: {tags_doc}."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags to OR-select sources (e.g. ['hyderabad','tech']).",
                        },
                        "hours": {
                            "type": "integer",
                            "description": "Only items published within the last N hours.",
                            "default": 24,
                            "minimum": 1,
                            "maximum": 720,
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Maximum items to return.",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 60,
                        },
                    },
                    "required": ["tags"],
                },
            },
        }
    ]
    if search_enabled:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "General web search. Use for queries not well covered by "
                        "RSS packs (e.g. events near Hyderabad, niche topics, "
                        "fact lookups). Returns title/url/snippet."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {
                                "type": "integer",
                                "default": 6,
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "recency_days": {
                                "type": ["integer", "null"],
                                "description": "If set, restrict to news from the last N days.",
                                "default": None,
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    return schemas


def _serialize_items(items: list[FeedItem]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        out.append(
            {
                "title": it.title,
                "url": it.url,
                "summary": it.summary,
                "published": it.published.isoformat() if it.published else None,
                "source": it.source,
                "tags": it.tags,
            }
        )
    return out


def _serialize_hits(hits: list[SearchHit]) -> list[dict[str, Any]]:
    out = []
    for h in hits:
        out.append(
            {
                "title": h.title,
                "url": h.url,
                "snippet": h.snippet,
                "published": h.published.isoformat() if h.published else None,
                "source": h.source,
            }
        )
    return out


class ToolRunner:
    """Server-side executor for tool calls coming back from the model."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: SourceRegistry,
        search: SearchClient,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._search = search

    async def run(self, name: str, raw_args: str) -> str:
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "bad arguments JSON"})

        if name == "fetch_rss_pack":
            tags = args.get("tags") or []
            hours = int(args.get("hours") or 24)
            max_items = min(
                int(args.get("max_items") or 20),
                self._settings.max_rss_items_per_pack,
            )
            items = await fetch_pack(
                self._registry, tags=tags, hours=hours, limit=max_items
            )
            return json.dumps(
                {
                    "tool": "fetch_rss_pack",
                    "tags": tags,
                    "hours": hours,
                    "count": len(items),
                    "items": _serialize_items(items),
                }
            )

        if name == "web_search":
            if not self._search.enabled:
                return json.dumps({"error": "web search not configured"})
            query = str(args.get("query") or "").strip()
            max_results = int(args.get("max_results") or 6)
            recency_days = args.get("recency_days")
            recency = int(recency_days) if recency_days is not None else None
            hits = await self._search.search(
                query, max_results=max_results, recency_days=recency
            )
            return json.dumps(
                {
                    "tool": "web_search",
                    "query": query,
                    "count": len(hits),
                    "results": _serialize_hits(hits),
                }
            )

        return json.dumps({"error": f"unknown tool: {name}"})
