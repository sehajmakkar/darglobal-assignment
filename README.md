# DarGlobal × Wasalt Real-Estate AI Assistant

An AI chatbot that answers questions about **DarGlobal** luxury developments and **Wasalt** property listings. It uses data scraped from both public websites and a free LLM served through [OpenRouter](https://openrouter.ai), and it runs as a single Docker container.

> **Status:** 🚧 In development. The deployment pipeline is live; the chatbot itself is being built.
>
> **Live URL:** https://dgbot-1023394202328.europe-west1.run.app (currently a placeholder page and health check)

---

## What it does

- Answers questions about DarGlobal projects, brand partners, locations, amenities, and company information. Examples: *"What is DaVinci Tower by Pagani?"*, *"Which DarGlobal projects are in Saudi Arabia?"*
- Answers questions about Wasalt property listings. Example: *"Show me apartments for rent in Riyadh."*
- **Grounded answers with sources.** Every answer comes from the scraped data and links to the original pages. If the data doesn't cover a question, the bot says so and doesn't guess.
- **English and Arabic.** The bot replies in the language you ask in.
- Streams responses token by token.

## Architecture

```
 OFFLINE                                   RUNTIME (one Docker container)
 ───────                                   ──────────────────────────────
 sitemaps + robots.txt                     React chat UI  ──►  FastAPI (/api/chat, SSE)
        │                                                          │
   polite scraper  ──►  raw HTML                         hybrid retrieval (dense + BM25)
        │                                                   over Qdrant (embedded)
   parsers + cleaning                                              │
        │                                                 prompt + citations
   data/processed/*.jsonl  ── docker build ──►  index    OpenRouter free LLM (with fallbacks)
```

- **Scraping runs separately from the app.** The scraper saves a versioned data snapshot, and the Docker image builds its search index from that snapshot. If a source site goes down, the deployed chatbot keeps working.
- **Retrieval-augmented generation (RAG).** Search combines semantic vectors with keyword (BM25) matching, so exact names like "Pagani" or "DG1" are found reliably. Results can also be filtered by city, property type, and price.
- **Built to scale.** Moving the vector store to a Qdrant server is a single environment-variable change. The API is stateless, so it can scale horizontally. Adding a new data source means adding one module.

## Tech stack

| Layer | Technology |
|---|---|
| Scraping | Python, httpx, selectolax, Playwright (only for pages that need JavaScript rendering), trafilatura |
| Data | Pydantic v2 schemas, JSONL snapshot |
| Embeddings | fastembed (local, multilingual) |
| Vector search | Qdrant: hybrid dense + BM25 search with metadata filters |
| LLM | Free OpenRouter models (`:free`), called through the OpenAI-compatible SDK |
| Backend | FastAPI with Server-Sent Events streaming |
| Frontend | React, Vite, TypeScript, Tailwind |
| Deployment | Docker (multi-stage build), Google Cloud Run, GitHub Actions |

## Data sources & scraping policy

| Source | What is collected | How |
|---|---|---|
| [DarGlobal](https://www.darglobal.co.uk) | Projects, brand partners, company pages, press, insights, blog | A standard browser at human pace, because the site shows a JavaScript bot check to plain HTTP clients |
| [Wasalt](https://wasalt.sa) | Sale and rental listings, daily rentals, and city/district coverage, in English and Arabic | Wasalt's public sitemaps (`cdn.wasalt.sa`), plus a small sample of listing pages saved by hand |

The scraper follows these rules:
- It only fetches public pages that robots.txt allows. Sitemaps are the source of URLs.
- Automated requests use an honest User-Agent, a request-rate limit, and a response cache, so no page is downloaded twice.
- It never tries to get around bot protection: no spoofed identities, stealth tooling, proxies, or CAPTCHA solving. Wasalt's main site blocks automated clients, so the scraper never requests it and uses only Wasalt's published sitemaps. The resulting gaps are listed under [Limitations](#limitations).

## Run locally

> The app currently serves a placeholder page and a health check while the chatbot is built.

**With Docker:**

```bash
cp .env.example .env            # add OPENROUTER_API_KEY
docker build -t dg-assistant .
docker run -p 7860:7860 --env-file .env dg-assistant
# open http://localhost:7860  ·  API docs: http://localhost:7860/api/docs
```

**Without Docker** (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run python -m dgbot.api      # http://localhost:7860
uv run pytest                   # unit tests (no network, no LLM quota used)
```

## Project structure

```
src/dgbot/
  core/        # config, logging, errors
  domain/      # typed data models (projects, listings, articles, chat)
  scraping/    # offline, per-source scrapers (DarGlobal, Wasalt); never shipped in the runtime image
  ingestion/   # normalisation, chunking, indexing pipeline
  retrieval/   # embeddings, vector store, hybrid retriever (behind interfaces)
  llm/         # LLM client interface + OpenRouter implementation
  chat/        # chat use case: retrieve → prompt → generate, with citations
  api/         # thin FastAPI layer (routes, schemas, wiring)
  evaluation/  # retrieval and answer-quality evals
frontend/      # React chat UI
data/processed # scraped data snapshot (JSONL)
eval/          # golden question set
tests/         # unit, integration, and HTML fixtures
```

## Limitations

- **Most Wasalt listings have no price or city.** Wasalt's main site blocks automated access, so most listing data comes from sitemap URLs. Those URLs encode the property type, area, bedrooms, and listing ID. The bot says so when a question needs data it doesn't have.

_More limitations will be added as they are found, each with its cause and impact._

## Roadmap

- [ ] Data collection: DarGlobal
- [ ] Data collection: Wasalt
- [ ] Cleaning, normalization, and the data snapshot
- [ ] Hybrid retrieval and evaluation set
- [ ] RAG chat API with streaming and citations
- [ ] Chat UI (English and Arabic, RTL layout)
- [ ] Docker image
- [ ] Public deployment and CI/CD
- [ ] Structured search tool (filter by price, bedrooms, and city)

---

Built by Sehaj Preet as part of the DarGlobal Junior AI Engineer assessment.
