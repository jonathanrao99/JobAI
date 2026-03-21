"""
backend/db/client.py
====================
Supabase client singleton. Import `db` anywhere in the backend.

Works in FastAPI (after init_db), Celery workers, and CLI without requiring
the async lifespan — the client is created lazily on first use.
"""

import threading

from supabase import create_client
from loguru import logger

from backend.config import settings

_client = None
_lock = threading.Lock()


def _ensure_client():
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is None:
            _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


async def init_db():
    """FastAPI lifespan: create client and verify connectivity."""
    client = _ensure_client()
    try:
        client.table("agent_runs").select("id").limit(1).execute()
        logger.info("✅ Supabase connection verified")
    except Exception as e:
        logger.warning(f"⚠️  Supabase connectivity check failed: {e}")
        logger.warning("   Check your SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")


def get_db():
    return _ensure_client()


# Convenience alias (callable: db())
db = get_db
