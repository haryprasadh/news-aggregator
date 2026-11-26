"""Thin OpenRouter client wrapper using the OpenAI-compatible SDK."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from ..config import Settings


log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Wraps AsyncOpenAI configured for OpenRouter.

    Notes:
    - `extra_headers` carries the recommended HTTP-Referer + X-Title that
      OpenRouter uses for app attribution.
    - We expose two surfaces: `chat()` for single non-streaming calls (used
      by the tool loop) and `stream_chat()` for streaming the final reply.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key or "missing",
        )

    @property
    def configured(self) -> bool:
        return bool(self._settings.openrouter_api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "HTTP-Referer": self._settings.openrouter_app_url,
            "X-Title": self._settings.openrouter_app_title,
        }

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "extra_headers": self._headers(),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format
        return await self._client.chat.completions.create(**kwargs)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            extra_headers=self._headers(),
        )
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta
            except (AttributeError, IndexError):
                continue
            content = getattr(delta, "content", None)
            if content:
                yield content
