"""
Generate cover letter, LinkedIn note, and cold email for a job using the LLM.
Falls back to deterministic templates when the LLM is unavailable or returns invalid JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from backend.prompts.application_materials_prompt import (
    APPLICATION_MATERIALS_JSON_SCHEMA,
    APPLICATION_MATERIALS_SYSTEM,
    build_application_materials_user_message,
)
from backend.utils.llm_client import call_llm_sync, parse_json_response

PROFILE_PATH = Path("data/candidate_profile.json")

# Bounded output reduces OpenRouter 429 pressure vs very large max_tokens.
_MATERIALS_MAX_TOKENS = 2800


def load_candidate_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {}
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _format_education_facts(profile: dict[str, Any]) -> str:
    edu = profile.get("education")
    if not isinstance(edu, dict):
        return ""
    uni = str(edu.get("university") or "").strip()
    deg = str(edu.get("degree") or "").strip()
    major = str(edu.get("major") or "").strip()
    gy = edu.get("graduation_year")
    gm = str(edu.get("graduation_month") or "").strip()
    gpa = str(edu.get("gpa") or "").strip()
    lines = []
    if deg or major:
        parts = [p for p in (deg, f"in {major}" if major else "") if p]
        lines.append("Degree: " + " ".join(parts).strip())
    if uni:
        lines.append(f"Institution: {uni}")
    if gm or gy:
        lines.append(f"Expected completion: {gm} {gy}".strip())
    if gpa:
        lines.append(f"GPA: {gpa}")
    return "\n".join(lines)


def _jd_hook(description: str, max_len: int = 220) -> str:
    """One short phrase from the JD for personalization."""
    t = re.sub(r"\s+", " ", (description or "").strip())
    if not t:
        return "the problems you are solving"
    return t[:max_len] + ("..." if len(t) > max_len else "")


def build_fallback_application_materials(job: dict[str, Any], profile: dict[str, Any]) -> dict[str, str]:
    """
    Deterministic cold email + cover letter + LinkedIn note when LLM fails.
    Matches the user's requested structure (paragraphs, headers, signature block).
    """
    personal = profile.get("personal") or {}
    name = (personal.get("name") or personal.get("full_name") or "Candidate").strip()
    email = (personal.get("email") or "").strip()
    phone = (personal.get("phone") or "").strip()
    location = (personal.get("location") or "").strip()
    linkedin = (personal.get("linkedin_url") or "").strip()
    github = (personal.get("github_url") or "").strip()

    title = (job.get("title") or "this role").strip()
    company = (job.get("company") or "your team").strip()
    desc = (job.get("description") or "").strip()
    hook = _jd_hook(desc)

    edu_line = _format_education_facts(profile)
    if not edu_line:
        edu_line = "Graduate training in data science and analytics."

    cold_subject = f"Applied for {title}, resume attached"

    cold_email = f"""Hi {company} team,

I just applied for your {title} opening and wanted to share a quick reason I am excited about it.

I enjoy building analytics that operators actually use, not reports that sit in folders. At Birdside HTX, I unified POS and delivery data across 10K+ transactions, built KPI dashboards used in daily decisions, reduced stock inconsistencies by 30%, and cut manual reporting effort by 70%.

I am finishing my M.S. in Data Science and I am strongest when the work sits between business questions and technical execution: SQL, Python, clean data pipelines, and clear communication that helps teams act fast. This role lines up with what I care about: {hook}

I have attached my resume for your review. If helpful, I can also share a one-page project brief tailored to this role.

Thanks for your time,
{name}
{location or "Houston, TX"}
{phone}
{email}
LinkedIn: {linkedin or "(add your LinkedIn)"}
GitHub: {github or "(add your GitHub)"}"""

    cover_letter = f"""{name}
{location or "Houston, TX"}
{email} | {phone}
{linkedin}

Dear Hiring Manager,

I am excited to apply for the {title} role at {company} because this opportunity matches the kind of work I do best: turning messy, fast-moving data into clear decisions teams can trust.

At Birdside HTX, I built end-to-end analytics pipelines that integrated Square POS, DoorDash, UberEats, and internal data across 10K+ transactions. I translated that data into practical KPI dashboards used in daily operations for inventory, sales, and performance tracking. The result was measurable impact: stock inconsistencies dropped by 30%, manual reporting effort dropped by 70%, and decision speed improved across shifts.

