"""
backend/routers/resumes.py
===========================
POST /api/resumes/tailor          — tailor resume for a specific job_id
GET  /api/resumes                  — list all resume versions
GET  /api/resumes/:id              — single resume version detail
GET  /api/resumes/:id/download     — download pdf or tex
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.db.client import db
from backend.errors import INTERNAL_ERROR, log_internal_error

REPO_ROOT = Path(__file__).resolve().parents[2]

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "tex": "text/plain",
}

router = APIRouter()


class TailorRequest(BaseModel):
    job_id: str


@router.post("/tailor")
async def tailor_resume(body: TailorRequest):
    """Tailor the base resume for a specific APPLY job."""
    client = db()

    try:
        result = client.table("jobs").select("*").eq("id", body.job_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")
        job = result.data
    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("tailor_resume fetch job", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None

    try:
        import asyncio

        from backend.agents.resume_agent import run_resume_agent

        result = await asyncio.to_thread(run_resume_agent, job)

        return {
            "success": True,
            "resume_id": result.get("resume_id"),
            "job_id": body.job_id,
            "job_title": job.get("title"),
            "company": job.get("company"),
            "pdf_path": result.get("pdf_path"),
            "tex_path": result.get("file_path"),
            "diff_summary": result["diff_summary"],
            "keywords_added": result["keywords_added"],
            "jd_keywords": result.get("jd_keywords", []),
            "ats_score_estimate": result.get("ats_score_estimate"),
            "skills_line": result.get("skills_line", ""),
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail="Required resume or profile file is missing on the server.",
        ) from None
    except Exception as e:
        log_internal_error("tailor_resume run_resume_agent", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("")
async def list_resumes(
    job_id: str | None = Query(None, description="Filter by job UUID"),
    limit: int = 50,
    offset: int = 0,
):
    """List resume versions; optional filter by job_id."""
    try:
        client = db()
        q = (
            client.table("resumes")
            .select("*, jobs(title, company, ai_score)")
            .order("created_at", desc=True)
        )
        if job_id:
            q = q.eq("job_id", job_id)
        result = q.range(offset, offset + limit - 1).execute()
        return {"resumes": result.data, "count": len(result.data)}
    except Exception as e:
        log_internal_error("GET /resumes", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("/{resume_id}")
async def get_resume(resume_id: str):
    """Get a single resume version."""
    try:
        client = db()
        result = (
            client.table("resumes")
            .select("*, jobs(title, company, description, ai_score, job_url)")
            .eq("id", resume_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Resume not found")
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("GET /resumes/{id}", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("/{resume_id}/download")
async def download_resume(
    resume_id: str,
    format: str = Query("pdf", pattern="^(pdf|tex)$"),
):
    """Download a tailored resume as PDF or TEX."""
    client = db()
    try:
        result = (
            client.table("resumes")
            .select("file_path")
            .eq("id", resume_id)
            .single()
            .execute()
        )
    except Exception as e:
        log_internal_error("GET /resumes/{id}/download meta", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None

    if not result.data or not result.data.get("file_path"):
        raise HTTPException(status_code=404, detail="Resume not found")

    base = Path(result.data["file_path"])
    target = base.with_suffix(f".{format}")
    full_path = REPO_ROOT / target

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Requested resume file is not available.")

    # PDF: inline disposition so browsers can render inside <iframe> (attachment often shows a blank box).
    disposition = "inline" if format == "pdf" else "attachment"
    return FileResponse(
        path=str(full_path),
        media_type=_MEDIA_TYPES.get(format, "application/octet-stream"),
        filename=full_path.name,
        content_disposition_type=disposition,
    )
