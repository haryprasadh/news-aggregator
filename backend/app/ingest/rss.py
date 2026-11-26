"""RSS / Atom ingestion with tag-based source packs."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import feedparser
import httpx
import yaml

from ..models import FeedItem


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    tags: tuple[str, ...]


class SourceRegistry:
    """Loads `sources.yaml` and indexes sources by tag."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sources: list[Source] = []
        self._by_tag: dict[str, list[Source]] = {}
        self.reload()

    def reload(self) -> None:
        data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        raw = data.get("sources", [])
        srcs: list[Source] = []
        index: dict[str, list[Source]] = {}
        for entry in raw:
            tags = tuple(entry.get("tags", []) or [])
            src = Source(name=entry["name"], url=entry["url"], tags=tags)
            srcs.append(src)
            for tag in tags:
                index.setdefault(tag, []).append(src)
        self._sources = srcs
        self._by_tag = index

    @property
    def all(self) -> list[Source]:
        return list(self._sources)

    @property
    def tags(self) -> list[str]:
        return sorted(self._by_tag.keys())

    def select(self, tags: Iterable[str]) -> list[Source]:
        wanted = {t.strip().lower() for t in tags if t}
        if not wanted:
            return list(self._sources)
        seen: set[str] = set()
        out: list[Source] = []
        for tag in wanted:
            for s in self._by_tag.get(tag, []):
                if s.url not in seen:
                    seen.add(s.url)
                    out.append(s)
        return out


def _parse_time(struct) -> datetime | None:
    if not struct:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(struct), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize(entry, src: Source) -> FeedItem | None:
    url = entry.get("link") or ""
    title = (entry.get("title") or "").strip()
    if not url or not title:
        return None
    summary = entry.get("summary") or entry.get("description") or ""
    if isinstance(summary, list) and summary:
        summary = summary[0].get("value", "")
    published = _parse_time(entry.get("published_parsed")) or _parse_time(
        entry.get("updated_parsed")
    )
    return FeedItem(
        title=title,
        url=url,
        summary=str(summary)[:600],
        published=published,
        source=src.name,
        tags=list(src.tags),
    )


async def _fetch_one(client: httpx.AsyncClient, src: Source) -> list[FeedItem]:
    try:
        r = await client.get(src.url, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        log.warning("RSS fetch failed for %s: %s", src.name, exc)
        return []
    try:
        parsed = feedparser.parse(r.content)
    except Exception as exc:
        log.warning("RSS parse failed for %s: %s", src.name, exc)
        return []
    out: list[FeedItem] = []
    for entry in parsed.entries:
        item = _normalize(entry, src)
        if item is not None:
            out.append(item)
    return out


async def fetch_sources(sources: list[Source]) -> list[FeedItem]:
    if not sources:
        return []
    headers = {
        "User-Agent": "LocalNewsDesk/1.0 (+local app)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    }
    async with httpx.AsyncClient(headers=headers) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, s) for s in sources], return_exceptions=False
        )
    flat: list[FeedItem] = []
    for r in results:
        flat.extend(r)
    return flat


def filter_recent(
    items: list[FeedItem], hours: int, limit: int | None = None
) -> list[FeedItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    fresh: list[FeedItem] = []
    undated: list[FeedItem] = []
    for it in items:
        if it.published is None:
            undated.append(it)
        elif it.published >= cutoff:
            fresh.append(it)
    fresh.sort(key=lambda i: i.published or cutoff, reverse=True)
    out = fresh + undated
    if limit is not None:
        out = out[:limit]
    return out


async def fetch_pack(
    registry: SourceRegistry,
    tags: Iterable[str],
    hours: int,
    limit: int,
) -> list[FeedItem]:
    sources = registry.select(tags)
    items = await fetch_sources(sources)
    seen: set[str] = set()
    deduped: list[FeedItem] = []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        deduped.append(it)
    return filter_recent(deduped, hours=hours, limit=limit)
