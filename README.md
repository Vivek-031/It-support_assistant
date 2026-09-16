# AI IT Support Assistant

A small help-desk app. A user describes a technical problem, the FastAPI backend saves it as a ticket in SQL, searches a 15-article IT knowledge base, and sends the question plus the matching articles to a free LLM (Groq or Gemini). The app shows the answer and stores it with the ticket.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then paste ONE free API key into .env
uvicorn app.main:app --reload
```

Open http://localhost:8000 for the UI, or http://localhost:8000/docs for the interactive API docs.

**Free API keys**

| Provider | Where to get it | `.env` settings |
|---|---|---|
| Groq (default) | https://console.groq.com/keys | `LLM_PROVIDER=groq`, `GROQ_API_KEY=...` |
| Google Gemini | https://aistudio.google.com/apikey | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...` |

If a model name is retired, change `GROQ_MODEL` / `GEMINI_MODEL` in `.env`. You don't need to change any code.

**Optional**

```bash
pip install -r requirements-dev.txt && pytest     # tests mock the LLM, so no key needed
docker build -t it-support . && docker run --env-file .env -p 8000:8000 it-support
```

## Architecture

```
Browser (frontend/: HTML + vanilla JS)
   │  POST /api/tickets {question}
   ▼
FastAPI (app/main.py)
   1. Validate input (Pydantic)            app/schemas.py
   2. Search knowledge base (BM25)         app/retrieval.py
   3. Save ticket: question + context      app/models.py  → SQLite (support.db)
   4. Call LLM with question + context     app/llm.py     → Groq / Gemini REST API
   5. Update ticket with answer / error    → return JSON to the UI
```

| File | Responsibility |
|---|---|
| `app/main.py` | App startup (create tables, seed KB, build search index), API routes, serves the UI |
| `app/config.py` | Reads settings and secrets from environment variables / `.env` |
| `app/database.py` | SQLAlchemy engine, session, and `get_db` dependency |
| `app/models.py` | `tickets` and `kb_articles` tables |
| `app/schemas.py` | Request validation and response shapes |
| `app/retrieval.py` | Dependency-free BM25 keyword search over the KB |
| `app/llm.py` | Prompt, Groq/Gemini HTTP calls, error mapping |
| `app/kb_seed.json` | 15 IT problems and solutions, loaded into SQL on first start |
| `frontend/` | Single-page UI: question form, answer, sources, recent tickets |

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tickets` | Create a ticket, retrieve context, generate and store the AI answer |
| `GET` | `/api/tickets?limit=20` | List recent tickets (newest first) |
| `GET` | `/api/tickets/{id}` | Full ticket: question, retrieved context, sources, AI response |
| `GET` | `/api/kb` | List all knowledge base articles |
| `GET` | `/api/kb/search?q=...` | Test retrieval without calling the LLM |
| `GET` | `/api/health` | Status, active provider, whether a key is configured |

Example:

```bash
curl -X POST localhost:8000/api/tickets -H "Content-Type: application/json" \
  -d '{"question": "My VPN keeps disconnecting when I work from home"}'
```

Status codes: `201` success · `422` invalid input · `404` unknown ticket · `503` LLM not configured · `502`/`504` LLM failure or timeout. When the LLM fails, the ticket is still saved with `status="failed"`, and the response includes its `ticket_id`.

## Key technical decisions

- **Retrieval uses BM25, not embeddings.** For 15 short articles, keyword ranking (with stopwords, light stemming, and extra weight on titles and keywords) is accurate. It is also easy to explain and needs no ML libraries or extra API calls. Articles scoring below a threshold are dropped. If nothing matches, the LLM is told so and gives general guidance. To scale up, swap `KnowledgeBaseIndex` for embeddings or a vector store; the rest of the app stays the same.
- **The ticket is saved before the LLM call.** User questions are never lost, and failures are recorded (`status`, `error_message`) for follow-up.
- **The full context is stored per ticket.** `retrieved_context` holds the exact text sent to the LLM, and `sources` holds article IDs, titles, and scores. This makes each answer auditable and easy to debug.
- **LLM calls use plain REST (httpx), not SDKs.** This keeps dependencies small and makes Groq and Gemini interchangeable with one environment variable. Temperature is low (0.2) for consistent troubleshooting steps.
- **Sync endpoints.** FastAPI runs `def` routes in a threadpool, so blocking SQLAlchemy and httpx calls don't block the event loop. This is simpler than async and fine at this scale.
- **SQLite via SQLAlchemy.** It needs no setup. To switch to Postgres or MySQL, change `DATABASE_URL`.
- **One process serves both UI and API.** The frontend is served by FastAPI from the same origin, so there's no CORS setup or build step.

## Security notes

- API keys are read only from environment variables / `.env`. `.env` is git-ignored and Docker-ignored, and `.env.example` has no secrets.
- Keys never reach the browser. `/api/health` reports only whether a key is set.
- The Gemini key is sent in the `x-goog-api-key` header rather than the URL, so it doesn't appear in request logs.
- Error messages sent to the client are generic. Detailed provider errors are only logged on the server.
- Input is validated on both the client and the server: whitespace is collapsed, length must be 10–1000 characters, and the text must contain words.
- The UI renders the AI answer as escaped text (only `**bold**` is allowed), which prevents XSS. The system prompt tells the model to treat the question as data.

## Possible improvements

Authentication and per-user tickets, streaming responses, embeddings-based search, an admin UI to edit KB articles, ticket status workflow (assign/resolve), and rate limiting.
