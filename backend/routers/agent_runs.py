"""
GET /api/agent-runs — recent scraper / agent execution history (agent_runs table).
"""

from fastapi import APIRouter, HTTPException, Query

from backend.db.client import db
from backend.errors import INTERNAL_ERROR, log_internal_error

router = APIRouter()


@router.get("")
async def list_agent_runs(
    limit: int = Query(30, le=100),
    agent_name: str | None = Query(None, description="Filter e.g. scraper"),
):
    try:
        client = db()
        q = client.table("agent_runs").select("*").order("started_at", desc=True).limit(limit)
        if agent_name:
            q = q.eq("agent_name", agent_name)
        result = q.execute()
        return {"runs": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        log_internal_error("GET /agent-runs", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None
