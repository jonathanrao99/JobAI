"""
backend/routers/applications.py
================================
CRUD for application tracking.

POST /api/applications              — create application from a job_id
GET  /api/applications              — list applications (filterable by status)
PATCH /api/applications/:id/status  — update application status
GET  /api/applications/:id          — single application detail
DELETE /api/applications/:id        — remove an application
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.db.client import db

router = APIRouter()


class CreateApplication(BaseModel):
    job_id: str
    notes: Optional[str] = None


class UpdateStatus(BaseModel):
    status: str  # queued | applied | response_received | phone_screen | ...
    notes: Optional[str] = None


VALID_STATUSES = {
    "queued", "applied", "viewed", "response_received",
    "phone_screen", "technical", "final_round", "offer",
    "rejected", "ghosted", "manual_required", "skipped",
}


@router.post("")
async def create_application(body: CreateApplication):
    """Create an application record for a job."""
    client = db()
    try:
        job = client.table("jobs").select("id, title, company").eq("id", body.job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        row = {"job_id": body.job_id, "status": "queued"}
        if body.notes:
            row["notes"] = body.notes
        result = client.table("applications").insert(row).execute()
        app_row = result.data[0] if result.data else row
        return {"success": True, "application": app_row}
    except Exception as e:
        if "unique_application_per_job" in str(e):
            raise HTTPException(status_code=409, detail="Application already exists for this job")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List applications with joined job info."""
    try:
        client = db()
        q = (
            client.table("applications")
            .select("*, jobs(id, title, company, location, job_url, source_board, ai_score, ai_verdict, is_remote)")
            .order("created_at", desc=True)
        )
        if status and status in VALID_STATUSES:
            q = q.eq("status", status)
        result = q.range(offset, offset + limit - 1).execute()
        rows = result.data or []
        return {"applications": rows, "count": len(rows)}
    except Exception as e:
        logger.error(f"GET /applications error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{application_id}")
async def get_application(application_id: str):
    try:
        client = db()
        result = (
            client.table("applications")
            .select("*, jobs(*, resumes(id, version_name, file_path, created_at))")
            .eq("id", application_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{application_id}/status")
async def update_application_status(application_id: str, body: UpdateStatus):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    try:
        client = db()
        update: dict = {"status": body.status}
        if body.notes:
            update["notes"] = body.notes
        if body.status == "applied":
            update["applied_at"] = "now()"

        result = client.table("applications").update(update).eq("id", application_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"success": True, "application": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{application_id}")
async def delete_application(application_id: str):
    try:
        client = db()
        result = client.table("applications").delete().eq("id", application_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
