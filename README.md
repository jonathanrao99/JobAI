# Job Search Agent

Fully autonomous job search system. Scrapes 250+ job sources, tailors your resume per application, auto-applies via Playwright, reaches out to hiring managers on LinkedIn/Gmail, and learns from failures.

## Quick Start

```bash
# 1. Clone and scaffold
bash setup.sh

# 2. Activate environment
conda activate job-agent   # or: source .venv/bin/activate

# 3. Install Python deps
pip install -r backend/requirements.txt

# 4. Configure
cp .env.example .env
# → Fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY

# 5. Run Supabase migration
# → SQL Editor → paste backend/db/schema.sql → Run (includes job_dashboard_stats RPC)
# → Or: python backend/db/migrate.py  (prints the same instructions)

# 6. Fill in your profile
# → Edit data/candidate_profile.json with your actual details
# → Drop your resume into data/resumes/resume_base.docx

# 7. Start API + frontend together
(cd frontend && npm install) # once, if you don’t already have frontend/node_modules
npm install                    # once at repo root (concurrently for npm run dev)
npm run dev                    # API via scripts/dev-api.sh → .venv or conda env `job-agent` (not system Python)

# Optional: background workers
docker compose up -d           # Redis + Celery + Flower
```

Open http://localhost:5173. In **development**, [`frontend/hooks/useJobs.js`](frontend/hooks/useJobs.js) resolves `/api/...` to `http://<same-hostname>:8000/...` so the browser does not use Next’s dev proxy for API calls (avoids timeouts on long routes such as `POST /api/applications/{id}/prepare`). Set `NEXT_PUBLIC_API_URL` to override (e.g. production). [`scripts/dev-api.sh`](scripts/dev-api.sh) binds Uvicorn to `0.0.0.0:8000` so `http://<LAN-IP>:5173` can reach the API; add that origin to `FRONTEND_URL` for CORS.

**Vercel:** In the project’s **Settings → General → Root Directory**, set **`frontend`** so the Next.js build writes `.next` where Vercel expects. Config lives in [`frontend/vercel.json`](frontend/vercel.json). Redeploy after changing Root Directory. Set **`NEXT_PUBLIC_API_URL`** to your **public** FastAPI base URL (no trailing slash); the deployed Next app does not proxy `/api` to localhost. Add your Vercel URL to **`FRONTEND_URL`** on the API for CORS. Optional: **`NEXT_PUBLIC_JOBAI_API_TOKEN`** if the API requires auth.

**If you see `ENOENT` / `app-build-manifest.json` / `_buildManifest.js.tmp`:** Turbopack + Fast Refresh can race when the cache is rewritten. The API used to reload on *every* repo file change (including `frontend/.next`), which made this worse — `scripts/dev-api.sh` now uses **`--reload-dir backend`** only. Default **`npm run dev`** in `frontend/` uses webpack (not `--turbopack`) for more stable HMR; use `npm run dev:turbo --prefix frontend` if you want Turbopack. To fix a broken cache: stop dev, run **`npm run clean:frontend`** (or `bash scripts/clean-frontend-next.sh`), then **`npm run dev`** again.

### Development

```bash
npm test                       # pytest via .venv (smoke-tests API; Supabase init mocked)
npm run lint:backend           # ruff on backend/
npm run build:frontend         # Next.js production build
```

Without `.venv`, use `python -m pytest tests -q` with your conda env active.

### Job Board time filter and keywords

- **`GET /api/jobs?since_days=N`** filters by **listing time**: `posted_at >= cutoff`, or if `posted_at` is null, **`scraped_at`** (so the “Last 24 Hours” tab matches when the job was posted, not when it was ingested).
- **`jd_keywords`** on `jobs` is filled by the filter-agent LLM from the title and description. If your database predates this column, run [`backend/db/migrations/add_jd_keywords.sql`](backend/db/migrations/add_jd_keywords.sql) in the Supabase SQL Editor.

### Scrape volume vs. quality vs. LLM cost

Tune the optional `scraper_agent` block in `config.yaml` (see `config.yaml.example`):

- **`jobspy_sites` / `results_per_query` / `hours_old`** — raw listing volume from JobSpy.
- **`locations`** — list of location strings for JobSpy (defaults to `target_locations` when omitted). Combined with `search_queries`, total fetches are capped by **`jobspy_max_fetch_combos`** to avoid runaway runtime.
- **`max_jobs_per_run`** — after hash + normalized **URL** dedupe, jobs are **pre-ranked** (title overlap with `target_job_titles`, remote flag, recency) so the cap keeps the strongest rows for the LLM.
- **`description_backfill_max`** — bounded HTTP fetches to fill empty/short descriptions before filtering (improves match quality without scraping everything twice).

