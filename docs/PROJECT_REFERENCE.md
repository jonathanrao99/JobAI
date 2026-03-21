# JobAI — Project reference

This document describes **everything currently set up** in the repository: architecture, configuration, APIs, frontend, data, workers, and tooling. It reflects the codebase as of the last update to this file.

---

## 1. What this project is

**JobAI** (also referred to as “Job Search Agent” in the UI and README) is a **monorepo** with:

- A **FastAPI** backend that talks to **Supabase (Postgres)** via the Supabase Python client (service role).
- A **React + Vite** SPA that proxies API calls to the backend in development.
- **Background work** via **Celery + Redis** (optional): scheduled scrapes, job purge hooks, etc.
- **Agents** for scraping, LLM-based job filtering/scoring, and resume tailoring (LaTeX → PDF).
- **Local files** under `data/` for candidate profile and base resume.

Longer-term roadmap items (auto-apply, outreach automation, etc.) may be described in `README.md`; this file focuses on **what exists in code and config today**.

---

## 2. Repository layout (high level)

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app, routers, agents, scrapers, prompts, DB helpers, Celery tasks |
| `frontend/` | Vite + React app (`src/pages`, `src/hooks`, `styles.css`) |
| `data/` | `candidate_profile.json`, resumes, logs (`data/logs/`), outputs |
| `companies/` | Per-company ATS / job-board YAML configs consumed by scrapers |
| `config.yaml` | Scraper / search profiles (copy from `config.yaml.example`) |
| `supabase/` | Local Supabase project files when using Supabase CLI (if used) |
| `scripts/dev-api.sh` | Runs uvicorn with `.venv` or conda `job-agent` |
| `tests/` | Pytest smoke tests |
| `.github/workflows/ci.yml` | CI pipeline |
| `docker-compose.yml` | Redis + Celery worker + Celery beat + Flower |
| `Dockerfile` | Image for Celery services (installs `backend/requirements.txt`) |
| `package.json` (root) | `npm run dev`, `npm test`, lint/build helpers |
| `pyproject.toml` | Pytest path, Ruff/Black settings |
| `.env` / `.env.example` | Secrets and URLs (not committed) |

---

## 3. Runtimes, ports, and URLs

| Service | Default URL | Notes |
|---------|-------------|--------|
| Frontend (Vite) | `http://localhost:5173` | Dev server; proxies `/api` → backend |
| Backend (Uvicorn) | `http://127.0.0.1:8000` | Started by `scripts/dev-api.sh` or manually |
| API docs (Swagger) | `http://127.0.0.1:8000/api/docs` | FastAPI OpenAPI |
| ReDoc | `http://127.0.0.1:8000/api/redoc` | Alternative docs |
| Health | `GET /health` | No `/api` prefix |
| Redis | `localhost:6379` | From `REDIS_URL` / defaults in `backend/config.py` |
| Flower (Docker) | `http://localhost:5555` | Celery monitor (when compose is up) |

**Vite proxy** (`frontend/vite.json`): requests from the browser to `/api/*` go to `http://127.0.0.1:8000`, so the frontend uses relative paths like `/api/jobs`.

**CORS**: `backend/main.py` allows `settings.frontend_url` (default `http://localhost:5173`).

---

## 4. Environment variables

Configuration is loaded by **Pydantic Settings** from **`backend/config.py`**, reading **`.env`** at the repo root.

### Required for a working DB-backed app

- **`SUPABASE_URL`** — project URL  
- **`SUPABASE_SERVICE_KEY`** — service role key (backend uses this; never expose to the browser)

### Commonly used for LLM features

- **`ANTHROPIC_API_KEY`** — Claude (filter agent, resume agent, etc., depending on `llm_provider` / `llm_model`)

### Optional / provider-specific (see `backend/config.py` for full list)

- `SUPABASE_ANON_KEY`  
- `OPENROUTER_API_KEY`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `OPENAI_API_KEY`  
- `APIFY_API_TOKEN`, `REDIS_URL`, `ENVIRONMENT`, `SECRET_KEY`  
- `FRONTEND_URL`, `BACKEND_URL`  
- Gmail, Calendar, Resend, Apollo, PhantomBuster, 2Captcha, Apify — placeholders for future or optional integrations  

