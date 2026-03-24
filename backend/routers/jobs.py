"""
backend/routers/jobs.py
========================
FastAPI routes for job listings.

GET  /api/jobs              — paginated job list with filters (+ total)
GET  /api/jobs/stats        — counts by verdict, source, etc.
GET  /api/jobs/:id          — single job detail
POST /api/jobs/scrape       — trigger scrape (Celery if available, else in-process)
POST /api/jobs/:id/verdict  — manually override AI verdict
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.db.client import db
from backend.errors import INTERNAL_ERROR, log_internal_error
from backend.utils.salary_parse import parse_salary_range_from_text

router = APIRouter()

_SEARCH_MAX_LEN = 120

# List endpoint omits large text fields unless include_description=true
_JOB_LIST_COLUMNS_SLIM = (
    "id,title,company,location,job_url,source_board,ats_platform,posted_at,scraped_at,"
    "is_remote,ai_score,ai_verdict,jd_keywords,salary_min,salary_max,salary_currency,"
    "requires_clearance,requires_sponsorship,company_size,glassdoor_rating,"
    "has_recent_layoffs,has_mutual_connection,mutual_connection_name"
)


def _enrich_job_salary_fields(job: dict | None) -> dict | None:
    """Fill salary_min/max from description when DB columns are empty (legacy rows)."""
    if not job:
        return job
    if job.get("salary_min") is not None or job.get("salary_max") is not None:
        return job
    sm, sx = parse_salary_range_from_text(job.get("description") or "")
    if sm is None and sx is None:
        return job
    enriched = dict(job)
    if sm is not None:
        enriched["salary_min"] = sm
    if sx is not None:
        enriched["salary_max"] = sx
    return enriched


def _sanitize_search_term(raw: str | None) -> str | None:
    """Strip ILIKE wildcards and trim length so user input cannot broaden the pattern."""
    if not raw:
        return None
    s = raw.strip()[:_SEARCH_MAX_LEN]
    if not s:
        return None
    s = re.sub(r"[%_\\]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


# ── Models ────────────────────────────────────────────────────────────────


class VerdictOverride(BaseModel):
    verdict: str  # APPLY | MAYBE | SKIP
    reason: str | None = None


class ScrapeRequest(BaseModel):
    dry_run: bool = False


class ManualJobCreate(BaseModel):
    title: str
    company: str
    job_url: str
    description: str | None = None
    location: str | None = None
    is_remote: bool | None = None
    tailor: bool = False


# ── Query helpers ─────────────────────────────────────────────────────────


def _apply_job_filters(
    query,
    verdict: str | None,
    source: str | None,
    search: str | None,
    min_score: int,
    is_remote: bool | None,
    since_days: int | None = None,
):
    if verdict:
        # `ai_verdict` casing in DB is not guaranteed (e.g. `apply` vs `APPLY`).
        # Use case-insensitive matching so verdict filters work reliably.
        v = (verdict or "").strip()
        if v:
            query = query.ilike("ai_verdict", v)
    if source:
        query = query.eq("source_board", source)
    if min_score:
        query = query.gte("ai_score", min_score)
    if is_remote is not None:
        query = query.eq("is_remote", is_remote)
    if search:
        safe = _sanitize_search_term(search)
        if safe:
            query = query.or_(f"title.ilike.%{safe}%,company.ilike.%{safe}%")
    if since_days is not None and since_days > 0:
        # Match listing date (posted_at), not scrape ingest time. Fallback to scraped_at when posted_at is unknown.
        cutoff_dt = datetime.now(UTC) - timedelta(days=since_days)
        cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        q = f'"{cutoff}"'
        query = query.or_(f"posted_at.gte.{q},and(posted_at.is.null,scraped_at.gte.{q})")
    return query


_stats_rpc_fallback_logged = False
_analytics_rpc_fallback_logged = False


def _count_jobs(
    client,
    verdict: str | None = None,
    source: str | None = None,
    search: str | None = None,
    min_score: int = 0,
    is_remote: bool | None = None,
    since_days: int | None = None,
) -> int:
    q = client.table("jobs").select("id", count="exact", head=True)
    q = _apply_job_filters(q, verdict, source, search, min_score, is_remote, since_days)
    r = q.execute()
    return r.count if r.count is not None else 0


def _stats_from_rpc(client) -> dict[str, Any] | None:
    try:
        r = client.rpc("job_dashboard_stats").execute()
        raw = r.data
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            return None
        bv = raw.get("by_verdict") or {}
        if not isinstance(bv, dict):
            bv = {}
        bs = raw.get("by_source") or {}
        if not isinstance(bs, dict):
            bs = {}

        # Normalize verdict keys to uppercase in case the RPC returns lowercase keys.
        bv_upper: dict[str, int] = {}
        for k, v in bv.items():
            if k is None:
                continue
            try:
                bv_upper[str(k).upper()] = int(v or 0)
            except Exception:
                bv_upper[str(k).upper()] = 0

        logger.info(
            "job_dashboard_stats RPC returned: "
            f"total={raw.get('total', 0)} remote_count={raw.get('remote_count', 0)} "
            f"by_verdict_keys={list(bv.keys())} "
            f"APPLY={bv_upper.get('APPLY', 0)} MAYBE={bv_upper.get('MAYBE', 0)} SKIP={bv_upper.get('SKIP', 0)}"
        )

        return {
            "total": int(raw.get("total", 0)),
            "by_verdict": {
                "APPLY": int(bv_upper.get("APPLY", 0)),
                "MAYBE": int(bv_upper.get("MAYBE", 0)),
                "SKIP": int(bv_upper.get("SKIP", 0)),
            },
            "by_source": {str(k): int(v) for k, v in bs.items()},
            "avg_score": float(raw.get("avg_score", 0) or 0),
            "remote_count": int(raw.get("remote_count", 0)),
        }
    except Exception:
        global _stats_rpc_fallback_logged
        if not _stats_rpc_fallback_logged:
            logger.info(
                "Job stats: using SQL count fallback (RPC job_dashboard_stats not in DB). "
                "Paste the job_dashboard_stats() block from backend/db/schema.sql into "
                "Supabase SQL Editor and run once — then reload the API."
            )
            _stats_rpc_fallback_logged = True
        return None


def _stats_fallback(client) -> dict[str, Any]:
    def _count(**kwargs) -> int:
        return _count_jobs(client, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        fut_total = pool.submit(_count)
        fut_apply = pool.submit(_count, verdict="APPLY")
        fut_maybe = pool.submit(_count, verdict="MAYBE")
        fut_skip = pool.submit(_count, verdict="SKIP")
        fut_remote = pool.submit(_count, is_remote=True)
        total = fut_total.result()
        verdict_counts = {
            "APPLY": fut_apply.result(),
            "MAYBE": fut_maybe.result(),
            "SKIP": fut_skip.result(),
        }
        remote_count = fut_remote.result()

    by_source: dict[str, int] = {}
    avg_score = 0.0

    if total <= 8000:
        rows = client.table("jobs").select("source_board, ai_score").execute().data or []
        scores = [j["ai_score"] for j in rows if j.get("ai_score") is not None]
        if scores:
            avg_score = round(sum(scores) / len(scores), 1)
        for j in rows:
            s = j.get("source_board") or "unknown"
            by_source[s] = by_source.get(s, 0) + 1

    return {
        "total": total,
        "by_verdict": verdict_counts,
        "by_source": by_source,
        "avg_score": avg_score,
        "remote_count": remote_count,
    }


def _analytics_rows_since(client, cutoff_iso: str, max_rows: int) -> list[dict]:
    """Paginate through jobs for time-series (PostgREST default page size is 1000)."""
    rows: list[dict] = []
    offset = 0
    batch = 1000
    while len(rows) < max_rows:
        take = min(batch, max_rows - len(rows))
        result = (
            client.table("jobs")
            .select("scraped_at, ai_verdict")
            .gte("scraped_at", cutoff_iso)
            .order("scraped_at", desc=False)
            .range(offset, offset + take - 1)
            .execute()
        )
        chunk = result.data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < take:
            break
        offset += take
    return rows


def _analytics_from_rpc(client, days: int) -> dict[str, Any] | None:
    try:
        r = client.rpc("job_analytics_series", {"p_days": days}).execute()
        raw = r.data
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            return None
        series = raw.get("series")
        if not isinstance(series, list):
            return None
        return {
            "series": series,
            "rows_used": int(raw.get("rows_used", 0) or 0),
            "truncated": bool(raw.get("truncated", False)),
        }
    except Exception:
        global _analytics_rpc_fallback_logged
        if not _analytics_rpc_fallback_logged:
            logger.info(
                "Job analytics: using row-scan fallback (RPC job_analytics_series not in DB). "
                "Apply the job_analytics_series() block from backend/db/schema.sql in Supabase SQL Editor."
            )
            _analytics_rpc_fallback_logged = True
        return None


# ── Routes (specific paths before /{job_id}) ──────────────────────────────


@router.get("/analytics")
async def get_job_analytics(
    days: int = Query(30, ge=1, le=90, description="Rolling window in days"),
):
    """Daily job counts by verdict (scraped_at) for charts. RPC aggregates in DB when available."""
    try:
        client = db()
        from_rpc = _analytics_from_rpc(client, days)
        if from_rpc is not None:
            return {
                "days": days,
                "series": from_rpc["series"],
                "rows_used": from_rpc["rows_used"],
                "truncated": from_rpc["truncated"],
            }

        cutoff = datetime.now(UTC) - timedelta(days=days)
        cutoff_iso = cutoff.replace(microsecond=0).isoformat()
        rows = _analytics_rows_since(client, cutoff_iso, max_rows=50_000)

        by_day: dict[str, dict[str, int]] = {}
        for row in rows:
            sa = row.get("scraped_at")
            if not sa:
                continue
            day = sa[:10]
            if day not in by_day:
                by_day[day] = {"total": 0, "APPLY": 0, "MAYBE": 0, "SKIP": 0}
            by_day[day]["total"] += 1
            v = (row.get("ai_verdict") or "MAYBE").upper()
            if v in by_day[day]:
                by_day[day][v] += 1

        series = sorted(
            ({"date": d, **counts} for d, counts in by_day.items()),
            key=lambda x: x["date"],
        )
        return {
            "days": days,
            "series": series,
            "rows_used": len(rows),
            "truncated": len(rows) >= 50_000,
        }
    except Exception as e:
        log_internal_error("GET /jobs/analytics", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("/stats")
async def get_job_stats():
    """Aggregated dashboard stats (RPC when available, else count-based fallback)."""
    try:
        client = db()
        stats = _stats_from_rpc(client)
        if stats is None:
            stats = _stats_fallback(client)
        else:
            # If the RPC is partially working (e.g. verdict filters mismatched due to casing),
            # fall back to the Python aggregation.
            total = int(stats.get("total") or 0)
            by_verdict = stats.get("by_verdict") or {}
            verdict_sum = sum(int(by_verdict.get(k) or 0) for k in ("APPLY", "MAYBE", "SKIP"))
            if total > 0 and verdict_sum == 0:
                logger.warning(
                    "job_dashboard_stats returned zero verdict counts; using fallback aggregation"
                )
                stats = _stats_fallback(client)
        return stats
    except Exception as e:
        log_internal_error("GET /jobs/stats", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.post("/scrape")
async def trigger_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    """Queue scrape on Celery when the broker is reachable; otherwise run in-process."""

    dry = body.dry_run

    def _run_sync():
        from backend.tasks import execute_scrape_pipeline

        try:
            result = execute_scrape_pipeline(dry_run=dry)
            logger.info(f"In-process scrape complete: {result}")
        except Exception as e:
            logger.error(f"In-process scrape failed: {e}")

    try:
        from backend.tasks import celery_app

        async_result = celery_app.send_task(
            "backend.tasks.scrape_and_filter",
            kwargs={"dry_run": dry},
        )
        return {
            "status": "queued",
            "task_id": str(async_result.id),
            "dry_run": dry,
            "message": "Scrape queued on Celery. Poll GET /api/agent-runs for progress.",
        }
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}); scrape will run in-process after response returns")
        background_tasks.add_task(_run_sync)
        return {
            "status": "started",
            "task_id": None,
            "dry_run": dry,
            "message": "Scrape running in the API process. Watch GET /api/agent-runs for the scraper row.",
        }


@router.post("/manual")
async def create_manual_job(body: ManualJobCreate, background_tasks: BackgroundTasks):
    """Manually add a job (paste link + description) and optionally trigger resume tailoring."""
    client = db()

    dedup = hashlib.sha256(f"{body.company}|{body.title}|{body.location or ''}".lower().encode()).hexdigest()
    sm, sx = parse_salary_range_from_text(body.description or "")
    row = {
        "title": body.title,
        "company": body.company,
        "job_url": body.job_url,
        "description": body.description,
        "location": body.location,
        "is_remote": body.is_remote or False,
        "source_board": "manual",
        "dedup_hash": dedup,
        "ai_verdict": "APPLY",
        "ai_score": 8,
        "ai_reason": "Manually added by user",
    }
    if sm is not None:
        row["salary_min"] = sm
    if sx is not None:
        row["salary_max"] = sx
    try:
        result = client.table("jobs").upsert(row, on_conflict="dedup_hash").execute()
        job_row = result.data[0] if result.data else None
        if not job_row:
            raise HTTPException(status_code=500, detail="Failed to insert job")
    except HTTPException:
        raise
    except Exception as e:
        if "duplicate" in str(e).lower() or "conflict" in str(e).lower():
            existing = client.table("jobs").select("*").eq("dedup_hash", dedup).single().execute()
            job_row = existing.data
        else:
            log_internal_error("POST /jobs/manual upsert", e)
            raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None

    tailor_result = None
    if body.tailor and job_row:
        try:
            import asyncio

            from backend.agents.resume_agent import run_resume_agent
            tailor_result = await asyncio.to_thread(run_resume_agent, job_row)
        except Exception as e:
            logger.warning(f"Auto-tailor after manual add failed: {e}")

    return {
        "success": True,
        "job": job_row,
        "tailor_result": tailor_result,
    }


@router.get("")
async def get_jobs(
    verdict: str | None = Query(None, description="APPLY | MAYBE | SKIP"),
    source: str | None = Query(None),
    search: str | None = Query(None),
    min_score: int = Query(0, ge=0, le=10),
    is_remote: bool | None = Query(None),
    since_days: int | None = Query(None, ge=1, le=90, description="Only jobs from last N days"),
    include_description: bool = Query(
        False,
        description="Include full description (large); board/search UIs should pass true",
    ),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated job listings with optional filters."""
    try:
        client = db()

        cols = "*" if include_description else _JOB_LIST_COLUMNS_SLIM
        query = client.table("jobs").select(cols, count="exact")
        query = _apply_job_filters(query, verdict, source, search, min_score, is_remote, since_days)
        result = (
            query.order("scraped_at", desc=True)
            .order("ai_score", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        rows = result.data or []
        if include_description:
            rows = [_enrich_job_salary_fields(r) for r in rows]
        total = getattr(result, "count", None)
        total = int(total) if total is not None else len(rows)
        return {
            "jobs": rows,
            "count": len(rows),
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < total,
        }

    except Exception as e:
        log_internal_error("GET /jobs", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get a single job by ID."""
    try:
        client = db()
        result = client.table("jobs").select("*").eq("id", job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        return _enrich_job_salary_fields(result.data)

    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("GET /jobs/{job_id}", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.post("/{job_id}/verdict")
async def override_verdict(job_id: str, body: VerdictOverride):
    """Manually override the AI verdict for a job."""
    if body.verdict not in ("APPLY", "MAYBE", "SKIP"):
        raise HTTPException(status_code=400, detail="verdict must be APPLY, MAYBE, or SKIP")

    try:
        client = db()
        update = {"ai_verdict": body.verdict}
        if body.reason:
            update["ai_reason"] = f"[Manual] {body.reason}"

        result = client.table("jobs").update(update).eq("id", job_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        return {"success": True, "job_id": job_id, "new_verdict": body.verdict}

    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("POST /jobs/{job_id}/verdict", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None