Each completed scrape stores **`funnel_by_source`** on the `agent_runs` row (`metadata`): per `source_board`, counts for `raw`, `post_dedup`, `to_llm`, `instant_reject`, and LLM `apply` / `maybe` / `skip`. Use that to see which sources feed good matches.

Cheap pre-filters live in `data/candidate_profile.json` under `ai_scoring_signals`: **`instant_reject_keywords`** and optional **`title_must_include_any`** (title must contain at least one substring when the list is non-empty).

### Extra Apify actors (`scraper_agent.apify_actors`)

Set `APIFY_API_TOKEN` in `.env`. The scraper already calls the **Dice** actor (`shahidirfan/dice-job-scraper`) internally. To add **additional** [Apify Store](https://apify.com/store) actors, list them under `scraper_agent.apify_actors` in `config.yaml` (see `config.yaml.example`). Each entry needs an actor `id`, `source_board`, `mapper` (`dice` or `flex`), and an `input` object whose string values can use `{query}`, `{keyword}`, and `{location}`. Do **not** duplicate the Dice actor in YAML (it is skipped to avoid double-fetching).

**Compliance:** Job-board scraping may violate site terms; verify Apify actor licenses and target-site policies before running in production.

---

## Build Roadmap

| Session | What gets built | Status |
|---------|----------------|--------|
| **1 — Scaffold** | Project structure, Supabase schema, FastAPI shell, React shell | ✅ Done |
| **2 — Scraper Agent** | Apify + jobspy integration, ATS scrapers from kesiee/apply, deduplication, filter agent with Claude scoring | 🔜 Next |
| **3 — Resume Agent** | Claude resume tailoring, .docx generation, version tracking | ⏳ |
| **4 — Apply Agent** | Playwright-stealth, Easy Apply, ATS form loop, CAPTCHA handling, dry-run mode | ⏳ |
| **5 — Apply Agent (cont.)** | Workday, Greenhouse, Lever, Ashby full form support, failure logging | ⏳ |
| **6 — Outreach Agent** | Apollo contact lookup, PhantomBuster LinkedIn DM, Gmail cold email, 3-touch sequence | ⏳ |
| **7 — Dashboard** | React dashboard, Analytics charts, agent control panel | In progress |
| **8 — Status Parsing** | Gmail OAuth inbox parser, LinkedIn message parser, Calendar invite detector | ⏳ |
| **9 — Learning Agent** | Failure analysis, prompt evolution, answer memory with pgvector | ⏳ |

---

## Architecture

```
JobAI/
├── backend/
│   ├── agents/           # scraper, filter, resume (+ latex helper)
│   ├── prompts/          # LLM prompt text
│   ├── routers/          # jobs, resumes, agent_runs
│   ├── scrapers/         # ATS + Adzuna/Jooble (+ apply_config)
│   ├── utils/            # dedup, llm_client, rate_limiter, …
│   ├── db/
│   │   ├── schema.sql    # tables + job_dashboard_stats()
│   │   ├── migrate.py    # prints how to apply schema
│   │   └── client.py     # Supabase (lazy singleton)
│   ├── tasks.py          # Celery
│   ├── config.py
│   └── main.py
├── frontend/
│   ├── app/              # Next.js app router pages/layout
│   ├── components/       # shared client components
│   └── hooks/            # React Query API helpers
├── companies/            # per-company ATS YAML (scraper input)
├── scripts/dev-api.sh    # picks .venv / conda for uvicorn
├── data/                 # profile, resumes, logs
├── package.json          # npm run dev
├── docker-compose.yml
├── Dockerfile
└── setup.sh
```

## Monthly Cost Estimate

| Service | Cost | Notes |
|---------|------|-------|
| Apify Starter | $49/mo | LinkedIn + Indeed scraping |
| PhantomBuster Starter | $56/mo | LinkedIn outreach |
| Anthropic API | ~$25/mo | ~$0.10/application end-to-end |
| Apollo.io | Free → $39/mo | 50 lookups/mo free |
| Resend | Free | 3k emails/mo |
| Supabase | Free | More than enough |
| **Total** | **~$130/mo** | **Start lean: ~$25/mo (free tiers)** |
