"""
backend/agents/scraper_agent.py
=================================
Orchestrates all job scraping sources:
  1. jobspy     — LinkedIn, Indeed, ZipRecruiter, Google Jobs, Dice (sites + queries from config.yaml)
  2. Adzuna/Jooble — global API feeds when keys are set in config.yaml job_boards
  3. ATS        — Greenhouse, Lever, Ashby, Workday, SmartRecruiters (from companies/ YAMLs)
  4. Dice       — also via Apify actor when APIFY_API_TOKEN set (shahidirfan/dice-job-scraper)

Then deduplicates, runs filter agent, and writes to Supabase.
"""

import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import httpx
from loguru import logger

from backend.config import settings
from backend.utils.dedup import make_dedup_hash, filter_duplicates
from backend.agents.filter_agent import run_filter_agent, save_scored_jobs_to_db
from backend.db.client import db


# ── Config ───────────────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "data scientist",
    "machine learning engineer",
    "data analyst",
    "AI engineer",
    "data engineer",
    "software engineer python",
    "full stack developer",
    "analytics engineer",
]

RESULTS_PER_QUERY = 30
HOURS_OLD = 168            # 7-day window matching purge window
MAX_JOBS_PER_RUN = 500

ATS_MAX_WORKERS = 10
ATS_COMPANY_TIMEOUT = 20

APIFY_TIMEOUT = 120        # Max seconds to wait for an Apify sync run


def _load_scraper_agent_yaml() -> dict:
    """Optional `scraper_agent:` block in project-root config.yaml."""
    import yaml

    p = Path(__file__).resolve().parents[2] / "config.yaml"
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("scraper_agent") or {}
    except Exception as e:
        logger.warning(f"Could not read scraper_agent from config.yaml: {e}")
        return {}


def _resolve_apply_config():
    try:
        from backend.scrapers.apply_config import load_apply_config

        return load_apply_config()
    except Exception as e:
        logger.debug(f"apply config not loaded for scraper: {e}")
        return None


def _build_search_queries(sa: dict, apply_cfg) -> list[str]:
    base = list(sa.get("search_queries") or SEARCH_QUERIES)
    seen = {q.lower().strip() for q in base}
    if apply_cfg and getattr(apply_cfg, "target_job_titles", None):
        for t in apply_cfg.target_job_titles[:25]:
            k = (t or "").lower().strip()
            if k and k not in seen:
                seen.add(k)
                base.append(t)
    return base


# ── Main entry point ─────────────────────────────────────────────────────

