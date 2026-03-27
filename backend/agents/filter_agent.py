"""
backend/agents/filter_agent.py
================================
Scores scraped jobs against the candidate profile using the LLM.
Runs after scraper_agent, before apply_agent.

Flow:
  raw jobs → pre-filter (instant rejects) → LLM scoring in batches → scored jobs
"""

import asyncio
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dateutil import parser as dateparser
from loguru import logger

from backend.config import settings
from backend.db.client import db
from backend.prompts.filter_prompt import FILTER_SYSTEM_PROMPT, build_filter_prompt
from backend.utils.dedup import pre_filter_by_keywords
from backend.utils.llm_client import call_llm, parse_json_response
from backend.utils.salary_parse import parse_salary_range_from_text

PROFILE_PATH = Path("data/candidate_profile.json")
BATCH_SIZE = 10           # Jobs per LLM call


def _count_by_source_board(jobs: list[dict]) -> dict[str, int]:
    return dict(Counter((j.get("source_board") or "unknown") for j in jobs))


def _normalize_jd_keywords(raw) -> list[str]:
    """LLM output: 8–15 short strings; cap length for DB and UI."""
    if not raw:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s[:120]] if s else []
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        s = str(x).strip()[:120]
        if s and s not in out:
            out.append(s)
        if len(out) >= 15:
            break
    return out


def load_profile() -> dict:
    """Load candidate profile from disk."""
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Candidate profile not found at {PROFILE_PATH}. "
            "Copy the template and fill it in first."
        )
    return json.loads(PROFILE_PATH.read_text())


_FILTER_JSON_REPAIR_SYSTEM = (
    "You fix malformed JSON. Output ONLY a valid JSON array (no markdown, no prose). "
    "Each element must be an object with keys: index, score, verdict, reason, "
    "missing_skills, strengths, jd_keywords."
)


async def _score_batch(batch: list[dict], profile: dict, batch_num: int, total_batches: int) -> list[dict]:
    """Score a single batch of jobs via LLM. Returns list of scored job dicts."""
    logger.info(f"   Scoring batch {batch_num}/{total_batches} ({len(batch)} jobs)...")

    try:
        prompt = build_filter_prompt(batch, profile)
        response = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            system=FILTER_SYSTEM_PROMPT,
            max_tokens=4000,
            temperature=0.1,
            expect_json=True,
        )

        try:
            results = parse_json_response(response)
        except ValueError:
            repair_user = (
                "The following text was supposed to be ONLY a JSON array matching the schema. "
                "Return ONLY the corrected JSON array, same length as jobs implied, no markdown.\n\n"
                + response[:14_000]
            )
            logger.warning(f"   Batch {batch_num}: JSON parse failed — one repair attempt via LLM")
            repaired = await call_llm(
                messages=[{"role": "user", "content": repair_user}],
                system=_FILTER_JSON_REPAIR_SYSTEM,
                max_tokens=6000,
                temperature=0.0,
                expect_json=True,
            )
            results = parse_json_response(repaired)

        if not isinstance(results, list):
            raise ValueError(f"Expected list, got {type(results)}")

        scored = []
        for result in results:
            idx = result.get("index", 0)
            if idx >= len(batch):
                continue

            job = batch[idx].copy()
            job["ai_score"] = int(result.get("score", 5))
            job["ai_verdict"] = result.get("verdict", "MAYBE").upper()
            job["ai_reason"] = result.get("reason", "")
            job["ai_missing_skills"] = result.get("missing_skills", [])
            job["ai_strengths"] = result.get("strengths", [])
            job["jd_keywords"] = _normalize_jd_keywords(result.get("jd_keywords"))
            scored.append(job)

        return scored

    except Exception as e:
        logger.error(f"   Batch {batch_num} failed: {e}")
        fallback = []
        for job in batch:
            j = job.copy()
            j["ai_score"] = 5
            j["ai_verdict"] = "MAYBE"
            j["ai_reason"] = f"Scoring error — manual review recommended: {str(e)[:100]}"
            j["jd_keywords"] = []
            fallback.append(j)
        return fallback


def run_filter_agent(jobs: list[dict]) -> dict:
    """
    Main entry point. Score a list of raw scraped jobs.

    Uses asyncio.gather with CONCURRENT_BATCHES parallelism to speed up scoring.
    """
    if not jobs:
        logger.warning("Filter agent received empty job list")
        return {
            "apply": [],
            "maybe": [],
            "skip": [],
            "total_scored": 0,
            "instant_rejects": 0,
            "llm_calls": 0,
            "funnel_llm": {
                "candidates_by_source": {},
                "instant_reject_by_source": {},
                "apply_by_source": {},
                "maybe_by_source": {},
                "skip_by_source": {},
            },
        }

    profile = load_profile()
    logger.info(f"🤖 Filter agent starting — {len(jobs)} jobs to score")

    candidates, instant_rejects = pre_filter_by_keywords(jobs, profile)
    logger.info(f"   Pre-filter: {len(instant_rejects)} instant rejects, {len(candidates)} to LLM")

    batches = [candidates[i:i + BATCH_SIZE] for i in range(0, len(candidates), BATCH_SIZE)]
    total_batches = len(batches)
    logger.info(f"   {total_batches} batches of ~{BATCH_SIZE} (concurrency={max(1, int(getattr(settings, 'filter_llm_concurrent_batches', 2) or 2))})")

    scored = asyncio.run(_run_all_batches(batches, profile, total_batches))
    llm_calls = total_batches

    all_results = scored + instant_rejects
    all_results.sort(key=lambda x: x.get("ai_score", 0), reverse=True)

    apply = [j for j in all_results if j.get("ai_verdict") == "APPLY"]
    maybe = [j for j in all_results if j.get("ai_verdict") == "MAYBE"]
    skip  = [j for j in all_results if j.get("ai_verdict") == "SKIP"]

    logger.info(
        f"✅ Filter complete: {len(apply)} APPLY, {len(maybe)} MAYBE, "
        f"{len(skip)} SKIP | {llm_calls} LLM calls"
    )

    return {
        "apply": apply,
        "maybe": maybe,
        "skip": skip,
        "total_scored": len(all_results),
        "instant_rejects": len(instant_rejects),
        "llm_calls": llm_calls,
        "funnel_llm": {
            "candidates_by_source": _count_by_source_board(candidates),
            "instant_reject_by_source": _count_by_source_board(instant_rejects),
            "apply_by_source": _count_by_source_board(apply),
            "maybe_by_source": _count_by_source_board(maybe),
            "skip_by_source": _count_by_source_board(skip),
        },
    }


