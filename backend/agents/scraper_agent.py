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

import html
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dateutil import parser as dateparser
from loguru import logger

from backend.agents.filter_agent import run_filter_agent, save_scored_jobs_to_db
from backend.config import settings
from backend.db.client import db
from backend.scrapers.apify_mappers import map_dice_item
from backend.utils.dedup import filter_duplicates, make_dedup_hash

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

DEFAULT_JOBSPY_MAX_COMBOS = 300
DEFAULT_DESC_MIN_CHARS = 80
DEFAULT_DESC_BACKFILL_MAX = 40
DEFAULT_MAX_RESULTS_PER_SOURCE = 200
DEFAULT_MAX_APIFY_ACTOR_RUNS = 40
DEFAULT_DROP_JOBS_WITHOUT_POSTED_AT = False


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


def _resolve_jobspy_locations(sa: dict, apply_cfg) -> list[str]:
    locs = sa.get("locations")
    if isinstance(locs, list) and locs:
        out = [str(x).strip() for x in locs if str(x).strip()]
        if out:
            return out
    if apply_cfg and getattr(apply_cfg, "target_locations", None):
        out = [str(x).strip() for x in apply_cfg.target_locations if str(x).strip()]
        if out:
            return out
    return ["United States"]


def _count_by_source_board(jobs: list[dict]) -> dict[str, int]:
    return dict(Counter((j.get("source_board") or "unknown") for j in jobs))


def _prerank_score(job: dict, title_phrases: list[str]) -> float:
    """Cheap deterministic score: title overlap with targets, remote, recency."""
    title = (job.get("title") or "").lower()
    score = 0.0
    for phrase in title_phrases:
        p = (phrase or "").lower().strip()
        if len(p) >= 3 and p in title:
            score += min(len(p), 36.0)
    if job.get("is_remote"):
        score += 14.0
    posted = job.get("posted_at")
    if posted:
        try:
            dt = dateparser.parse(str(posted))
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                age_hours = (datetime.now(UTC) - dt).total_seconds() / 3600.0
                if age_hours <= 24:
                    score += 24.0
                elif age_hours <= 72:
                    score += 14.0
                elif age_hours <= 168:
                    score += 7.0
        except Exception:
            pass
    return score


def _prerank_jobs_for_cap(jobs: list[dict], title_phrases: list[str]) -> list[dict]:
    phrases = [p for p in title_phrases if (p or "").strip()]
    if not phrases:
        phrases = ["engineer", "scientist", "analyst", "developer", "data", "machine learning", "ai"]
    return sorted(jobs, key=lambda j: _prerank_score(j, phrases), reverse=True)


def _is_recent_posted_at(posted_at: str, max_age_hours: int) -> bool:
    if not posted_at:
        return False
    try:
        dt = dateparser.parse(str(posted_at))
        if dt is None:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age_hours = (datetime.now(UTC) - dt).total_seconds() / 3600.0
        return age_hours <= max_age_hours
    except Exception:
        return False


def _filter_to_latest_jobs(
    jobs: list[dict],
    *,
    max_age_hours: int,
    drop_without_posted_at: bool,
) -> tuple[list[dict], int]:
    """Keep only recent jobs based on posted_at recency window."""
    kept: list[dict] = []
    dropped = 0
    for job in jobs:
        posted = str(job.get("posted_at") or "").strip()
        if not posted:
            if drop_without_posted_at:
                dropped += 1
                continue
            kept.append(job)
            continue
        if _is_recent_posted_at(posted, max_age_hours):
            kept.append(job)
        else:
            dropped += 1
    return kept, dropped


def _strip_html_to_text(raw: str) -> str:
    if not raw:
        return ""
    s = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _backfill_short_descriptions(
    jobs: list[dict],
    max_fetch: int,
    min_chars: int,
) -> int:
    """Fetch listing pages for empty/short descriptions (bounded per run)."""
    if max_fetch <= 0 or min_chars <= 0:
        return 0
    n = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(timeout=18.0, follow_redirects=True, headers=headers) as client:
        for job in jobs:
            if n >= max_fetch:
                break
            desc = (job.get("description") or "").strip()
            if len(desc) >= min_chars:
                continue
            url = (job.get("job_url") or "").strip()
            if not url:
                continue
            try:
                r = client.get(url)
                if r.status_code >= 400:
                    continue
                text = _strip_html_to_text(r.text)[:50000]
                if len(text) > len(desc):
                    job["description"] = text
                    n += 1
            except Exception:
                continue
    if n:
        logger.info(f"   Description backfill: fetched {n} pages (cap={max_fetch})")
    return n


