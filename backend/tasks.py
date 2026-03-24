"""
backend/tasks.py
=================
Celery task definitions + beat schedule.

Start worker:  celery -A backend.tasks worker --loglevel=info
Start beat:    celery -A backend.tasks beat --loglevel=info
With both:     celery -A backend.tasks worker --beat --loglevel=info
Monitor:       celery -A backend.tasks flower --port=5555
"""

from datetime import UTC, datetime

from celery import Celery
from celery.schedules import crontab
from loguru import logger

from backend.config import settings


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

# ── Celery app ────────────────────────────────────────────────────────────

celery_app = Celery(
    "job_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Chicago",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ── Beat schedule (cron) ─────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    "scrape-jobs-weekday": {
        "task": "backend.tasks.scrape_and_filter",
        "schedule": crontab(hour="0,4,8,12,16,20", minute="0", day_of_week="1-5"),
    },
    "scrape-jobs-weekend": {
        "task": "backend.tasks.scrape_and_filter",
        "schedule": crontab(hour="8,16", minute="0", day_of_week="6,0"),
    },
    "purge-old-jobs-nightly": {
        "task": "backend.tasks.purge_old_jobs",
        "schedule": crontab(hour="0", minute="0"),
    },
    "ghost-stale-applications": {
        "task": "backend.tasks.ghost_stale_applications",
        "schedule": crontab(hour="0", minute="5"),
    },
}


# ── Scrape pipeline (shared by Celery + in-process fallback) ──────────────


def execute_scrape_pipeline(dry_run: bool = False) -> dict:
    """Insert agent_run, scrape → filter → store, update agent_run."""
    from backend.agents.scraper_agent import run_scraper_agent
    from backend.db.client import db

    client = db()
    run_record = client.table("agent_runs").insert({
        "agent_name": "scraper",
        "status": "running",
    }).execute()

    run_id = run_record.data[0]["id"] if run_record.data else None

    try:
        result = run_scraper_agent(dry_run=dry_run)

        if run_id:
            client.table("agent_runs").update({
                "status": "completed",
                "completed_at": _utc_now_iso(),
                "items_processed": result.get("scraped_raw", 0),
                "items_succeeded": result.get("inserted_to_db", 0),
                "metadata": result,
            }).eq("id", run_id).execute()

        return result

    except Exception as e:
        logger.error(f"execute_scrape_pipeline failed: {e}")

        if run_id:
            client.table("agent_runs").update({
                "status": "failed",
                "completed_at": _utc_now_iso(),
                "error_message": str(e),
            }).eq("id", run_id).execute()

        raise


# ── Tasks ─────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="backend.tasks.scrape_and_filter", max_retries=2)
def scrape_and_filter(self, dry_run: bool = False):
    """Full scrape → filter → store pipeline."""
    try:
        return execute_scrape_pipeline(dry_run=dry_run)
    except Exception as e:
        raise self.retry(exc=e, countdown=300) from None


@celery_app.task(name="backend.tasks.purge_old_jobs")
def purge_old_jobs():
    """Delete jobs older than 7 days that have no application."""
    from backend.db.client import db

    client = db()
    try:
        client.rpc("purge_old_jobs").execute()
        logger.info("✅ Purged old jobs (>7 days, no application)")
    except Exception as e:
        logger.error(f"purge_old_jobs task failed: {e}")


@celery_app.task(name="backend.tasks.ghost_stale_applications")
def ghost_stale_applications():
    """Mark applications with no activity for 30 days as ghosted."""
    from backend.db.client import db

    client = db()
    try:
        client.rpc("auto_ghost_stale_applications").execute()
        logger.info("✅ Ghosted stale applications")
    except Exception as e:
        logger.error(f"Ghost task failed: {e}")
