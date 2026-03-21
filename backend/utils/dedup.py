"""
backend/utils/dedup.py
=======================
Job deduplication using normalized SHA-256 hashes.
Prevents the same job from being applied to twice.
"""

import hashlib
import re
from loguru import logger


def make_dedup_hash(company: str, title: str, location: str = "") -> str:
    """
    Generate a stable deduplication hash for a job.
    Normalizes text before hashing to catch near-duplicates.
    """
    normalized = _normalize(company) + "|" + _normalize(title) + "|" + _normalize(location)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)       # remove punctuation
    text = re.sub(r"\s+", " ", text)           # collapse whitespace
    # Remove common suffixes that vary between boards
    text = re.sub(r"\b(inc|llc|corp|ltd|co)\b", "", text)
    return text.strip()


def is_duplicate(job: dict, existing_hashes: set[str]) -> bool:
    """Check if a job's hash already exists in the seen set."""
    h = make_dedup_hash(
        job.get("company", ""),
        job.get("title", ""),
        job.get("location", ""),
    )
    return h in existing_hashes


def filter_duplicates(jobs: list[dict], existing_hashes: set[str]) -> tuple[list[dict], int]:
    """
    Remove duplicates from a list of jobs.

    Returns:
        (unique_jobs, duplicate_count)
    """
    seen = set(existing_hashes)
    unique = []
    dup_count = 0

    for job in jobs:
        h = make_dedup_hash(
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", ""),
        )
        if h in seen:
            dup_count += 1
        else:
            seen.add(h)
            job["dedup_hash"] = h
            unique.append(job)

    if dup_count:
        logger.debug(f"Dedup: removed {dup_count} duplicates, {len(unique)} unique jobs remain")

    return unique, dup_count


def pre_filter_by_keywords(jobs: list[dict], profile: dict) -> tuple[list[dict], list[dict]]:
    """
    Cheap pre-filter before calling the LLM.
    Instantly rejects jobs with dealbreaker keywords.
    Returns (candidates_for_llm, instant_rejects)
    """
    signals = profile.get("ai_scoring_signals", {})
    instant_reject = [kw.lower() for kw in signals.get("instant_reject_keywords", [])]

    candidates = []
    rejected = []

    for job in jobs:
        text = (
            (job.get("title") or "") + " " +
            (job.get("description") or "")
        ).lower()

        rejected_flag = False
        for kw in instant_reject:
            if kw in text:
                job["ai_verdict"] = "SKIP"
                job["ai_score"] = 1
                job["ai_reason"] = f"Auto-rejected: contains '{kw}'"
                rejected.append(job)
                rejected_flag = True
                break

        if not rejected_flag:
            candidates.append(job)

    if rejected:
        logger.debug(f"Pre-filter: {len(rejected)} instant rejects, {len(candidates)} sent to LLM")

    return candidates, rejected
