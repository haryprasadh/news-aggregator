# News Desk

A lean local web app that builds you one short daily digest and lets you chat
about news, events, and current affairs. The model runs on
[OpenRouter](https://openrouter.ai/), grounded by your curated RSS packs and
an optional web-search API. No database — sources, defaults, and your API
keys are the only on-disk state.

Designed for: a software engineer in Mahabubabad / Hyderabad who wants to
stay current on India, Telangana, tech, jobs, and exam-style current affairs
without browsing 20 sites.

## Architecture (one screen)

```
Browser (Vite + React)
   │
   ▼
FastAPI (backend/app)
   ├── /api/digest             RSS packs (+ optional search) → OpenRouter → JSON digest
   ├── /api/digest/refresh     same, forced rebuild
   ├── /api/chat               SSE: tool-loop chat (RSS pack tool + web_search tool)
   ├── /api/health             config + counts
   └── /api/sources            list source pack contents

Source packs:  backend/config/sources.yaml   (edit freely)
Defaults:      backend/config/defaults.yaml  (digest sections, location ladder)
```

The model decides when to fetch fresh RSS items (`fetch_rss_pack`) and when
to use general web search (`web_search`). It is instructed to cite only URLs
that came back from those tools.

## Prerequisites

- Python 3.11+
- Node 20+
- An OpenRouter API key (https://openrouter.ai/keys)
- Optional: a Tavily or Serper API key (for fresh web search; without it the
  app still works but uses only RSS feeds)

## First-time setup

```bash
cp .env.example .env
# edit .env and put your OPENROUTER_API_KEY in
# (optionally TAVILY_API_KEY or SERPER_API_KEY)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web && npm install && cd ..
```

## Run

Two terminals. Backend:

```bash
source .venv/bin/activate
python -m backend.app.main
# serves on http://127.0.0.1:8787
```

Frontend:

```bash
cd web
npm run dev
# open http://localhost:5173
```

The Vite dev server proxies `/api/*` to the backend.

## Model selection

`OPENROUTER_MODEL` controls the model used for chat + tool-loop reasoning.
`OPENROUTER_DIGEST_MODEL` (optional) is used for the bulk digest summarisation
step — you can keep it cheap.

Verify slugs at https://openrouter.ai/models before editing. Suggested:

| Use | Recommended slug |
|-----|------------------|
| Chat + tools (main) | `anthropic/claude-sonnet-4.5` (or a current Sonnet-class slug) |
| Chat + tools, cheaper | `openai/gpt-4o` |
| Digest summariser | `openai/gpt-4o-mini` or `google/gemini-2.5-flash` |

## Customising your news

- **Add / remove sources**: edit [`backend/config/sources.yaml`](backend/config/sources.yaml).
  Tag each source. The digest builder selects by tag.
- **Reorder digest sections / queries**: edit [`backend/config/defaults.yaml`](backend/config/defaults.yaml).
- **Wildcard / serendipity**: add sources with the `wildcard` tag. The UI and
  prompt always flag those as "verify".

No restart is required for source edits if you redeploy; the registry is
reloaded on process start. Restart the backend after editing the YAMLs.

## Modes

The chat UI exposes a mode selector. Each mode is just a system-prompt
suffix; the backend logic is the same:

- `default` — concise, point-wise answers with citations
- `tech` — software-engineering lens
- `upsc` — UPSC current-affairs revision format
- `ssc` — SSC CGL crisp facts
- `civic` — must-know civic items for an Indian citizen

## What it does NOT do (by design)

- No accounts, no chat history persistence, no analytics.
- No paywall scraping. RSS feeds + your search API only.
- No vector DB. Evidence is fetched live for each request.
- No mobile app. Local web only.

## Troubleshooting

- "OpenRouter not configured" — set `OPENROUTER_API_KEY` in `.env` and restart
  the backend.
- Digest is empty / warnings about search — that's fine; search is optional.
  Without it, freshness depends entirely on RSS.
- A specific feed stays empty — the site may have changed its RSS URL.
  Replace it in `sources.yaml`.
- Model returns generic answers without citations — try a stronger model
  (`OPENROUTER_MODEL=anthropic/claude-sonnet-4.5`) or rephrase "today" / "this
  week" in your prompt; that triggers the tool calls.

## Layout

```
backend/
  app/
    main.py          # FastAPI app + lifespan wiring
    config.py        # pydantic-settings (.env loader)
    models.py        # shared schemas
    api/routes.py    # /api/health, /api/digest, /api/chat (SSE), /api/sources
    ingest/rss.py    # source registry + async feedparser fetch
    search/client.py # Tavily / Serper adapter (graceful no-key)
    llm/
      openrouter.py  # OpenAI SDK pointed at OpenRouter
      prompts.py     # base persona + mode suffixes + digest JSON contract
      tools.py       # tool schemas + server-side dispatch
      chat.py        # tool-loop resolver + final streaming
    digest/builder.py
  config/
    sources.yaml
    defaults.yaml
web/
  src/
    App.tsx          # 2-pane layout: digest + chat
    api.ts           # fetch + manual SSE parser
    main.tsx, styles.css
  vite.config.ts     # /api proxy to backend
```
