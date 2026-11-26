"""Shared pydantic models for the API and orchestrator."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FeedItem(BaseModel):
    """One normalized item from an RSS / Atom feed."""

    title: str
    url: str
    summary: str = ""
    published: Optional[datetime] = None
    source: str
    tags: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    """One normalized result from the web-search adapter."""

    title: str
    url: str
    snippet: str = ""
    published: Optional[datetime] = None
    source: str = ""


class DigestBullet(BaseModel):
    what: str
    why: str = ""
    link: str = ""


class DigestSection(BaseModel):
    id: str
    title: str
    bullets: list[DigestBullet]
    note: str = ""


class Digest(BaseModel):
    generated_at: datetime
    sections: list[DigestSection]
    model: str
    used_search: bool
    warnings: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    mode: Literal["default", "upsc", "ssc", "civic", "tech"] = "default"
    model: Optional[str] = None


class Citation(BaseModel):
    title: str
    url: str
    source: str = ""


class HealthInfo(BaseModel):
    ok: bool
    llm_configured: bool
    search_configured: bool
    model: str
    digest_model: str
    sources_count: int