**`.env.example`** lists a minimal subset; **`backend/config.py`** is the source of truth for variable names and defaults.

---

## 5. Python backend

### 5.1 Dependencies

- Declared in **`backend/requirements.txt`** (FastAPI, Uvicorn, Supabase, Celery, Redis, Anthropic, jobspy, playwright, python-docx, etc.).
- Install: `pip install -r backend/requirements.txt` (often inside `.venv`).

### 5.2 Entry point: `backend/main.py`

- **FastAPI** app with lifespan: calls **`init_db()`** from `backend/db/client.py` (Supabase connectivity check).
- **Logging**: Loguru to stdout and rotating files under `data/logs/`.
- **Exception handling**: Unhandled exceptions on `/api/*` return generic 500 JSON; HTTPException and validation errors use Starlette/FastAPI handlers.
- **Routers** (all prefixed as below):

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/api/jobs` | `backend/routers/jobs.py` | Jobs listing, stats, analytics, scrape, manual job, verdict override |
| `/api/resumes` | `backend/routers/resumes.py` | Tailor resume, list/get resumes, download PDF/TeX |
| `/api/profile` | `backend/routers/profile.py` | Read/write `data/candidate_profile.json` |
| `/api/applications` | `backend/routers/applications.py` | Application CRUD / status (Supabase `applications` table) |
| `/api/agent-runs` | `backend/routers/agent_runs.py` | Recent scraper/agent run history |

### 5.3 HTTP API (concrete routes)

**Jobs** — `backend/routers/jobs.py`

- `GET /api/jobs/analytics?days=1..90` — time-series buckets by `scraped_at` / verdict (caps rows scanned for safety).
- `GET /api/jobs/stats` — dashboard aggregates; uses RPC `job_dashboard_stats()` when present, else Python fallback.
- `POST /api/jobs/scrape` — queue Celery task `scrape_and_filter` if broker available; else runs scrape **in-process** via `BackgroundTasks`.
- `POST /api/jobs/manual` — create/upsert a **manual** job (link + description, etc.); optional auto-tailor.
- `GET /api/jobs` — paginated list with filters: `verdict`, `source`, `search`, `min_score`, `is_remote`, **`since_days`** (time window on `scraped_at`), `limit`, `offset`; returns `total`, `has_more`.
- `GET /api/jobs/{job_id}` — single job.
- `POST /api/jobs/{job_id}/verdict` — override `APPLY` / `MAYBE` / `SKIP`.

**Resumes** — `backend/routers/resumes.py`

- `POST /api/resumes/tailor` — body `{ "job_id": "<uuid>" }`; runs resume agent for that job.
- `GET /api/resumes` — list resumes; optional `job_id` query filter.
- `GET /api/resumes/{resume_id}` — detail.
- `GET /api/resumes/{resume_id}/download?format=pdf|tex` — file download from disk paths stored in DB.

**Profile** — `backend/routers/profile.py`

- `GET /api/profile` — returns full JSON profile, a **normalized `form`** object for the UI, and `last_saved`.
- `PUT /api/profile` — updates **`data/candidate_profile.json`**, merging with existing keys (preserves advanced fields not edited in the form). Writes `skills.flat_list`, merges personal/education/experience/projects, sets `_profile_saved_at`.

**Applications** — `backend/routers/applications.py`

- `POST /api/applications` — create row for a `job_id` (unique per job).
- `GET /api/applications` — list with optional `status` filter.
- `GET /api/applications/{id}` — detail with joined job data.
- `PATCH /api/applications/{id}/status` — update pipeline status (`queued`, `applied`, … per DB enum).
- `DELETE /api/applications/{id}` — delete record.

**Agent runs** — `backend/routers/agent_runs.py`

- `GET /api/agent-runs` — recent rows from `agent_runs` (optional `agent_name` filter).

**Health**

- `GET /health` — `{ status, version, environment }` (`backend/version.py`).

### 5.4 Database client: `backend/db/client.py`

- **Lazy singleton** Supabase client created with **service role** key.
- **`db()`** is a callable alias used across routers and tasks (works in FastAPI and Celery without relying on FastAPI lifespan for first use).
- **`init_db()`** (lifespan): lightweight query to verify connectivity.

### 5.5 Agents and pipelines

| Component | Path | Role |
|-----------|------|------|
| Scraper agent | `backend/agents/scraper_agent.py` | Orchestrates scraping + filtering + persistence; records `agent_runs` |
| Filter agent | `backend/agents/filter_agent.py` | Loads `data/candidate_profile.json`, scores jobs with LLM |
| Resume agent | `backend/agents/resume_agent.py` | Tailors resume from base `.docx`, LLM, LaTeX/PDF pipeline |
| LaTeX helper | `backend/agents/latex_resume_agent.py` | LaTeX render / PDF compile |
| Prompts | `backend/prompts/*.py` | Filter and resume system/user prompts |

**Candidate profile** is loaded from **`data/candidate_profile.json`**. The filter prompt (`backend/prompts/filter_prompt.py`) builds a profile summary; it supports **`skills.flat_list`** when present for skills text.

**Base resume** is expected at **`data/resumes/resume_base.docx`** (resume agent).

### 5.6 Scrapers

Located under **`backend/scrapers/`**: generic/jobspy integration, ATS modules (Greenhouse, Lever, Workday, Ashby, SmartRecruiters, etc.), board feeds (Adzuna, Jooble), and **`apply_config.py`** + **`config.yaml`** for enabling routes, API keys, concurrency, rate limits, etc. See `backend/scrapers/README.md` if present for detail.

**`companies/*.yaml`** — company-specific definitions used as scraper input.

### 5.7 Celery: `backend/tasks.py`

- **Broker/backend**: `redis_url` from settings (default `redis://localhost:6379/0`).
- **Tasks** include `scrape_and_filter`, `purge_old_jobs`, `ghost_stale_applications` (exact names and bindings in file).
- **Beat schedule**: weekdays/weekend scrape windows, nightly purge, ghost stale applications (cron in `tasks.py`).
- **Shared pipeline**: `execute_scrape_pipeline(dry_run=...)` used by Celery and by the API fallback path.

Docker Compose runs **worker**, **beat**, and **Flower**; the **FastAPI app itself is not** in Compose by default (you run it via `npm run dev` or uvicorn locally).

---

## 6. Database schema (Supabase)

Canonical SQL is **`backend/db/schema.sql`**. It defines (among others):

- **`jobs`** — scraped jobs, AI score/verdict, URLs, salaries, remote flags, timestamps, dedup hash.
- **`resumes`** — base/tailored resume metadata and `file_path`, optional `job_id`.
- **`applications`** — per-job application state machine (`application_status` enum), links to `job_id` / `resume_id`.
- **`agent_runs`** — scraper/agent execution audit (status, counts, errors, tokens/cost fields).
- **`status_events`**, **`contacts`**, **`outreach`**, **`failures`**, **`answer_memory`** — richer automation schema for future features.
- **RPC** **`job_dashboard_stats()`** — aggregated stats for the dashboard API (optional but recommended).

**Migrations**: `backend/db/migrate.py` is a helper to print/apply instructions; many workflows paste `schema.sql` into the Supabase SQL Editor.

**RLS** is enabled on tables in the schema file; the **backend uses the service role**, which bypasses RLS for server-side operations.

---

## 7. Frontend (React + Vite)

### 7.1 Stack

- **React 18**, **React Router 6**, **TanStack Query v5**
- **Recharts** for the Analytics chart page
- **Vite 5** for bundling and dev server

### 7.2 Global styles

- **`frontend/src/styles.css`** — CSS variables for the dark theme (`--bg-base`, `--accent`, etc.), shared with all pages.

### 7.3 API helper

- **`frontend/src/hooks/useJobs.js`** — `fetch` wrapper `api()`, React Query hooks: stats, jobs, analytics, scrape, agent runs, resumes, applications, profile save/load, etc.

### 7.4 Routes (see `frontend/src/App.jsx`)

| Path | Page | Role |
|------|------|------|
| `/` | Dashboard | Stats, scrape CTA, top APPLY jobs |
| `/board` | Job Board | Time filters, search, verdict filters, add to applications, tailor |
| `/add-job` | Add Job | Manual job + optional tailor |
| `/applied` | Applied | Application list and status updates |
| `/profile` | Profile | Edit `candidate_profile.json` via API |
| `/pipeline` | Pipeline | Legacy-style list with verdict overrides and tailor |
| `/agents` | Agents | Scrape trigger, run log, stats |
| `/analytics` | Analytics | Charts from `/api/jobs/analytics` |
| `/outreach` | Outreach | Lightweight outreach checklist / APPLY queue |

**Layout**: Left nav with sections (Dashboard, Jobs, Tools), status footer with DB job count.

---

## 8. Local data files (important)

| File | Role |
|------|------|
| `data/candidate_profile.json` | **Source of truth** for candidate info for agents; editable via **Profile** UI and **`GET/PUT /api/profile`** |
| `data/resumes/resume_base.docx` | Base resume for tailoring |
| `data/resumes/tailored/` | Output area for generated files (as implemented by resume agent) |
| `data/logs/app_*.log` | Rotating app logs from Loguru |

---

## 9. Root `package.json` scripts

| Script | What it does |
|--------|----------------|
| `npm run dev` | **`concurrently`**: `./scripts/dev-api.sh` + `npm run dev --prefix frontend` |
| `npm run dev:api` | API only |
| `npm run dev:web` | Frontend only |
| `npm test` | `./.venv/bin/python -m pytest tests -q` |
| `npm run lint:backend` | Ruff on `backend/` |
| `npm run build:frontend` | Vite production build in `frontend/` |

---

## 10. CI (GitHub Actions)

**`.github/workflows/ci.yml`**

- **backend job**: Python 3.11, `pip install -r backend/requirements.txt pytest`, `pytest tests -q`
- **frontend job**: Node 20, `npm ci --prefix frontend`, `npm run build --prefix frontend`

Ruff is **not** enforced in CI currently (lint script exists locally).

---

## 11. Testing

- **`tests/conftest.py`** — patches `init_db` with `AsyncMock` so the app loads **without** a live Supabase connection.
- **`tests/test_api.py`** — smoke tests: `GET /health`, `GET /api/docs`.

Run: `npm test` or `pytest tests -q` with `PYTHONPATH=.` (see `pyproject.toml`).

---

## 12. Docker

- **`docker-compose.yml`**: Redis, Celery worker, Celery beat, Flower; mounts project and `data/`, uses `.env`.
- **`Dockerfile`**: Python 3.11 slim, installs `backend/requirements.txt`, copies repo — intended for **workers**, not the Vite dev server.

---

## 13. Security and operations notes

- **Secrets** live in `.env`; never commit real keys.
- **Supabase service key** must only be used **server-side**.
- **Rate limiting** was experimented with (SlowAPI) and removed due to FastAPI/Pydantic interaction issues; reintroduce via middleware or gateway if needed.
- **Production** would require hardening: HTTPS, stricter CORS, auth for the API, secrets rotation, etc.

---

## 14. Quick reference: “where do I change X?”

| Goal | Where |
|------|--------|
| Add/change REST endpoint | `backend/routers/*.py`, register in `backend/main.py` |
| Change LLM model / provider | `.env` + `backend/config.py` + `backend/utils/llm_client.py` |
| Change scrape behavior / boards | `config.yaml`, `backend/scrapers/`, `backend/agents/scraper_agent.py` |
| Change filter prompt | `backend/prompts/filter_prompt.py` |
| Change resume prompt | `backend/prompts/resume_prompt.py` |
| DB tables / RPC | `backend/db/schema.sql`, Supabase SQL Editor |
| UI page | `frontend/src/pages/*.jsx`, routes in `frontend/src/App.jsx` |
| Candidate JSON on disk | `data/candidate_profile.json` or Profile UI → `PUT /api/profile` |

---

*End of reference. For first-time setup steps, see `README.md` and `setup.sh`.*
