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

Open http://localhost:5173 (proxies `/api` to the backend).

### Development

```bash
npm test                       # pytest via .venv (smoke-tests API; Supabase init mocked)
npm run lint:backend           # ruff on backend/
npm run build:frontend         # Vite production build
```

Without `.venv`, use `python -m pytest tests -q` with your conda env active.


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
| **7 — Dashboard** | React Kanban + Table, Analytics charts, Outreach center, Agent control panel | ⏳ |
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
├── frontend/src/
│   ├── pages/            # Dashboard, Pipeline, Agents (+ Analytics/Outreach placeholders)
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