I pair this business-side execution with strong technical depth from graduate training and project work. {edu_line}

Beyond tools, I focus on communication and ownership. I am comfortable collaborating with non-technical stakeholders, clarifying ambiguous requirements, and delivering analysis that is both technically sound and operationally useful.

I have attached my resume for your review. I would welcome the opportunity to discuss how I can contribute to your team with reliable analytics, clear reporting, and a strong bias toward measurable outcomes.

Thank you for your time and consideration.

Sincerely,
{name}"""

    first = name.split()[0] if name else "there"
    linkedin_note = (
        f"Hi {first}, I applied for {title} at {company}. "
        f"I am excited about {hook[:120]}{'...' if len(hook) > 120 else ''} "
        "Happy to connect if you want a quick fit check."
    )
    if len(linkedin_note) > 280:
        linkedin_note = linkedin_note[:277] + "..."

    return {
        "cover_letter": cover_letter.strip(),
        "linkedin_note": linkedin_note.strip(),
        "cold_email": cold_email.strip(),
        "cold_email_subject": cold_subject,
    }


def run_application_materials_agent(job: dict) -> dict[str, Any]:
    """
    Returns keys: cover_letter, linkedin_note, cold_email, cold_email_subject.
    On LLM failure, returns deterministic fallback and generation_status="fallback".
    """
    profile = load_candidate_profile()
    personal = profile.get("personal") or {}
    name = (personal.get("name") or personal.get("full_name") or "Candidate").strip()
    email = (personal.get("email") or "").strip()
    phone = (personal.get("phone") or "").strip()
    location = (personal.get("location") or "").strip()
    linkedin = (personal.get("linkedin_url") or "").strip()
    github = (personal.get("github_url") or "").strip()
    portfolio = (personal.get("portfolio_url") or "").strip()
    skills = profile.get("skills")
    if isinstance(skills, list):
        skills_summary = ", ".join(str(s) for s in skills[:40])
    elif isinstance(skills, str):
        skills_summary = skills.strip()[:2000]
    elif isinstance(skills, dict):
        parts: list[str] = []
        for _k, v in skills.items():
            if isinstance(v, list):
                parts.extend(str(x) for x in v[:30])
            elif v:
                parts.append(str(v))
        skills_summary = ", ".join(parts)[:2000]
    else:
        skills_summary = str(skills or "")[:2000]

    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    desc = (job.get("description") or "").strip()

    user_msg = build_application_materials_user_message(
        job_title=title,
        company=company,
        job_description=desc,
        candidate_name=name,
        candidate_email=email,
        skills_summary=skills_summary or "See resume.",
        candidate_phone=phone,
        candidate_location=location,
        candidate_linkedin=linkedin,
        candidate_github=github,
        candidate_portfolio=portfolio,
        education_facts=_format_education_facts(profile),
    )
    full_system = f"{APPLICATION_MATERIALS_SYSTEM}\n\n{APPLICATION_MATERIALS_JSON_SCHEMA}"

    logger.info(f"Application materials: generating for {title} @ {company}")

    try:
        raw = call_llm_sync(
            messages=[{"role": "user", "content": user_msg}],
            system=full_system,
            max_tokens=_MATERIALS_MAX_TOKENS,
            temperature=0.35,
            expect_json=True,
            strict_json_object=True,
        )
        data = parse_json_response(raw)
        if not isinstance(data, dict):
            raise ValueError("LLM returned non-object JSON for application materials")

        cover = str(data.get("cover_letter") or "").strip()
        li = str(data.get("linkedin_note") or "").strip()
        if len(li) > 280:
            li = li[:277] + "..."

        cold_subj = str(
            data.get("cold_email_subject")
            or f"Applied for {title}, resume attached"
        ).strip()
        cold_body = str(data.get("cold_email") or "").strip()

        out = {
            "cover_letter": cover,
            "linkedin_note": li,
            "cold_email": cold_body,
            "cold_email_subject": cold_subj,
            "generation_status": "ok",
        }
        return out
    except Exception as e:
        logger.warning(f"Application materials LLM failed, using fallback: {e}")
        fb = build_fallback_application_materials(job, profile)
        return {**fb, "generation_status": "fallback"}
