"""
GET /api/admin/ops-summary — operational snapshot for Admin UI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from backend.db.client import db
from backend.errors import INTERNAL_ERROR, log_internal_error

router = APIRouter()


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@router.get("/ops-summary")
async def ops_summary():
    try:
        client = db()
        latest = (
            client.table("agent_runs")
            .select("id, started_at, metadata")
            .eq("agent_name", "scraper")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_row = (latest.data or [None])[0] or {}
        meta = latest_row.get("metadata") if isinstance(latest_row.get("metadata"), dict) else {}

        funnel = meta.get("funnel_by_source") if isinstance(meta.get("funnel_by_source"), dict) else {}
        by_source = []
        for source, row in sorted(funnel.items()):
            if not isinstance(row, dict):
                continue
            by_source.append(
                {
                    "source": source,
                    "raw": _to_int(row.get("raw")),
                    "post_dedup": _to_int(row.get("post_dedup")),
                    "apply": _to_int(row.get("apply")),
                    "maybe": _to_int(row.get("maybe")),
                    "skip": _to_int(row.get("skip")),
                }
            )

        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        apps_rows = (
            client.table("applications")
            .select("id")
            .gte("updated_at", since)
            .not_.is_("cover_letter", "null")
            .limit(500)
            .execute()
        ).data or []
        app_ids = [str(r.get("id")) for r in apps_rows if r.get("id")]
        prepare_runs_24h = len(app_ids)

        db_reused_24h = 0
        apify_called_24h = 0
        emails_enriched_24h = 0
        if app_ids:
            try:
                links = (
                    client.table("application_contacts")
                    .select("application_id, source_actor, contacts(source, email_verified)")
                    .in_("application_id", app_ids)
                    .limit(3000)
                    .execute()
                ).data or []
                apify_apps: set[str] = set()
                for row in links:
                    app_id = str(row.get("application_id") or "")
                    source_actor = str(row.get("source_actor") or "").strip()
                    contact = row.get("contacts") or {}
                    source = str(contact.get("source") or "").strip().lower()
                    email_verified = bool(contact.get("email_verified"))
                    if source == "db_fallback":
                        db_reused_24h += 1
                    if source_actor:
                        apify_apps.add(app_id)
                    if email_verified:
                        emails_enriched_24h += 1
                apify_called_24h = len(apify_apps)
            except Exception:
                # application_contacts table may not exist yet in every environment.
                pass

        return {
            "summary": {
                "latest_scrape_at": latest_row.get("started_at"),
                "scraped_raw": _to_int(meta.get("scraped_raw")),
                "unique_new": _to_int(meta.get("unique_new")),
                "dedup_removed": _to_int(meta.get("dedup_removed")),
                "stale_dropped": _to_int(meta.get("stale_dropped")),
                "recency_hours": _to_int(meta.get("recency_hours")),
                "inserted_to_db": _to_int(meta.get("inserted_to_db")),
                "by_source": by_source,
                "prepare_runs_24h": prepare_runs_24h,
                "db_reused_24h": db_reused_24h,
                "apify_called_24h": apify_called_24h,
                "emails_enriched_24h": emails_enriched_24h,
            }
        }
    except Exception as e:
        log_internal_error("GET /admin/ops-summary", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None