def run_scraper_agent(dry_run: bool = False) -> dict:
    start = time.time()
    logger.info("🔍 Scraper agent starting...")

    sa = _load_scraper_agent_yaml()
    apply_cfg = _resolve_apply_config()

    search_queries = _build_search_queries(sa, apply_cfg)
    jobspy_sites = sa.get("jobspy_sites") or [
        "linkedin",
        "indeed",
        "zip_recruiter",
        "google",
        "dice",
    ]
    results_per_query = int(sa.get("results_per_query", RESULTS_PER_QUERY))
    hours_old = int(sa.get("hours_old", HOURS_OLD))
    max_jobs_cap = int(sa.get("max_jobs_per_run", MAX_JOBS_PER_RUN))

    existing_hashes = _get_existing_hashes()
    logger.info(f"   {len(existing_hashes)} existing jobs in DB")

    all_jobs = []

    jobspy_jobs = _scrape_with_jobspy(
        search_queries, jobspy_sites, results_per_query, hours_old
    )
    all_jobs.extend(jobspy_jobs)
    logger.info(f"   jobspy: {len(jobspy_jobs)} raw jobs")

    if apply_cfg:
        board_jobs = _scrape_board_api_feeds(apply_cfg)
        all_jobs.extend(board_jobs)
        logger.info(f"   job boards (Adzuna/Jooble): {len(board_jobs)} raw jobs")

    ats_jobs = _scrape_ats_companies()
    all_jobs.extend(ats_jobs)
    logger.info(f"   ATS scrapers: {len(ats_jobs)} raw jobs")

    dice_jobs = _scrape_dice(search_queries, results_per_query)
    all_jobs.extend(dice_jobs)
    logger.info(f"   Dice (Apify): {len(dice_jobs)} raw jobs")

    logger.info(f"   Total raw: {len(all_jobs)} jobs")

    unique_jobs, dup_count = filter_duplicates(all_jobs, existing_hashes)
    logger.info(f"   After dedup: {len(unique_jobs)} unique ({dup_count} duplicates removed)")

    if len(unique_jobs) > max_jobs_cap:
        logger.warning(f"   Capping to {max_jobs_cap} jobs (had {len(unique_jobs)})")
        unique_jobs = unique_jobs[:max_jobs_cap]

    if not unique_jobs:
        logger.info("   No new jobs found. Exiting.")
        elapsed = round(time.time() - start, 1)
        return {
            "scraped_raw": 0,
            "unique_new": 0,
            "apply": 0,
            "maybe": 0,
            "skip": 0,
            "inserted_to_db": 0,
            "llm_calls": 0,
            "elapsed_seconds": elapsed,
            "dry_run": dry_run,
        }

    filter_results = run_filter_agent(unique_jobs)

    db_results = {"inserted": 0, "skipped_duplicates": 0, "errors": 0}
    if not dry_run:
        all_scored = filter_results["apply"] + filter_results["maybe"] + filter_results["skip"]
        db_results = save_scored_jobs_to_db(all_scored)
    else:
        logger.info("   DRY RUN — skipping DB write")

    elapsed = round(time.time() - start, 1)

    summary = {
        "scraped_raw": len(all_jobs),
        "unique_new": len(unique_jobs),
        "apply": len(filter_results["apply"]),
        "maybe": len(filter_results["maybe"]),
        "skip": len(filter_results["skip"]),
        "inserted_to_db": db_results["inserted"],
        "llm_calls": filter_results["llm_calls"],
        "elapsed_seconds": elapsed,
        "dry_run": dry_run,
    }

    logger.info(
        f"✅ Scraper agent done in {elapsed}s | "
        f"{summary['apply']} APPLY, {summary['maybe']} MAYBE, {summary['skip']} SKIP | "
        f"{db_results['inserted']} written to DB"
    )

    if filter_results["apply"]:
        logger.info("🏆 Top APPLY jobs:")
        for job in filter_results["apply"][:5]:
            logger.info(f"   [{job['ai_score']}/10] {job['title']} @ {job['company']} — {job.get('ai_reason', '')}")

    return summary


# ── jobspy scraping ───────────────────────────────────────────────────────

def _scrape_with_jobspy(
    search_queries: list[str],
    site_names: list[str],
    results_wanted: int,
    hours_old: int,
) -> list[dict]:
    """Scrape job boards via python-jobspy (sites + volume from config)."""
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    allowed = {"linkedin", "indeed", "zip_recruiter", "google", "dice", "bayt"}
    sites = [s for s in site_names if s in allowed] or ["linkedin", "indeed", "zip_recruiter", "google"]

    all_jobs = []
    seen_urls = set()

    for query in search_queries:
        try:
            logger.debug(f"   jobspy scraping: '{query}' ({sites})")

            jobs_df = scrape_jobs(
                site_name=sites,
                search_term=query,
                location="United States",
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=True,
                verbose=0,
            )

            if jobs_df is None or jobs_df.empty:
                continue

            for _, row in jobs_df.iterrows():
                url = str(row.get("job_url", ""))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                job = {
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "")),
                    "location": str(row.get("location", "")),
                    "description": str(row.get("description", ""))[:50000],
                    "job_url": url,
                    "source_board": str(row.get("site", "jobspy")),
                    "is_remote": bool(row.get("is_remote", False)),
                    "salary_min": row.get("min_amount"),
                    "salary_max": row.get("max_amount"),
                    "posted_at": str(row.get("date_posted", "")),
                    "dedup_hash": make_dedup_hash(
                        str(row.get("company", "")),
                        str(row.get("title", "")),
                        str(row.get("location", "")),
                    ),
                }
                all_jobs.append(job)

            time.sleep(random.uniform(2, 5))

        except Exception as e:
            logger.warning(f"   jobspy error for '{query}': {e}")
            continue

    return all_jobs


