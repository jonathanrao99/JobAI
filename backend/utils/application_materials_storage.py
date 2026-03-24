"""
Persist application materials when optional DB columns are missing (Supabase not migrated).
Stores LinkedIn / cold email in `notes` under a single JSON line prefix.
"""

from __future__ import annotations

import json

JOBAI_PREFIX = "__JOBAI_MATERIALS_JSON__:"


def strip_jobai_line_from_notes(notes: str | None) -> str:
    if not notes:
        return ""
    lines = [ln for ln in notes.split("\n") if not ln.strip().startswith(JOBAI_PREFIX)]
    return "\n".join(lines).strip()


def merge_notes_with_materials_json(existing_notes: str | None, materials: dict) -> str:
    """Append / replace the JobAI JSON line; preserve other note text."""
    payload = {
        "linkedin_note": (materials.get("linkedin_note") or "").strip(),
        "cold_email": (materials.get("cold_email") or "").strip(),
        "cold_email_subject": (materials.get("cold_email_subject") or "").strip(),
    }
    line = JOBAI_PREFIX + json.dumps(payload, ensure_ascii=False)
    base = strip_jobai_line_from_notes(existing_notes)
    if base:
        return base + "\n\n" + line
    return line


def is_missing_materials_columns_error(exc: BaseException) -> bool:
    s = str(exc)
    return "PGRST204" in s or "cold_email" in s or "linkedin_note" in s or "schema cache" in s
