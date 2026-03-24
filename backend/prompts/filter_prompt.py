"""
backend/prompts/filter_prompt.py
=================================
System and user prompts for the job filter agent.
Isolated here so the learning agent can patch them without touching logic.
"""

def _skills_line(profile: dict) -> str:
    sk = profile.get("skills") or {}
    if not isinstance(sk, dict):
        return ""
    fl = sk.get("flat_list")
    if isinstance(fl, list) and fl:
        return ", ".join(str(x) for x in fl if x)
    langs = sk.get("languages") or []
    ml = (sk.get("ml_and_data") or [])[:5]
    fw = (sk.get("frameworks") or [])[:4]
    return ", ".join(str(x) for x in (langs + ml + fw) if x)


def _education_line(profile: dict) -> str:
    edu = profile.get("education") or {}
    if not isinstance(edu, dict):
        return "N/A"
    deg = edu.get("degree") or ""
    maj = edu.get("major") or ""
    uni = edu.get("university") or ""
    gy = edu.get("graduation_year") or ""
    gm = edu.get("graduation_month") or ""
    if not (deg or maj or uni):
        return "N/A"
    return f"{deg} in {maj} from {uni} (graduating {gm} {gy})".strip()


def _work_exp_line(profile: dict) -> str:
    wx = profile.get("work_experience") or []
    if not isinstance(wx, list) or not wx:
        return "N/A"
    parts = []
    for w in wx:
        if not isinstance(w, dict):
            continue
        r, c = w.get("role") or "", w.get("company") or ""
        if r or c:
            parts.append(f"{r} at {c}".strip())
    return ", ".join(parts) if parts else "N/A"


# Enough JD text for scoring + keyword extraction (token budget handled by caller max_tokens).
JD_DESCRIPTION_MAX_CHARS = 6000


FILTER_SYSTEM_PROMPT = """You are an expert job search assistant. Your job is to evaluate job listings
against a candidate's profile and decide whether they should apply.

You must be strict and honest. A score of 8-10 means this is genuinely a strong match.
A score of 1-3 means the candidate would likely be rejected or the role is a poor fit.
Do not inflate scores — the candidate's time is valuable.

SCORING CRITERIA:
- Title match (does the role match what they're targeting?)
- Experience requirements (are they within range? 0-3 years is fine for this candidate)
- Skills overlap (do their actual skills appear in the JD?)
- Company quality (is this a real company worth applying to?)
- Dealbreakers (instantly score 1 if any dealbreaker is present)

VERDICT RULES:
- APPLY: score 7-10. Strong match, candidate should apply immediately.
- MAYBE: score 4-6. Partial match, worth considering but not priority.
- SKIP:  score 1-3. Poor fit, likely waste of time, or dealbreaker present.

IMPORTANT: Ground all answers in the candidate profile. Never invent qualifications."""


def build_filter_prompt(jobs_batch: list[dict], profile: dict) -> str:
    """Build the user prompt for a batch of jobs."""

    personal = profile.get("personal") or {}
    edu = profile.get("education") or {}
    gpa = edu.get("gpa") if isinstance(edu, dict) else "N/A"
    profile_summary = f"""
CANDIDATE PROFILE:
- Name: {personal.get('name', 'N/A')}
- Degree: {_education_line(profile)}
- GPA: {gpa}
- Experience: {profile.get('years_experience', 'N/A')} years ({profile.get('_experience_note', '')})
- Target roles: {', '.join((profile.get('target_roles') or [])[:8])}
- Skills: {_skills_line(profile)}
- Work experience: {_work_exp_line(profile)}
- Target locations: {', '.join(profile.get('work_preferences', {}).get('target_locations', []) or [])}
- Salary target: ${profile.get('salary', {}).get('target_min_usd', 0):,} – ${profile.get('salary', {}).get('target_max_usd', 0):,}
- Dealbreakers: {', '.join(profile.get('dealbreakers', []) or [])}
- Visa: {profile.get('work_preferences', {}).get('visa_status', 'N/A')}
"""

    jobs_text = ""
    for i, job in enumerate(jobs_batch):
        desc = str(job.get("description") or "")[:JD_DESCRIPTION_MAX_CHARS]
        jobs_text += f"""
JOB {i}:
  Title: {job.get('title', 'N/A')}
  Company: {job.get('company', 'N/A')}
  Location: {job.get('location', 'N/A')}
  Source: {job.get('source_board', 'N/A')}
  Description (excerpt up to {JD_DESCRIPTION_MAX_CHARS} chars): {desc}
  Salary: {job.get('salary_min', 'N/A')} – {job.get('salary_max', 'N/A')}
"""

    return f"""{profile_summary}

JOBS TO EVALUATE:
{jobs_text}

Respond with a JSON array — one object per job, in order. Each object must have:
{{
  "index": <integer, 0-based>,
  "score": <integer 1-10>,
  "verdict": "APPLY" | "MAYBE" | "SKIP",
  "reason": "<one sentence, specific to this job and candidate>",
  "missing_skills": ["<skill the JD wants that candidate lacks>"],
  "strengths": ["<specific reason candidate is a good fit>"],
  "jd_keywords": ["<8-15 short strings: tools, frameworks, languages, domains, methods mentioned in the title or description — only if explicitly stated; do not invent credentials or employers>"]
}}

Respond ONLY with the JSON array. No preamble, no markdown fences."""