def _merge_funnel_by_source(
    raw_by: dict[str, int],
    dedup_by: dict[str, int],
    funnel_llm: dict,
) -> dict[str, dict]:
    sources: set[str] = set(raw_by) | set(dedup_by)
    for key in (
        "candidates_by_source",
        "instant_reject_by_source",
        "apply_by_source",
        "maybe_by_source",
        "skip_by_source",
    ):
        sources |= set((funnel_llm or {}).get(key) or {})
    out: dict[str, dict] = {}
    for s in sorted(sources):
        out[s] = {
            "raw": raw_by.get(s, 0),
            "post_dedup": dedup_by.get(s, 0),
            "to_llm": (funnel_llm or {}).get("candidates_by_source", {}).get(s, 0),
            "instant_reject": (funnel_llm or {}).get("instant_reject_by_source", {}).get(s, 0),
            "apply": (funnel_llm or {}).get("apply_by_source", {}).get(s, 0),
            "maybe": (funnel_llm or {}).get("maybe_by_source", {}).get(s, 0),
            "skip": (funnel_llm or {}).get("skip_by_source", {}).get(s, 0),
        }
    return out


# ── Main entry point ─────────────────────────────────────────────────────

def run_scraper_agent(dry_run: bool = False) -> dict:
    start = time.time()
    logger.info("🔍 Scraper agent starting...")

    sa = _load_scraper_agent_yaml()
    apply_cfg = _resolve_apply_config()
    runtime_profile = (sa.get("runtime_profile") or settings.scraper_runtime_profile or "balanced").strip().lower()

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
    jobspy_locations = _resolve_jobspy_locations(sa, apply_cfg)
    max_jobspy_combos = int(sa.get("jobspy_max_fetch_combos", DEFAULT_JOBSPY_MAX_COMBOS))
    desc_min_chars = int(sa.get("description_min_chars", DEFAULT_DESC_MIN_CHARS))
    desc_backfill_max = int(sa.get("description_backfill_max", DEFAULT_DESC_BACKFILL_MAX))
    max_results_per_source = int(sa.get("max_results_per_source", settings.scraper_max_results_per_source or DEFAULT_MAX_RESULTS_PER_SOURCE))
    max_apify_actor_runs = int(sa.get("max_apify_actor_runs", settings.scraper_max_apify_actor_runs or DEFAULT_MAX_APIFY_ACTOR_RUNS))
    drop_without_posted_at = bool(sa.get("drop_jobs_without_posted_at", DEFAULT_DROP_JOBS_WITHOUT_POSTED_AT))
    if runtime_profile == "fast":
        results_per_query = min(results_per_query, 20)
        max_jobspy_combos = min(max_jobspy_combos, 120)
        desc_backfill_max = min(desc_backfill_max, 20)
        max_apify_actor_runs = min(max_apify_actor_runs, 16)
    elif runtime_profile == "max":
        results_per_query = min(max(results_per_query, 40), 80)
        max_jobspy_combos = min(max(max_jobspy_combos, 350), 600)
        max_apify_actor_runs = min(max(max_apify_actor_runs, 60), 120)
    logger.info(
        f"   scraper profile={runtime_profile} results_per_query={results_per_query} "
        f"jobspy_combos={max_jobspy_combos} apify_actor_runs_cap={max_apify_actor_runs}"
    )
    prerank_titles: list[str] = []
    if apply_cfg and getattr(apply_cfg, "target_job_titles", None):
        prerank_titles = list(apply_cfg.target_job_titles)
    if not prerank_titles:
        prerank_titles = list(search_queries)

    all_jobs = []

    jobspy_jobs = _scrape_with_jobspy(
        search_queries,
        jobspy_sites,
        results_per_query,
        hours_old,
        jobspy_locations,
        max_jobspy_combos,
    )
    if len(jobspy_jobs) > max_results_per_source:
        jobspy_jobs = _prerank_jobs_for_cap(jobspy_jobs, search_queries)[:max_results_per_source]
    all_jobs.extend(jobspy_jobs)
    logger.info(f"   jobspy: {len(jobspy_jobs)} raw jobs")

    if apply_cfg:
        board_jobs = _scrape_board_api_feeds(apply_cfg)
        if len(board_jobs) > max_results_per_source:
            board_jobs = _prerank_jobs_for_cap(board_jobs, search_queries)[:max_results_per_source]
        all_jobs.extend(board_jobs)
        logger.info(f"   job boards (Adzuna/Jooble): {len(board_jobs)} raw jobs")

    ats_jobs = _scrape_ats_companies()
    if len(ats_jobs) > max_results_per_source:
        ats_jobs = _prerank_jobs_for_cap(ats_jobs, search_queries)[:max_results_per_source]
    all_jobs.extend(ats_jobs)
    logger.info(f"   ATS scrapers: {len(ats_jobs)} raw jobs")

    dice_jobs = _scrape_dice(
        search_queries,
        results_per_query,
        jobspy_locations[0] if jobspy_locations else "United States",
    )
    if len(dice_jobs) > max_results_per_source:
        dice_jobs = _prerank_jobs_for_cap(dice_jobs, search_queries)[:max_results_per_source]
    all_jobs.extend(dice_jobs)
    logger.info(f"   Dice (Apify): {len(dice_jobs)} raw jobs")

    apify_cfg_jobs = _scrape_apify_config_actors(
        sa,
        search_queries,
        jobspy_locations[0] if jobspy_locations else "United States",
        results_per_query,
        max_actor_runs=max_apify_actor_runs,
    )
    if len(apify_cfg_jobs) > max_results_per_source:
        apify_cfg_jobs = _prerank_jobs_for_cap(apify_cfg_jobs, search_queries)[:max_results_per_source]
    all_jobs.extend(apify_cfg_jobs)
    logger.info(f"   Apify (config actors): {len(apify_cfg_jobs)} raw jobs")

    logger.info(f"   Total raw: {len(all_jobs)} jobs")
    all_jobs, dropped_old = _filter_to_latest_jobs(
        all_jobs,
        max_age_hours=hours_old,
        drop_without_posted_at=drop_without_posted_at,
    )
    if dropped_old:
        logger.info(f"   Recency filter: dropped {dropped_old} stale jobs (>{hours_old}h)")
    raw_by_source = _count_by_source_board(all_jobs)

    existing_hashes = _get_existing_hashes_for_candidates(all_jobs)
    logger.info(f"   {len(existing_hashes)} candidate dedup hashes already in DB")

    unique_jobs, dup_count = filter_duplicates(all_jobs, existing_hashes)
    logger.info(f"   After dedup: {len(unique_jobs)} unique ({dup_count} duplicates removed)")
    dedup_by_source = _count_by_source_board(unique_jobs)

    if len(unique_jobs) > max_jobs_cap:
        logger.warning(f"   Pre-rank cap: keeping top {max_jobs_cap} of {len(unique_jobs)} by title/recency")
        unique_jobs = _prerank_jobs_for_cap(unique_jobs, prerank_titles)[:max_jobs_cap]
    elif len(unique_jobs) > 1:
        unique_jobs = _prerank_jobs_for_cap(unique_jobs, prerank_titles)

    backfilled = _backfill_short_descriptions(unique_jobs, desc_backfill_max, desc_min_chars)

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
            "funnel_by_source": {},
            "description_backfills": 0,
            "stale_dropped": dropped_old,
            "recency_hours": hours_old,
        }

    filter_results = run_filter_agent(unique_jobs)

    db_results = {"inserted": 0, "skipped_duplicates": 0, "errors": 0}
    if not dry_run:
        all_scored = filter_results["apply"] + filter_results["maybe"] + filter_results["skip"]
        db_results = save_scored_jobs_to_db(all_scored)
    else:
        logger.info("   DRY RUN — skipping DB write")

    elapsed = round(time.time() - start, 1)

    funnel_llm = filter_results.get("funnel_llm") or {}
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
        "funnel_by_source": _merge_funnel_by_source(raw_by_source, dedup_by_source, funnel_llm),
        "description_backfills": backfilled,
        "dedup_removed": dup_count,
        "stale_dropped": dropped_old,
        "recency_hours": hours_old,
    }

    logger.info(
        f"✅ Scraper agent done in {elapsed}s | "
        f"{summary['apply']} APPLY, {summary['maybe']} MAYBE, {summary['skip']} SKIP | "
        f"{db_results['inserted']} written to DB"
    )
    for source, funnel in sorted(summary["funnel_by_source"].items()):
        logger.info(
            "   source={} fetched={} deduped={} to_llm={} apply={} maybe={} skip={}".format(
                source,
                funnel.get("raw", 0),
                funnel.get("post_dedup", 0),
                funnel.get("to_llm", 0),
                funnel.get("apply", 0),
                funnel.get("maybe", 0),
                funnel.get("skip", 0),
            )
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
    locations: list[str],
    max_fetch_combos: int,
) -> list[dict]:
    """Scrape job boards via python-jobspy (sites, locations, and combo cap from config)."""
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    allowed = {"linkedin", "indeed", "zip_recruiter", "google", "dice", "bayt"}
    sites = [s for s in site_names if s in allowed] or ["linkedin", "indeed", "zip_recruiter", "google"]

    locs = [x for x in (locations or []) if x] or ["United States"]
    pairs = [(q, loc) for q in search_queries for loc in locs]
    cap = max(1, max_fetch_combos)
    if len(pairs) > cap:
        random.shuffle(pairs)
        pairs = pairs[:cap]
        logger.info(f"   jobspy: capped query×location to {cap} fetches ({len(search_queries)} queries × {len(locs)} locs)")

    all_jobs = []
    seen_urls = set()

    for query, location in pairs:
        try:
            logger.debug(f"   jobspy scraping: '{query}' @ '{location}' ({sites})")

            jobs_df = scrape_jobs(
                site_name=sites,
                search_term=query,
                location=location,
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
            logger.warning(f"   jobspy error for '{query}' @ '{location}': {e}")
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

def _scrape_dice(search_queries: list[str], results_wanted: int, location: str) -> list[dict]:
    """Scrape Dice.com via Apify actor (shahidirfan/dice-job-scraper)."""
    if not settings.apify_api_token:
        logger.debug("   Dice: no APIFY_API_TOKEN — skipping")
        return []

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    loc = (location or "").strip() or "United States"

    for query in search_queries:
        try:
            items = _run_apify_actor(
                "shahidirfan/dice-job-scraper",
                {
                    "keyword": query,
                    "location": loc,
                    "posted_date": "7d",
                    "results_wanted": results_wanted,
                },
            )
            for item in items:
                mapped = map_dice_item(item, "dice")
                if mapped is None:
                    continue
                url = mapped.get("job_url") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                all_jobs.append(mapped)

            time.sleep(1)
        except Exception as e:
            logger.warning(f"   Dice error for '{query}': {e}")
            continue

    return all_jobs


def _expand_apify_input_template(obj, query: str, location: str):
    """Replace {query}, {keyword}, {location} in string leaves of a dict/list."""
    if isinstance(obj, str):
        return (
            obj.replace("{query}", query)
            .replace("{keyword}", query)
            .replace("{location}", location)
        )
    if isinstance(obj, dict):
        return {k: _expand_apify_input_template(v, query, location) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_apify_input_template(v, query, location) for v in obj]
    return obj


def _scrape_apify_config_actors(
    sa: dict,
    search_queries: list[str],
    default_location: str,
    results_default: int,
    max_actor_runs: int,
) -> list[dict]:
    """
    Optional `apify_actors` entries in config.yaml (scraper_agent block).
    Skips shahidirfan/dice-job-scraper — use the built-in Dice scrape for that actor.
    """
    if not settings.apify_api_token:
        return []
    specs = sa.get("apify_actors")
    if not isinstance(specs, list) or not specs:
        specs = [
            {
                "id": "horizon_datajobs/us-wellfound-jobs",
                "enabled": True,
                "source_board": "wellfound",
                "mapper": "flex",
                "results_wanted": max(10, int(results_default / 2)),
                "input": {"query": "{query}", "location": "{location}", "maxItems": max(10, int(results_default / 2))},
            },
            {
                "id": "horizon_datajobs/us-builtin-jobs",
                "enabled": True,
                "source_board": "builtin",
                "mapper": "flex",
                "results_wanted": max(10, int(results_default / 2)),
                "input": {"query": "{query}", "location": "{location}", "maxItems": max(10, int(results_default / 2))},
            },
        ]

    from backend.scrapers.apify_mappers import get_mapper

    out: list[dict] = []
    seen_urls: set[str] = set()
    loc = (default_location or "").strip() or "United States"

    actor_runs = 0
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        if not spec.get("enabled", True):
            continue
        actor_id = (spec.get("id") or "").strip()
        if not actor_id:
            continue
        if actor_id == "shahidirfan/dice-job-scraper":
            logger.debug("   apify_actors: skip shahidirfan/dice-job-scraper (built-in Dice path)")
            continue
        source_board = (spec.get("source_board") or "apify").strip()
        mapper_name = spec.get("mapper") or "flex"
        mapper_fn = get_mapper(mapper_name)
        rw = int(spec.get("results_wanted") or results_default or RESULTS_PER_QUERY)
        input_template = spec.get("input") if isinstance(spec.get("input"), dict) else {}

        for query in search_queries:
            if actor_runs >= max_actor_runs:
                logger.info(f"   apify_actors: run cap reached ({max_actor_runs})")
                return out
            try:
                input_data = _expand_apify_input_template(input_template, query, loc) if input_template else {}
                if not input_data:
                    input_data = {"keyword": query, "location": loc, "results_wanted": rw}
                else:
                    if "results_wanted" not in input_data and "maxItems" not in input_data:
                        input_data["results_wanted"] = rw
                items = _run_apify_actor(actor_id, input_data)
                actor_runs += 1
            except Exception as e:
                logger.warning(f"   Apify actor {actor_id}: {e}")
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                mapped = mapper_fn(item, source_board)
                if mapped is None:
                    continue
                u = mapped.get("job_url") or ""
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                out.append(mapped)
            time.sleep(1)

    return out


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
        future_map = {
            pool.submit(_scrape_one_company, company, config): company
            for company in companies
        }

        try:
            for future in as_completed(future_map, timeout=ATS_COMPANY_TIMEOUT):
                company = future_map[future]
                stem = company.get("_yaml_stem", company.get("name", "?"))
                try:
                    jobs = future.result()
                    if jobs:
                        all_jobs.extend(jobs)
                        success += 1
                        logger.debug(f"   ATS {stem}: {len(jobs)} jobs")
                except Exception as e:
                    failed += 1
                    logger.debug(f"   ATS failed {stem}: {e}")
        except FuturesTimeout:
            # Expected when some company scrapers exceed timeout window.
            pass

        # Any futures not completed within timeout window are considered timed out.
        for future, company in future_map.items():
            if future.done():
                continue
            timed_out += 1
            stem = company.get("_yaml_stem", company.get("name", "?"))
            logger.warning(f"   ATS timeout: {stem} (>{ATS_COMPANY_TIMEOUT}s)")
            future.cancel()

    logger.info(
        f"   ATS done: {success} OK, {failed} failed, {timed_out} timed out, "
        f"{len(all_jobs)} jobs found"
    )
    return all_jobs


# ── DB helpers ────────────────────────────────────────────────────────────

def _get_existing_hashes_paginated() -> set[str]:
    """Full-table dedup_hash fetch (fallback when RPC is unavailable)."""
    try:
        client = db()
        out: set[str] = set()
        batch = 1000
        offset = 0
        while True:
            result = (
                client.table("jobs")
                .select("dedup_hash")
                .range(offset, offset + batch - 1)
                .execute()
            )
            chunk = result.data or []
            for row in chunk:
                h = row.get("dedup_hash")
                if h:
                    out.add(h)
            if len(chunk) < batch:
                break
            offset += batch
        return out
    except Exception as e:
        logger.warning(f"Could not fetch existing hashes: {e} — proceeding without dedup check")
        return set()


def _get_existing_hashes_for_candidates(jobs: list[dict]) -> set[str]:
    """Return which dedup_hash values from this scrape batch already exist (bounded RPC calls)."""
    hashes = list({j.get("dedup_hash") for j in jobs if j.get("dedup_hash")})
    if not hashes:
        return set()
    client = db()
    found: set[str] = set()
    batch_size = 250
    for i in range(0, len(hashes), batch_size):
        chunk = hashes[i : i + batch_size]
        try:
            r = client.rpc("jobs_dedup_hashes_in", {"p_hashes": chunk}).execute()
            data = r.data
            if isinstance(data, str):
                import json

                data = json.loads(data)
            if isinstance(data, list):
                found.update(str(x) for x in data if x)
        except Exception as e:
            logger.warning(f"jobs_dedup_hashes_in RPC failed ({e}); falling back to full hash scan")
            return _get_existing_hashes_paginated()
    return found
