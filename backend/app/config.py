"""Runtime settings loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = BACKEND_ROOT / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4.5", alias="OPENROUTER_MODEL"
    )
    openrouter_digest_model: str = Field(
        default="", alias="OPENROUTER_DIGEST_MODEL"
    )
    openrouter_app_url: str = Field(
        default="http://localhost:5173", alias="OPENROUTER_APP_URL"
    )
    openrouter_app_title: str = Field(
        default="Local News Desk", alias="OPENROUTER_APP_TITLE"
    )

    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    serper_api_key: str = Field(default="", alias="SERPER_API_KEY")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8787, alias="PORT")

    max_rss_items_per_pack: int = Field(default=40, alias="MAX_RSS_ITEMS_PER_PACK")
    max_search_calls_per_digest: int = Field(
        default=4, alias="MAX_SEARCH_CALLS_PER_DIGEST"
    )
    max_tool_iterations_per_chat: int = Field(
        default=4, alias="MAX_TOOL_ITERATIONS_PER_CHAT"
    )
    digest_recency_hours: int = Field(default=24, alias="DIGEST_RECENCY_HOURS")

    sources_path: Path = CONFIG_DIR / "sources.yaml"
    defaults_path: Path = CONFIG_DIR / "defaults.yaml"

    @property
    def digest_model(self) -> str:
        return self.openrouter_digest_model or self.openrouter_model

    @property
    def has_search(self) -> bool:
        return bool(self.tavily_api_key or self.serper_api_key)

    @property
    def has_llm(self) -> bool:
        return bool(self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