# ── Adzuna / Jooble (global APIs; keys in config.yaml job_boards) ─────────

def _scrape_board_api_feeds(config) -> list[dict]:
    """Pull Adzuna + Jooble when credentials exist; reuses ATS normalizer."""
    combined: list[dict] = []
    pseudo_companies = (
        {"name": "Adzuna", "ats": "adzuna", "career_url": "https://www.adzuna.com"},
        {"name": "Jooble", "ats": "jooble", "career_url": "https://jooble.org"},
    )
    for company in pseudo_companies:
        try:
            batch = _scrape_one_company(company, config)
            combined.extend(batch)
        except Exception as e:
            logger.debug(f"   Board API {company.get('ats')}: {e}")
    return combined


# ── Dice scraping via Apify ──────────────────────────────────────────────

def _scrape_dice(search_queries: list[str], results_wanted: int) -> list[dict]:
    """Scrape Dice.com via Apify actor (shahidirfan/dice-job-scraper)."""
    if not settings.apify_api_token:
        logger.debug("   Dice: no APIFY_API_TOKEN — skipping")
        return []

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for query in search_queries:
        try:
            items = _run_apify_actor(
                "shahidirfan/dice-job-scraper",
                {
                    "keyword": query,
                    "location": "United States",
                    "posted_date": "7d",
                    "results_wanted": results_wanted,
                },
            )
            for item in items:
                url = item.get("url") or item.get("detailsPageUrl") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                loc = item.get("location") or ""
                work_setting = (item.get("workSetting") or "").lower()
                all_jobs.append({
                    "title": item.get("title") or "",
                    "company": item.get("company") or item.get("companyName") or "",
                    "location": loc,
                    "description": (item.get("description_text") or item.get("summary") or "")[:50000],
                    "job_url": url,
                    "source_board": "dice",
                    "is_remote": "remote" in loc.lower() or "remote" in work_setting,
                    "salary_min": None,
                    "salary_max": None,
                    "posted_at": item.get("posted") or item.get("firstActiveDate") or "",
                    "dedup_hash": make_dedup_hash(
                        item.get("company") or item.get("companyName") or "",
                        item.get("title") or "",
                        loc,
                    ),
                })

            time.sleep(1)
        except Exception as e:
            logger.warning(f"   Dice error for '{query}': {e}")
            continue

    return all_jobs


# ── Apify helper ─────────────────────────────────────────────────────────

def _run_apify_actor(actor_id: str, input_data: dict) -> list[dict]:
    """Run an Apify actor synchronously and return dataset items."""
    safe_id = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{safe_id}/run-sync-get-dataset-items"
    with httpx.Client(timeout=APIFY_TIMEOUT) as client:
        r = client.post(
            url,
            params={"token": settings.apify_api_token},
            json=input_data,
        )
        if r.status_code >= 400:
            logger.warning(f"   Apify {actor_id} HTTP {r.status_code}: {r.text[:200]}")
            return []
        return r.json() if isinstance(r.json(), list) else []


# ── ATS company scrapers (parallel) ──────────────────────────────────────