async def _run_all_batches(batches: list[list[dict]], profile: dict, total_batches: int) -> list[dict]:
    """Process all batches with bounded concurrency using a semaphore."""
    concurrent = max(1, int(getattr(settings, "filter_llm_concurrent_batches", 2) or 2))
    stagger_ms = max(0, int(getattr(settings, "filter_llm_batch_stagger_ms", 0) or 0))
    sem = asyncio.Semaphore(concurrent)

    async def _limited(batch, num):
        async with sem:
            if stagger_ms and num > 1:
                await asyncio.sleep((stagger_ms / 1000.0) * (num - 1))
            return await _score_batch(batch, profile, num, total_batches)

    tasks = [_limited(batch, i + 1) for i, batch in enumerate(batches)]
    results = await asyncio.gather(*tasks)
    flat = []
    for r in results:
        flat.extend(r)
    return flat


JOB_DESCRIPTION_DB_MAX = 50_000
UPSERT_CHUNK_SIZE = 200


def save_scored_jobs_to_db(scored_jobs: list[dict]) -> dict:
    """
    Write scored jobs to Supabase jobs table.
    Skips duplicates using dedup_hash unique constraint.
    """
    client = db()
    inserted = 0
    skipped = 0
    errors = 0
    rows: list[dict] = []
    for job in scored_jobs:
        try:
            desc_raw = job.get("description") or ""
            salary_min = _safe_int(job.get("salary_min"))
            salary_max = _safe_int(job.get("salary_max"))
            if salary_min is None and salary_max is None:
                sm, sx = parse_salary_range_from_text(desc_raw)
                if sm is not None:
                    salary_min = sm
                if sx is not None:
                    salary_max = sx

            rows.append({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "description": desc_raw[:JOB_DESCRIPTION_DB_MAX],
                "job_url": job.get("job_url", ""),
                "source_board": job.get("source_board", "unknown"),
                "ats_platform": job.get("ats_platform"),
                "dedup_hash": job.get("dedup_hash", ""),
                "ai_score": job.get("ai_score"),
                "ai_verdict": job.get("ai_verdict"),
                "ai_reason": job.get("ai_reason"),
                "jd_keywords": _normalize_jd_keywords(job.get("jd_keywords")),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "is_remote": bool(job.get("is_remote", False)),
                "posted_at": _sanitize_posted_at(job.get("posted_at")),
            })
        except Exception as e:
            logger.error(f"Row build error for {job.get('company')} / {job.get('title')}: {e}")
            errors += 1

    for i in range(0, len(rows), UPSERT_CHUNK_SIZE):
        chunk = rows[i:i + UPSERT_CHUNK_SIZE]
        try:
            result = client.table("jobs").upsert(
                chunk,
                on_conflict="dedup_hash",
                ignore_duplicates=True,
            ).execute()
            inserted_chunk = len(result.data or [])
            inserted += inserted_chunk
            skipped += max(0, len(chunk) - inserted_chunk)
        except Exception as e:
            logger.error(f"DB chunk write error ({i}:{i + len(chunk)}): {e}")
            errors += len(chunk)

    logger.info(f"💾 DB write: {inserted} inserted, {skipped} duplicates skipped, {errors} errors")
    return {"inserted": inserted, "skipped_duplicates": skipped, "errors": errors}


def _safe_int(val) -> int | None:
    """Convert salary value to int safely."""
    try:
        return int(float(str(val).replace(",", "").replace("$", "")))
    except (ValueError, TypeError):
        return None


def _sanitize_posted_at(val) -> str | None:
    """Normalize posted_at into an ISO-8601 string, or None if it's invalid."""
    if val is None:
        return None

    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

    if isinstance(val, int | float):
        # Handle NaN floats.
        try:
            if isinstance(val, float) and math.isnan(val):
                return None
        except Exception:
            return None

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None

        lower = s.lower()
        if lower in ("nan", "null", "none"):
            return None

        # Normalize common suffixes.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.isoformat()
        except Exception:
            pass

        try:
            dt = dateparser.parse(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.isoformat()
        except Exception:
            return None

    # Unknown type: safest to drop.
    return None
