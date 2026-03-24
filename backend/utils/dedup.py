"""
backend/utils/dedup.py
=======================
Job deduplication using normalized SHA-256 hashes and normalized job URLs.
Prevents the same job from being applied to twice.
"""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from loguru import logger

# Query params stripped for cross-board URL dedup (tracking / session noise).
_TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "trk",
        "source",
        "igshid",
        "si",
    }
)


def normalize_job_url(url: str) -> str:
    """Strip tracking query params and trailing slashes for stable URL-level dedup."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u)
        if not parsed.netloc:
            return u.lower()
        host = (parsed.netloc or "").lower().replace("www.", "")
        path = (parsed.path or "").rstrip("/") or "/"
        # Normalize common board-specific redirect wrappers.
        if "linkedin.com" in host and path.endswith("/jobs/view"):
            path = "/jobs/view"
        q = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_QUERY_PARAMS
        ]
        # Keep only high-signal identifiers when present.
        keep_only = {"jk", "vjk", "jobid", "job_id", "gh_jid", "lever-source", "gh_src"}
        if any(k.lower() in keep_only for k, _ in q):
            q = [(k, v) for k, v in q if k.lower() in keep_only]
        q.sort()
        new_query = urlencode(q)
        normalized = urlunparse(
            (
                (parsed.scheme or "https").lower(),
                host,
                path,
                "",  # params
                new_query,
                "",  # fragment often session-specific
            )
        )
        return normalized
    except Exception:
        return u.split("?", 1)[0].rstrip("/").lower()


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
    text = re.sub(r"[^\w\s]", " ", text)       # remove punctuation
    text = re.sub(r"\s+", " ", text)           # collapse whitespace
    # Remove common suffixes that vary between boards
    text = re.sub(r"\b(inc|llc|corp|ltd|co|company|technologies|technology)\b", "", text)
    return text.strip()


def filter_duplicates(jobs: list[dict], existing_hashes: set[str]) -> tuple[list[dict], int]:
    """
    Remove duplicates: normalized job_url first (same posting across boards), then hash.

    Returns:
        (unique_jobs, duplicate_count)
    """
    seen = set(existing_hashes)
    seen_norm_urls: set[str] = set()
    unique = []
    dup_count = 0

    for job in jobs:
        nu = normalize_job_url(job.get("job_url") or "")
        if nu:
            if nu in seen_norm_urls:
                dup_count += 1
                continue
            seen_norm_urls.add(nu)

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
    title_must_include_any = signals.get("title_must_include_any") or []
    title_must_include_any = [str(x).lower().strip() for x in title_must_include_any if str(x).strip()]

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

        if not rejected_flag and title_must_include_any:
            title_only = (job.get("title") or "").lower()
            if not any(k in title_only for k in title_must_include_any):
                job["ai_verdict"] = "SKIP"
                job["ai_score"] = 1
                job["ai_reason"] = "Auto-rejected: title missing required keyword(s)"
                rejected.append(job)
                rejected_flag = True

        if not rejected_flag:
            candidates.append(job)

    if rejected:
        logger.debug(f"Pre-filter: {len(rejected)} instant rejects, {len(candidates)} sent to LLM")

    return candidates, rejected
