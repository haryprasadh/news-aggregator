"""Chat orchestration: resolves model tool-calls, then streams the final reply."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from ..config import Settings
from ..ingest.rss import SourceRegistry
from ..models import ChatRequest
from ..search.client import SearchClient
from .openrouter import OpenRouterClient
from .prompts import system_prompt
from .tools import ToolRunner, tool_schemas


log = logging.getLogger(__name__)


def _dump_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        else:
            out.append({"role": m.role, "content": m.content})
    return out


async def resolve_then_stream(
    *,
    request: ChatRequest,
    settings: Settings,
    registry: SourceRegistry,
    search: SearchClient,
    openrouter: OpenRouterClient,
) -> AsyncIterator[str]:
    """Run the tool loop non-streaming, then stream the final assistant text.

    Yields plain text chunks for SSE.
    """
    if not openrouter.configured:
        yield (
            "OpenRouter is not configured. Set OPENROUTER_API_KEY in .env and "
            "restart the server."
        )
        return

    model = request.model or settings.openrouter_model
    runner = ToolRunner(settings=settings, registry=registry, search=search)
    tools = tool_schemas(
        search_enabled=search.enabled, available_tags=registry.tags
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(request.mode)}
    ]
    messages.extend(_dump_messages(request.messages))

    for _ in range(settings.max_tool_iterations_per_chat):
        resp = await openrouter.chat(
            model=model, messages=messages, tools=tools, temperature=0.2
        )
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            break
        # Echo the assistant's tool-call message into the running transcript
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            result = await runner.run(tc.function.name, tc.function.arguments or "{}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result,
                }
            )
    else:
        # We hit the iteration cap; nudge the model to wrap up using what it has.
        messages.append(
            {
                "role": "system",
                "content": (
                    "Tool budget exhausted. Answer the user now using only the "
                    "evidence already gathered. Cite URLs you already have."
                ),
            }
        )

    async for chunk in openrouter.stream_chat(
        model=model, messages=messages, temperature=0.3
    ):
        yield chunk
