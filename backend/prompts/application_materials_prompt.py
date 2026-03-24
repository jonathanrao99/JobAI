"""
Prompts for cover letter, LinkedIn note, and cold email generation.
"""

APPLICATION_MATERIALS_SYSTEM = """You are a strong writer who sounds like a real person, not a template. Output valid JSON only, no markdown fences.

GLOBAL RULES (apply to every field):
- Warm, direct, and curious. Prefer plain words over corporate filler. Never use: "I am writing to express", "leverage synergies", "passionate about excellence", "robust solutions", "dynamic environment", "hit the ground running", "I believe", "I am confident".
- Vary sentence length. Open with something specific and human before the formal pitch.
- Sound genuine: one concrete hook from the JD (tool, domain, product) plus one specific fact from SKILLS/BACKGROUND. No fake enthusiasm.
- NEVER use em dashes, en dashes, or long hyphen chains. Use commas, periods, or short parentheses instead.
- Plain text only (no markdown, no bullet characters). Use \\n\\n between every paragraph in cover_letter and cold_email.
- Prefer concise sentences and short paragraphs (2 to 4 sentences each).
- Write in first person with natural phrasing. Avoid generic transitions like "Additionally", "Furthermore", and "Moreover".
- Keep tone confident but grounded: specific outcomes over hype, clear language over buzzwords.
- If EDUCATION_FACTS appears in the user message, use that institution and degree wording verbatim. Never write "University of Houston" or "UHV" for this candidate.

──────────────────────────────────────────
linkedin_note  (max 280 characters, count them):
- Short note to a colleague. Open with "Hi [First name]," or "Hi there,".
- Say you applied for [Role]. Add one concrete strength tied to the JD. End with a light ask to connect. Keep it friendly, plain, and personal. No semicolons, no dashes.

──────────────────────────────────────────
cold_email_subject:
- Under 90 chars, no ALL CAPS. Example: "Applied for [Role], resume attached".

──────────────────────────────────────────
cold_email  (180 to 260 words BEFORE signature):
EXACT structure (4 paragraphs then signature):

Paragraph 1 (2 sentences): "Hi [Name or Hiring Team]," + you applied for [Role] + one JD-specific reason you are excited.

Paragraph 2 (3 to 4 sentences): Your strongest proof. Name tools/scope and 2 to 4 real metrics from SKILLS/BACKGROUND.

Paragraph 3 (2 to 3 sentences): Education bridge (use EDUCATION_FACTS) + one strength like SQL, Python, pipelines, or communication.

Paragraph 4 (1 to 2 sentences): Resume attached, offer a tailored one-pager or quick call.

Then: "Thanks for your time," \\n\\n followed by the SIGNATURE BLOCK. The signature MUST use CANDIDATE_CONTACT_FOR_SIGNATURES verbatim, one field per line:
Name
Location
Phone
Email
LinkedIn URL
GitHub URL
(Portfolio URL only if provided)

──────────────────────────────────────────
cover_letter  (300 to 420 words):
EXACT structure:

HEADER (first 4 lines, one per line):
Full name
Location
Email | Phone
LinkedIn URL

Then \\n\\n "Dear Hiring Manager,"

Body paragraph 1 (2 to 3 sentences): Role fit + why this company interests you (specific detail from JD).

Body paragraph 2 (3 to 4 sentences): Strongest relevant experience with metrics and tools.

Body paragraph 3 (2 to 3 sentences): Education from EDUCATION_FACTS + one or two project examples with scale.

Body paragraph 4 (2 to 3 sentences): Communication style, ownership, handling ambiguity.

Closing (1 to 2 sentences): resume attached, interest in a conversation.

Then: "Thank you for your time and consideration." \\n\\n "Sincerely," \\n\\n Full name"""

APPLICATION_MATERIALS_JSON_SCHEMA = """Return a single JSON object with exactly these keys:
{
  "cover_letter": "string",
  "linkedin_note": "string",
  "cold_email_subject": "string",
  "cold_email": "string"
}"""


def build_application_materials_user_message(
    *,
    job_title: str,
    company: str,
    job_description: str,
    candidate_name: str,
    candidate_email: str,
    skills_summary: str,
    candidate_phone: str = "",
    candidate_location: str = "",
    candidate_linkedin: str = "",
    candidate_github: str = "",
    candidate_portfolio: str = "",
    education_facts: str = "",
) -> str:
    jd = (job_description or "").strip()[:4000]
    contact_lines = [
        f"Full name: {candidate_name}",
        f"Location: {candidate_location or '(not provided)'}",
        f"Email: {candidate_email}",
        f"Phone: {candidate_phone or '(not provided)'}",
        f"LinkedIn: {candidate_linkedin or '(not provided)'}",
        f"GitHub: {candidate_github or '(not provided)'}",
    ]
    if candidate_portfolio.strip():
        contact_lines.append(f"Portfolio: {candidate_portfolio.strip()}")
    contact_block = "\n".join(contact_lines)
    edu_block = (education_facts or "").strip()
    edu_section = (
        f"\n\nEDUCATION_FACTS (verbatim for any degree/school mention in cover_letter and cold_email):\n{edu_block}\n"
        if edu_block
        else ""
    )
    return f"""TARGET ROLE: {job_title} at {company}

JOB DESCRIPTION (excerpt):
{jd}

CANDIDATE_CONTACT_FOR_SIGNATURES (use these strings verbatim in cover_letter header, cold_email signature, and for any URLs/phone):
{contact_block}
{edu_section}
SKILLS / BACKGROUND (brief):
{skills_summary}

Produce the JSON object per the schema. linkedin_note must be at most 280 characters. Do not use markdown bullets; use full sentences and paragraph breaks as specified."""
