# Code Review Platform — POC

An automatic code review platform that scans Python files against a set of rules using a local LLM. Submit a scan, let it run asynchronously, and fetch the results when ready.

## How it works

```
POST /scans  →  job queued  →  worker picks it up  →  LLM checks each rule  →  results stored
GET /scans/{id}  →  returns status + TRUE/FALSE per rule
```

- Rules are defined in `rules/rules.yaml` — add a new rule by adding a YAML entry, no code changes needed.
- Up to 5 scans run in parallel. Requests beyond that return HTTP 429.
- Results are cached for 24 hours. Resubmitting the same file returns the existing result instantly.
- Everything runs locally — no cloud, no external APIs.

## Prerequisites

| Dependency | Notes |
|---|---|
| [Docker + Docker Compose](https://docs.docker.com/get-docker/) | Runs Redis, API, and workers |
| [Ollama](https://ollama.com) | Runs the LLM on the host (needs GPU access, so it can't run in Docker) |

## Setup

**1. Clone the repo**
```bash
git clone <repo-url>
cd code-review-platform
```

**2. Pull the LLM model**
```bash
ollama pull qwen2.5-coder:7b && ollama list
```

**3. Configure environment**
```bash
cp .env.example .env
```

Defaults work out of the box. To swap the model or adjust limits, edit `.env`:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434   # reaches Ollama on your Mac from Docker
OLLAMA_MODEL=qwen2.5-coder:7b                       # swap to any model pulled in Ollama
REDIS_URL=redis://redis:6379
MAX_PARALLEL_SCANS=5
RESULT_TTL_SECONDS=86400
```

## Running the system

```bash
docker-compose up --build --scale worker=5
```

This starts:
- **Redis** — job queue + result store (port 6379)
- **API** — FastAPI server (port 8000)
- **5 workers** — process scan jobs in parallel

Wait until you see `Application startup complete` in the API logs, then you're ready.

## Usage

### Submit a scan

```bash
curl -X POST http://localhost:8000/scans -F "file=@your_file.py"
```

Returns `202` with `{"scan_id": "...", "status": "queued", "reused": false}`.
If the same file was already scanned recently, returns `200` with `"reused": true` and the existing `scan_id`.
If all 5 workers are busy, returns `429` — wait a moment and retry.

### Fetch results

```bash
curl http://localhost:8000/scans/<scan_id>
```

`results` is `null` until `status` is `done`, then holds one `{rule_id, name, passed}` entry per rule:

```json
{
  "scan_id": "3f2a1b4c-...",
  "status": "done",
  "results": [
    {"rule_id": "meaningful_variable_names", "name": "All variables have meaningful names", "passed": true},
    {"rule_id": "docstring_matches_logic",   "name": "Docstring of function reflects the actual code logic", "passed": false}
  ]
}
```

### Health check & docs

```bash
curl http://localhost:8000/health
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Running tests

```bash
# Create and activate the virtual environment (first time only)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run all tests (no Redis or Ollama needed)
pytest -v
```

All tests use `fakeredis` and mocked LLM clients — no live services required.

## Adding a new review rule

Edit `rules/rules.yaml` and add an entry:

```yaml
- id: your_rule_id
  name: "Human-readable rule name"
  prompt: |
    You are a code reviewer. <describe what to check>.
    Respond with valid JSON only: {"passed": true} or {"passed": false}
```

Restart the workers — they pick up the new rule automatically. Existing cached results are automatically invalidated (the cache key includes a hash of the rules file).

## Project structure

```
app/
  api/main.py          — FastAPI endpoints (POST /scans, GET /scans/{id})
  config.py            — all config loaded from .env
  models.py            — shared Pydantic schemas
  queue.py             — RQ job queue + capacity gate
  worker.py            — RQ job function (runs the review)
  reviewer/
    engine.py          — orchestrates one LLM call per rule
    ollama_client.py   — parametrized Ollama provider
    rules.py           — loads rules.yaml, computes ruleset version hash
  store/
    base.py            — ResultStore protocol (swappable backend)
    redis_store.py     — Redis implementation (AOF on, logical DB 1)
rules/
  rules.yaml           — rule definitions (data, not code)
tests/                 — unit tests (fakeredis + mocked LLM)
```