def _scrape_one_company(company: dict, config) -> list[dict]:
    """Scrape a single company. Runs inside a thread pool worker."""
    from backend.scrapers import get_scraper

    career_url = company.get("career_url") or company.get("careers_url")
    if not career_url:
        return []
    company["career_url"] = career_url

    scraper = get_scraper(company, config)
    if not scraper:
        return []

    raw_jobs = scraper.scrape()
    if not raw_jobs:
        return []

    results = []
    for job in raw_jobs:
        job_url = getattr(job, "apply_url", None) or getattr(job, "url", "") or ""
        location = getattr(job, "location", "") or ""
        remote_type = (getattr(job, "remote_type", "") or "").lower()
        is_remote = "remote" in remote_type or "remote" in location.lower()

        job_dict = {
            "title": getattr(job, "title", ""),
            "company": getattr(job, "company", company.get("name", "")),
            "location": location,
            "description": (getattr(job, "description", "") or "")[:50000],
            "job_url": job_url,
            "source_board": company.get("ats", "direct"),
            "ats_platform": company.get("ats", ""),
            "is_remote": is_remote,
            "salary_min": None,
            "salary_max": None,
            "posted_at": str(getattr(job, "date_posted", "") or ""),
            "dedup_hash": make_dedup_hash(
                company.get("name", ""),
                getattr(job, "title", ""),
                location,
            ),
        }
        if job_dict["job_url"]:
            results.append(job_dict)

    return results


def _scrape_ats_companies() -> list[dict]:
    """Scrape all company career pages concurrently with ThreadPoolExecutor."""
    companies_dir = Path("companies")
    if not companies_dir.exists():
        logger.warning("   companies/ directory not found — skipping ATS scraping")
        return []

    try:
        from backend.scrapers.apply_config import load_apply_config
    except ImportError as e:
        logger.warning(f"   ATS scrapers not available: {e}")
        return []

    try:
        config = load_apply_config()
    except Exception as e:
        logger.warning(f"   Could not load apply config: {e}")
        return []

    yaml_files = list(companies_dir.glob("*.yaml")) + list(companies_dir.glob("*.yml"))
    logger.info(f"   ATS: loading {len(yaml_files)} company configs (max_workers={ATS_MAX_WORKERS}, timeout={ATS_COMPANY_TIMEOUT}s)")

    import yaml as _yaml
    companies = []
    for yf in yaml_files:
        try:
            with open(yf) as f:
                c = _yaml.safe_load(f)
            if c and (c.get("career_url") or c.get("careers_url")):
                c["_yaml_stem"] = yf.stem
                companies.append(c)
        except Exception:
            continue

    all_jobs = []
    success = 0
    failed = 0
    timed_out = 0

    with ThreadPoolExecutor(max_workers=ATS_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_scrape_one_company, company, config): company
            for company in companies
        }

        for future in futures:
            company = futures[future]
            stem = company.get("_yaml_stem", company.get("name", "?"))
            try:
                jobs = future.result(timeout=ATS_COMPANY_TIMEOUT)
                if jobs:
                    all_jobs.extend(jobs)
                    success += 1
                    logger.debug(f"   ATS {stem}: {len(jobs)} jobs")
            except FuturesTimeout:
                timed_out += 1
                logger.warning(f"   ATS timeout: {stem} (>{ATS_COMPANY_TIMEOUT}s)")
                future.cancel()
            except Exception as e:
                failed += 1
                logger.debug(f"   ATS failed {stem}: {e}")

    logger.info(
        f"   ATS done: {success} OK, {failed} failed, {timed_out} timed out, "
        f"{len(all_jobs)} jobs found"
    )
    return all_jobs


# ── DB helpers ────────────────────────────────────────────────────────────

def _get_existing_hashes() -> set[str]:
    """Fetch all existing dedup hashes from DB."""
    try:
        client = db()
        result = client.table("jobs").select("dedup_hash").execute()
        return {row["dedup_hash"] for row in (result.data or []) if row.get("dedup_hash")}
    except Exception as e:
        logger.warning(f"Could not fetch existing hashes: {e} — proceeding without dedup check")
        return set()
