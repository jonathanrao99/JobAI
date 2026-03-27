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

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.db.client import db
from backend.errors import INTERNAL_ERROR, log_internal_error
from backend.utils.application_materials_storage import (
    is_missing_materials_columns_error,
    merge_notes_with_materials_json,
)

router = APIRouter()


class CreateApplication(BaseModel):
    job_id: str
    notes: str | None = None


class UpdateStatus(BaseModel):
    status: str  # queued | applied | response_received | phone_screen | ...
    notes: str | None = None


VALID_STATUSES = {
    "queued", "applied", "viewed", "response_received",
    "phone_screen", "technical", "final_round", "offer",
    "rejected", "ghosted", "manual_required", "skipped",
}


def _is_missing_app_contacts_error(err: Exception) -> bool:
    msg = str(err).lower()
    return "application_contacts" in msg and ("could not find" in msg or "does not exist" in msg)


def _normalize_contact_key(value: str) -> str:
    return (value or "").strip().lower()


def _persist_application_contacts(
    client,
    *,
    application_id: str,
    company: str,
    contacts: list[dict[str, Any]],
) -> int:
    """Upsert contacts and refresh application_contacts links. Returns linked count."""
    if not contacts:
        return 0

    try:
        client.table("application_contacts").select("id").limit(1).execute()
    except Exception as e:
        if _is_missing_app_contacts_error(e):
            logger.warning(
                "application_contacts table missing; skipping contact links. "
                "Run backend/db/migrations/add_application_contacts.sql."
            )
            return 0
        raise

    existing_rows = (
        client.table("contacts")
        .select("id, name, company, linkedin_url, email, do_not_contact")
        .eq("company", company)
        .limit(500)
        .execute()
    ).data or []

    by_linkedin: dict[str, dict[str, Any]] = {}
    by_email: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        li = _normalize_contact_key(row.get("linkedin_url") or "")
        em = _normalize_contact_key(row.get("email") or "")
        if li:
            by_linkedin[li] = row
        if em:
            by_email[em] = row

    # Refresh links per prepare run so ranking remains current.
    client.table("application_contacts").delete().eq("application_id", application_id).execute()

    links: list[dict[str, Any]] = []
    for idx, c in enumerate(contacts, start=1):
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        li = _normalize_contact_key(c.get("linkedin_url") or "")
        em = _normalize_contact_key(c.get("email") or "")
        existing = (li and by_linkedin.get(li)) or (em and by_email.get(em))
        if existing and existing.get("do_not_contact"):
            continue

        contact_id: str
        if existing:
            contact_id = existing["id"]
            updates: dict[str, Any] = {}
            if not existing.get("linkedin_url") and li:
                updates["linkedin_url"] = li
            if not existing.get("email") and em:
                updates["email"] = em
            if updates:
                client.table("contacts").update(updates).eq("id", contact_id).execute()
        else:
            row = {
                "name": name,
                "title": str(c.get("title") or "").strip(),
                "company": company,
                "department": str(c.get("department") or "").strip() or None,
                "seniority": str(c.get("seniority") or "").strip() or None,
                "linkedin_url": li or None,
                "email": em or None,
                "email_verified": bool(c.get("email_verified")),
                "source": "linkedin_search",
            }
            created = client.table("contacts").insert(row).execute()
            if not created.data:
                continue
            contact_id = created.data[0]["id"]
            created_row = created.data[0]
            if li:
                by_linkedin[li] = created_row
            if em:
                by_email[em] = created_row

        links.append(
            {
                "application_id": application_id,
                "contact_id": contact_id,
                "relevance_rank": idx,
                "role_bucket": str(c.get("role_bucket") or "relevant_ic"),
                "fit_reason": str(c.get("fit_reason") or "").strip() or None,
                "source_actor": str(c.get("source_actor") or "").strip() or None,
            }
        )

    if links:
        client.table("application_contacts").upsert(
            links,
            on_conflict="application_id,contact_id",
        ).execute()
    return len(links)


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
        log_internal_error("create_application fetch job", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None

    try:
        row = {"job_id": body.job_id, "status": "queued"}
        if body.notes:
            row["notes"] = body.notes
        result = client.table("applications").insert(row).execute()
        app_row = result.data[0] if result.data else row
        return {"success": True, "application": app_row}
    except Exception as e:
        if "unique_application_per_job" in str(e):
            raise HTTPException(status_code=409, detail="Application already exists for this job") from None
        log_internal_error("create_application insert", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("")
async def list_applications(
    status: str | None = Query(None, description="Filter by status"),
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
        include_contacts = True
        try:
            q = (
                client.table("applications")
                .select(
                    "*, jobs(id, title, company, location, job_url, source_board, ai_score, ai_verdict, is_remote), "
                    "application_contacts(relevance_rank, role_bucket, fit_reason, source_actor, "
                    "contacts(id, name, title, seniority, department, linkedin_url, email, email_verified, do_not_contact))"
                )
                .order("created_at", desc=True)
            )
        except Exception:
            include_contacts = False
        if status and status in VALID_STATUSES:
            q = q.eq("status", status)
        try:
            result = q.range(offset, offset + limit - 1).execute()
        except Exception as e:
            if include_contacts and _is_missing_app_contacts_error(e):
                q = (
                    client.table("applications")
                    .select("*, jobs(id, title, company, location, job_url, source_board, ai_score, ai_verdict, is_remote)")
                    .order("created_at", desc=True)
                )
                if status and status in VALID_STATUSES:
                    q = q.eq("status", status)
                result = q.range(offset, offset + limit - 1).execute()
            else:
                raise
        rows = result.data or []
        return {"applications": rows, "count": len(rows)}
    except Exception as e:
        log_internal_error("GET /applications", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.get("/job-ids")
async def list_application_job_ids():
    """Return all non-null job_ids for application membership checks."""
    try:
        client = db()
        ids: list[str] = []
        offset = 0
        page_size = 1000
        while True:
            result = (
                client.table("applications")
                .select("job_id")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                break
            ids.extend([r.get("job_id") for r in rows if r.get("job_id")])
            if len(rows) < page_size:
                break
            offset += page_size
        return {"job_ids": ids}
    except Exception as e:
        log_internal_error("GET /applications/job-ids", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


@router.post("/{application_id}/prepare")
async def prepare_application(application_id: str):
    """
    Tailor resume for the job, generate cover letter / LinkedIn note / cold email,
    and persist resume_id and text fields on the application row.
    """
    import asyncio

    try:
        client = db()
        app_res = (
            client.table("applications")
            .select("id, job_id, notes")
            .eq("id", application_id)
            .single()
            .execute()
        )
        if not app_res.data:
            raise HTTPException(status_code=404, detail="Application not found")
        job_id = app_res.data.get("job_id")
        if not job_id:
            raise HTTPException(status_code=400, detail="Application missing job_id")

        job_res = client.table("jobs").select("*").eq("id", job_id).single().execute()
        if not job_res.data:
            raise HTTPException(status_code=404, detail="Job not found")
        job = job_res.data

        from backend.agents.application_materials_agent import (
            build_fallback_application_materials,
            load_candidate_profile,
            run_application_materials_agent,
        )
        from backend.agents.contact_enrichment_agent import run_contact_enrichment_agent
        from backend.agents.resume_agent import run_resume_agent

        resume_result = await asyncio.to_thread(run_resume_agent, job)
        materials_status = "ok"
        try:
            materials_raw = await asyncio.to_thread(run_application_materials_agent, job)
        except Exception as mat_err:
            logger.warning(
                "applications.prepare: materials agent raised unexpectedly; using fallback. err={}",
                mat_err,
            )
            materials_raw = {
                **build_fallback_application_materials(job, load_candidate_profile()),
                "generation_status": "fallback",
            }
        materials_status = str(materials_raw.pop("generation_status", "ok"))
        materials = materials_raw
        contacts_result = await asyncio.to_thread(run_contact_enrichment_agent, job)
        contacts_status = contacts_result.get("status", "skipped")
        contacts_count = 0

        resume_id = resume_result.get("resume_id")
        _repo = Path(__file__).resolve().parents[2]
        _pp = resume_result.get("pdf_path")
        pdf_ready = bool(_pp and (_repo / Path(str(_pp))).is_file())
        existing_notes = (app_res.data or {}).get("notes")
        update: dict = {
            "cover_letter": materials.get("cover_letter") or "",
            "linkedin_note": materials.get("linkedin_note") or "",
            "cold_email": materials.get("cold_email") or "",
            "cold_email_subject": materials.get("cold_email_subject") or "",
        }
        if resume_id:
            update["resume_id"] = resume_id

        row = None
        try:
            upd = (
                client.table("applications")
                .update(update)
                .eq("id", application_id)
                .execute()
            )
            row = upd.data[0] if upd.data else None
        except Exception as first_err:
            if not is_missing_materials_columns_error(first_err):
                raise
            logger.warning(
                "applications.prepare: optional columns missing; using cover_letter + notes fallback. "
                "Run backend/db/migrations/add_application_materials.sql on Supabase. err={}",
                first_err,
            )
            notes_merged = merge_notes_with_materials_json(existing_notes, materials)
            fallback: dict = {
                "cover_letter": materials.get("cover_letter") or "",
                "notes": notes_merged,
            }
            if resume_id:
                fallback["resume_id"] = resume_id
            upd2 = (
                client.table("applications")
                .update(fallback)
                .eq("id", application_id)
                .execute()
            )
            row = upd2.data[0] if upd2.data else None

        if not row:
            raise HTTPException(status_code=404, detail="Application not found after update")

        try:
            contacts = contacts_result.get("contacts") or []
            if isinstance(contacts, list):
                contacts_count = _persist_application_contacts(
                    client,
                    application_id=application_id,
                    company=str(job.get("company") or ""),
                    contacts=[c for c in contacts if isinstance(c, dict)],
                )
        except Exception as c_err:
            contacts_status = "failed"
            logger.warning(f"applications.prepare: contact enrichment persistence failed: {c_err}")

        return {
            "success": True,
            "application": row,
            "resume": {
                "resume_id": resume_id,
                "pdf_path": resume_result.get("pdf_path"),
                "pdf_ready": pdf_ready,
                "diff_summary": resume_result.get("diff_summary"),
                "keywords_added": resume_result.get("keywords_added", []),
            },
            "materials": {
                "cover_letter": materials.get("cover_letter"),
                "linkedin_note": materials.get("linkedin_note"),
                "cold_email_subject": materials.get("cold_email_subject"),
                "cold_email": materials.get("cold_email"),
            },
            "materials_status": materials_status,
            "contacts_enrichment": {
                "status": contacts_status,
                "count": contacts_count,
                "db_reused": int(contacts_result.get("db_reused") or 0),
                "apify_called": int(contacts_result.get("apify_called") or 0),
                "emails_enriched": int(contacts_result.get("emails_enriched") or 0),
            },
        }
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail="Required resume or profile file is missing on the server.",
        ) from e
    except Exception as e:
        log_internal_error("POST /applications/{id}/prepare", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


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
        try:
            result = (
                client.table("applications")
                .select(
                    "*, jobs(*, resumes(id, version_name, file_path, created_at)), "
                    "application_contacts(relevance_rank, role_bucket, fit_reason, source_actor, "
                    "contacts(id, name, title, seniority, department, linkedin_url, email, email_verified, do_not_contact))"
                )
                .eq("id", application_id)
                .single()
                .execute()
            )
        except Exception as e:
            if not _is_missing_app_contacts_error(e):
                raise
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("GET /applications/{id}", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


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
            update["applied_at"] = datetime.now(UTC).isoformat()

        result = client.table("applications").update(update).eq("id", application_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"success": True, "application": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        log_internal_error("PATCH /applications/{id}/status", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None


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
        log_internal_error("DELETE /applications/{id}", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR) from None
