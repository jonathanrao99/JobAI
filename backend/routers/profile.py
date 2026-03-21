"""
backend/routers/profile.py
==========================
Read/write `data/candidate_profile.json` for the UI Profile tab.
Merges form data with the existing file so advanced keys (target_roles, salary, …) are preserved.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from loguru import logger

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "data" / "candidate_profile.json"

router = APIRouter()


class PersonalForm(BaseModel):
    full_name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    linkedin: str = ""
    github: str = ""
    website: str = ""


class EducationForm(BaseModel):
    university: str = ""
    degree: str = ""
    major: str = ""
    graduation_year: Optional[int] = None
    gpa: str = ""


class ExperienceForm(BaseModel):
    company: str = ""
    role: str = ""
    duration: str = ""
    bullets: list[str] = Field(default_factory=list)


class ProjectForm(BaseModel):
    name: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    github_url: str = ""
    impact: str = ""


class ProfilePayload(BaseModel):
    personal: PersonalForm
    skills: str = ""
    education: list[EducationForm] = Field(default_factory=list)
    work_experience: list[ExperienceForm] = Field(default_factory=list)
    projects: list[ProjectForm] = Field(default_factory=list)


def _load_raw() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Profile file not found at {PROFILE_PATH}. Create data/candidate_profile.json first.",
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _form_from_profile(raw: dict[str, Any]) -> ProfilePayload:
    p = raw.get("personal") or {}
    skills_obj = raw.get("skills") or {}
    if isinstance(skills_obj.get("flat_list"), list) and skills_obj["flat_list"]:
        skills_str = ", ".join(str(s) for s in skills_obj["flat_list"] if s)
    else:
        parts: list[str] = []
        if isinstance(skills_obj, dict):
            for key in ("languages", "ml_and_data", "frameworks", "data_tools", "databases", "cloud_and_devops", "concepts"):
                parts.extend(skills_obj.get(key) or [])
        skills_str = ", ".join(parts)

    edu = raw.get("education") or {}
    education_list = [
        EducationForm(
            university=str(edu.get("university") or ""),
            degree=str(edu.get("degree") or ""),
            major=str(edu.get("major") or ""),
            graduation_year=edu.get("graduation_year"),
            gpa=str(edu.get("gpa") or ""),
        )
    ]
    for e in raw.get("education_history") or []:
        if isinstance(e, dict):
            education_list.append(
                EducationForm(
                    university=str(e.get("university") or ""),
                    degree=str(e.get("degree") or ""),
                    major=str(e.get("major") or ""),
                    graduation_year=e.get("graduation_year"),
                    gpa=str(e.get("gpa") or ""),
                )
            )

    wx: list[ExperienceForm] = []
    for w in raw.get("work_experience") or []:
        if not isinstance(w, dict):
            continue
        wx.append(
            ExperienceForm(
                company=str(w.get("company") or ""),
                role=str(w.get("role") or ""),
                duration=str(w.get("duration") or ""),
                bullets=list(w.get("bullets") or []),
            )
        )

    proj: list[ProjectForm] = []
    for pr in raw.get("projects") or []:
        if not isinstance(pr, dict):
            continue
        ts = pr.get("tech_stack") or []
        if isinstance(ts, str):
            ts = [t.strip() for t in ts.split(",") if t.strip()]
        proj.append(
            ProjectForm(
                name=str(pr.get("name") or ""),
                description=str(pr.get("description") or ""),
                tech_stack=list(ts) if isinstance(ts, list) else [],
                github_url=str(pr.get("github_url") or ""),
                impact=str(pr.get("impact") or ""),
            )
        )

    return ProfilePayload(
        personal=PersonalForm(
            full_name=str(p.get("name") or ""),
            phone=str(p.get("phone") or ""),
            email=str(p.get("email") or ""),
            linkedin=str(p.get("linkedin_url") or ""),
            github=str(p.get("github_url") or ""),
            website=str(p.get("portfolio_url") or ""),
        ),
        skills=skills_str,
        education=education_list,
        work_experience=wx,
        projects=proj,
    )


def _merge_save(raw: dict[str, Any], body: ProfilePayload) -> dict[str, Any]:
    out = dict(raw)

    out["personal"] = {
        **(out.get("personal") or {}),
        "name": body.personal.full_name.strip(),
        "phone": body.personal.phone.strip(),
        "email": body.personal.email.strip(),
        "linkedin_url": (body.personal.linkedin or "").strip(),
        "github_url": (body.personal.github or "").strip(),
        "portfolio_url": (body.personal.website or "").strip(),
    }

    flat_skills = [s.strip() for s in (body.skills or "").split(",") if s.strip()]
    skills_prev = out.get("skills") if isinstance(out.get("skills"), dict) else {}
    out["skills"] = {
        **skills_prev,
        "flat_list": flat_skills,
        "languages": flat_skills[:80] if flat_skills else skills_prev.get("languages") or [],
    }

    edu_rows = [e for e in body.education if e.university.strip() or e.degree.strip() or e.major.strip()]
    if edu_rows:
        first = edu_rows[0]
        prev_edu = out.get("education") if isinstance(out.get("education"), dict) else {}
        out["education"] = {
            **prev_edu,
            "university": first.university.strip() or prev_edu.get("university", ""),
            "degree": first.degree.strip() or prev_edu.get("degree", ""),
            "major": first.major.strip() or prev_edu.get("major", ""),
            "graduation_year": first.graduation_year if first.graduation_year is not None else prev_edu.get("graduation_year"),
            "gpa": first.gpa.strip() if first.gpa else prev_edu.get("gpa", ""),
        }
        rest = []
        for e in edu_rows[1:]:
            rest.append(
                {
                    "university": e.university.strip(),
                    "degree": e.degree.strip(),
                    "major": e.major.strip(),
                    "graduation_year": e.graduation_year,
                    "gpa": e.gpa.strip(),
                }
            )
        if rest:
            out["education_history"] = rest
        elif "education_history" in out:
            del out["education_history"]

    wx_out: list[dict[str, Any]] = []
    for w in body.work_experience:
        if not (w.company.strip() or w.role.strip()):
            continue
        wx_out.append(
            {
                "company": w.company.strip(),
                "role": w.role.strip(),
                "duration": w.duration.strip(),
                "is_current": False,
                "bullets": [b.strip() for b in w.bullets if b and str(b).strip()],
                "impact_metrics": [],
            }
        )
    if wx_out:
        out["work_experience"] = wx_out

    pr_out: list[dict[str, Any]] = []
    for pr in body.projects:
        if not pr.name.strip():
            continue
        pr_out.append(
            {
                "name": pr.name.strip(),
                "description": pr.description.strip(),
                "tech_stack": pr.tech_stack or [],
                "github_url": (pr.github_url or "").strip(),
                "impact": (pr.impact or "").strip(),
            }
        )
    if pr_out:
        out["projects"] = pr_out

    out["_last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out["_profile_saved_at"] = datetime.now(timezone.utc).isoformat()

    return out


@router.get("")
async def get_profile():
    try:
        raw = _load_raw()
        form = _form_from_profile(raw)
        mtime = PROFILE_PATH.stat().st_mtime
        last_saved = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        saved_at = raw.get("_profile_saved_at") or last_saved
        return {
            "profile": raw,
            "form": form.model_dump(),
            "last_saved": saved_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def put_profile(body: ProfilePayload):
    try:
        raw = _load_raw()
        merged = _merge_save(raw, body)
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        form = _form_from_profile(merged)
        return {
            "success": True,
            "last_saved": merged.get("_profile_saved_at"),
            "form": form.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PUT /profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
