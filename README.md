# DarGlobal × Wasalt Real-Estate AI Assistant

An AI chatbot that answers questions about **DarGlobal** luxury developments and **Wasalt** property listings. It uses data scraped from both public websites and a free LLM served through [OpenRouter](https://openrouter.ai), and it runs as a single Docker container.

> **Status:** 🚧 In development. The live demo URL will appear here once it is deployed.
>
> **Live demo:** _coming soon_

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
| Deployment | Docker (multi-stage build), Hugging Face Spaces, GitHub Actions |

## Data sources & scraping policy

| Source | What is collected |
|---|---|
| [DarGlobal](https://www.darglobal.co.uk) | Projects, brand partners, company pages, press, insights, blog |
| [Wasalt](https://wasalt.sa) | Public property listings and category pages (English and Arabic) |

The scraper follows these rules:
- It only fetches public pages that robots.txt allows. Sitemaps are the source of URLs.
- It identifies itself with an honest User-Agent, limits its request rate, and caches responses so no page is downloaded twice.
- It never tries to get around bot protection. Any data limits that result from this are listed under [Limitations](#limitations).

## Run locally

> These instructions describe the target setup. They will be confirmed as each part is built.

```bash
# 1. Configure
cp .env.example .env            # add OPENROUTER_API_KEY

# 2. Run with Docker
docker build -t dg-assistant .
docker run -p 7860:7860 --env-file .env dg-assistant
# open http://localhost:7860
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

_Filled in as they are found. Each will include its cause and impact._

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
