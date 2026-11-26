"""Digest builder: feeds + optional search -> one OpenRouter JSON call."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import Settings
from ..ingest.rss import SourceRegistry, fetch_pack
from ..llm.openrouter import OpenRouterClient
from ..llm.prompts import DIGEST_SYSTEM
from ..models import Digest, DigestBullet, DigestSection, FeedItem, SearchHit
from ..search.client import SearchClient


log = logging.getLogger(__name__)


def _load_defaults(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _trim_item(it: FeedItem) -> dict[str, Any]:
    return {
        "title": it.title,
        "url": it.url,
        "summary": it.summary[:400],
        "published": it.published.isoformat() if it.published else None,
        "source": it.source,
    }


def _trim_hit(h: SearchHit) -> dict[str, Any]:
    return {
        "title": h.title,
        "url": h.url,
        "snippet": h.snippet[:400],
        "published": h.published.isoformat() if h.published else None,
        "source": h.source,
    }


def _empty_digest(model: str, warnings: list[str]) -> Digest:
    return Digest(
        generated_at=datetime.now(timezone.utc),
        sections=[],
        model=model,
        used_search=False,
        warnings=warnings,
    )


class DigestBuilder:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: SourceRegistry,
        search: SearchClient,
        openrouter: OpenRouterClient,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._search = search
        self._openrouter = openrouter
        self._defaults = _load_defaults(settings.defaults_path)

    @property
    def section_count(self) -> int:
        return len(self._defaults.get("digest", {}).get("sections", []) or [])

    async def build(self) -> Digest:
        cfg = self._defaults.get("digest", {})
        sections_cfg: list[dict[str, Any]] = cfg.get("sections", []) or []
        hours = int(cfg.get("recency_hours", self._settings.digest_recency_hours))
        max_items = int(cfg.get("max_items_per_section", 8))
        max_bullets = int(cfg.get("max_bullets_per_section", 6))

        warnings: list[str] = []
        if not self._openrouter.configured:
            warnings.append("OPENROUTER_API_KEY not set; returning empty digest.")
            return _empty_digest(self._settings.digest_model, warnings)
        if not self._search.enabled:
            warnings.append(
                "No search API key set. Digest is RSS-only; freshness may lag."
            )

        evidence: list[dict[str, Any]] = []
        search_calls_left = self._settings.max_search_calls_per_digest

        for sec in sections_cfg:
            tags = sec.get("tags", []) or []
            items = await fetch_pack(
                self._registry,
                tags=tags,
                hours=hours,
                limit=max_items,
            )
            seed_queries = sec.get("seed_queries", []) or []
            search_hits: list[SearchHit] = []
            if self._search.enabled and seed_queries and search_calls_left > 0:
                # one search call per section, biggest bang for buck
                q = seed_queries[0]
                try:
                    search_hits = await self._search.search(
                        q, max_results=5, recency_days=max(1, hours // 24 or 1)
                    )
                    search_calls_left -= 1
                except Exception as exc:
                    log.warning("digest search failed: %s", exc)
            evidence.append(
                {
                    "section": {
                        "id": sec.get("id"),
                        "title": sec.get("title"),
                        "max_bullets": max_bullets,
                        "is_wildcard": "wildcard" in tags,
                    },
                    "rss_items": [_trim_item(it) for it in items],
                    "search_hits": [_trim_hit(h) for h in search_hits],
                }
            )

        payload = {
            "now": datetime.now(timezone.utc).isoformat(),
            "location_ladder": self._defaults.get("profile", {}).get(
                "location_ladder", []
            ),
            "persona": self._defaults.get("profile", {}).get("persona", ""),
            "max_bullets_per_section": max_bullets,
            "evidence_by_section": evidence,
        }

        model = self._settings.digest_model
        resp = await self._openrouter.chat(
            model=model,
            messages=[
                {"role": "system", "content": DIGEST_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("digest JSON parse failed; raw=%s", text[:200])
            warnings.append("Model returned non-JSON; showing empty digest.")
            return _empty_digest(model, warnings)

        sections_out: list[DigestSection] = []
        for sec_in in data.get("sections", []) or []:
            bullets_in = sec_in.get("bullets", []) or []
            bullets: list[DigestBullet] = []
            for b in bullets_in[:max_bullets]:
                bullets.append(
                    DigestBullet(
                        what=str(b.get("what", "")).strip(),
                        why=str(b.get("why", "")).strip(),
                        link=str(b.get("link", "")).strip(),
                    )
                )
            sections_out.append(
                DigestSection(
                    id=str(sec_in.get("id", "")),
                    title=str(sec_in.get("title", "")),
                    bullets=bullets,
                    note=str(sec_in.get("note", "")).strip(),
                )
            )

        return Digest(
            generated_at=datetime.now(timezone.utc),
            sections=sections_out,
            model=model,
            used_search=self._search.enabled and search_calls_left
            < self._settings.max_search_calls_per_digest,
            warnings=warnings,
        )
