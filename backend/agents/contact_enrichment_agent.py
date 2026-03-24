"""
Find outreach contacts (3-5) for a job using Apify actors.
Primary path uses Google search actor to discover LinkedIn profiles.
Optional email enrichment actor can be configured via env.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from loguru import logger

from backend.config import settings

_ENRICHMENT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _normalize_linkedin_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u:
        return ""
    if not u.startswith("http"):
        u = f"https://{u.lstrip('/')}"
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower().replace("www.", "")
        if "linkedin.com" not in host:
            return ""
        path = re.sub(r"/+$", "", p.path or "")
        if not (path.startswith("/in/") or path.startswith("/pub/")):
            return ""
        return urlunparse(("https", host, path, "", "", ""))
    except Exception:
        return ""


def _run_apify_actor(actor_id: str, input_data: dict[str, Any]) -> list[dict[str, Any]]:
    if not actor_id or not settings.apify_api_token:
        return []
    safe_id = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{safe_id}/run-sync-get-dataset-items"
    try:
        with httpx.Client(timeout=settings.contact_enrichment_timeout_seconds) as client:
            r = client.post(
                url,
                params={"token": settings.apify_api_token},
                json=input_data,
            )
        if r.status_code >= 400:
            logger.warning(f"Apify {actor_id} HTTP {r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Apify actor {actor_id} failed: {e}")
        return []


def _title_tokens(job_title: str) -> set[str]:
    toks = re.findall(r"[a-z]+", (job_title or "").lower())
    return {t for t in toks if len(t) >= 4 and t not in {"engineer", "developer", "specialist"}}


def _bucket_for_title(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ("recruiter", "talent", "sourcer", "staffing", "people partner")):
        return "recruiter_talent"
    if any(k in t for k in ("director", "head of", "vp", "vice president")):
        return "director_plus"
    if any(k in t for k in ("manager", "team lead", "lead ")):
        return "hiring_manager"
    return "relevant_ic"


def _fit_reason(bucket: str, title: str, company: str) -> str:
    if bucket == "recruiter_talent":
        return f"Recruiting contact at {company}"
    if bucket == "hiring_manager":
        return f"Manager-level contact ({title})"
    if bucket == "director_plus":
        return f"Director/leadership contact ({title})"
    return f"Relevant IC profile ({title})"


def _score_contact(contact: dict[str, Any], role_tokens: set[str]) -> float:
    bucket = contact.get("role_bucket") or "relevant_ic"
    title = (contact.get("title") or "").lower()
    score = 0.0
    if bucket == "recruiter_talent":
        score += 4.2
    elif bucket == "hiring_manager":
        score += 4.0
    elif bucket == "director_plus":
        score += 3.7
    else:
        score += 2.8
    if contact.get("email"):
        score += 1.0
    if any(tok in title for tok in role_tokens):
        score += 0.8
    if "data" in title or "analytics" in title or "machine learning" in title:
        score += 0.4
    return score


def _parse_name_and_title(result_title: str, company: str) -> tuple[str, str]:
    raw = (result_title or "").strip()
    if not raw:
        return "", ""
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s+\|\s+", raw) if p.strip()]
    if not parts:
        return raw, ""
    name = parts[0]
    title = ""
    for p in parts[1:]:
        pl = p.lower()
        if company.lower() in pl:
            continue
        title = p
        break
    return name, title


def _extract_google_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # common shape: one item has organicResults[]
        org = item.get("organicResults")
        if isinstance(org, list):
            for r in org:
                if isinstance(r, dict):
                    out.append(r)
            continue
        # sometimes results are flattened rows
        out.append(item)
    return out


def _db_fallback_contacts(
    company: str,
    role_tokens: set[str],
    max_contacts: int,
    exclude_urls: set[str],
) -> list[dict[str, Any]]:
    """Pull existing contacts for the same company from the DB as a fallback."""
    try:
        from backend.db.client import db
        client = db()
        result = (
            client.table("contacts")
            .select("id, name, title, company, department, seniority, linkedin_url, email, email_verified")
            .ilike("company", f"%{company}%")
            .limit(30)
            .execute()
        )
        rows = result.data or []
    except Exception as e:
        logger.warning(f"DB fallback contacts query failed: {e}")
        return []

    contacts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        li = _normalize_linkedin_url(str(row.get("linkedin_url") or ""))
        if li and li in exclude_urls:
            continue
        title_line = str(row.get("title") or "").strip()
        bucket = _bucket_for_title(title_line)
        contacts.append(
            {
                "name": str(row.get("name") or "").strip() or "Contact",
                "title": title_line,
                "company": company,
                "department": str(row.get("department") or "").strip(),
                "seniority": str(row.get("seniority") or "").strip(),
                "linkedin_url": li or "",
                "email": str(row.get("email") or "").strip(),
                "email_verified": bool(row.get("email_verified")),
                "source": "db_fallback",
                "role_bucket": bucket,
                "fit_reason": _fit_reason(bucket, title_line or "profile", company),
                "source_actor": "",
            }
        )

    contacts.sort(key=lambda c: _score_contact(c, role_tokens), reverse=True)
    return contacts[:max_contacts]


def _cache_key(company: str, title: str) -> str:
    fam = " ".join(sorted(_title_tokens(title)))
    return f"{company.strip().lower()}::{fam}"


def run_contact_enrichment_agent(job: dict[str, Any]) -> dict[str, Any]:
    company = str(job.get("company") or "").strip()
    title = str(job.get("title") or "").strip()
    location = str(job.get("location") or "").strip()
    if not company:
        return {"status": "skipped", "contacts": [], "message": "missing_company"}

    max_contacts = max(1, min(10, int(settings.contact_enrichment_max_contacts or 5)))
    min_contacts = max(1, min(max_contacts, int(settings.contact_enrichment_min_contacts or 3)))
    email_top_k = max(0, min(max_contacts, int(settings.contact_enrichment_email_top_k or 3)))
    ttl_seconds = max(0, int(settings.contact_enrichment_cache_ttl_seconds or 0))
    force_refresh = bool(settings.contact_enrichment_force_refresh)
    actor_id = (settings.apify_people_actor_id or "").strip()
    role_tokens = _title_tokens(title)
    cache_key = _cache_key(company, title)

    if ttl_seconds > 0 and not force_refresh:
        cached = _ENRICHMENT_CACHE.get(cache_key)
        if cached:
            expires_at, cached_contacts = cached
            if expires_at > time.time():
                return {
                    "status": "cache_hit",
                    "contacts": cached_contacts[:max_contacts],
                    "count": min(len(cached_contacts), max_contacts),
                    "db_reused": 0,
                    "apify_called": 0,
                    "emails_enriched": 0,
                }

    contacts: list[dict[str, Any]] = []
    db_reused = 0
    apify_called = 0
    emails_enriched = 0
    apify_available = bool(settings.apify_api_token and actor_id)

    # DB-first contact reuse before spending any Apify calls.
    contacts = _db_fallback_contacts(company, role_tokens, max_contacts, exclude_urls=set())
    db_reused = len(contacts)
    if len(contacts) >= min_contacts:
        final = contacts[:max_contacts]
        if ttl_seconds > 0:
            _ENRICHMENT_CACHE[cache_key] = (time.time() + ttl_seconds, final)
        return {
            "status": "db_reuse",
            "contacts": final,
            "count": len(final),
            "db_reused": db_reused,
            "apify_called": apify_called,
            "emails_enriched": emails_enriched,
        }

    if apify_available:
        queries = [
            f'site:linkedin.com/in "{company}" recruiter',
            f'site:linkedin.com/in "{company}" hiring manager {title}',
            f'site:linkedin.com/in "{company}" director {title.split("/")[0].strip()}',
            f'site:linkedin.com/in "{company}" {title.split("/")[0].strip()}',
        ]
        # apify/google-search-scraper expects `queries` as a single string (newline-separated).
        queries_str = "\n".join(queries)
        base_input: dict[str, Any] = {
            "queries": queries_str,
            "maxPagesPerQuery": 1,
            "resultsPerPage": 10,
            "languageCode": "en",
        }
        items = _run_apify_actor(actor_id, base_input)
        apify_called += 1
        if not items:
            items = _run_apify_actor(
                actor_id,
                {**base_input, "queries": queries},
            )
            apify_called += 1
        search_results = _extract_google_results(items)

        seen: set[str] = set()
        for r in search_results:
            url = _normalize_linkedin_url(str(r.get("url") or r.get("link") or ""))
            if not url or url in seen:
                continue
            seen.add(url)
            name, inferred_title = _parse_name_and_title(str(r.get("title") or ""), company)
            snippet = str(r.get("description") or r.get("snippet") or "").strip()
            title_line = inferred_title or snippet.split(".")[0][:90]
            bucket = _bucket_for_title(title_line)
            contacts.append(
                {
                    "name": name or "LinkedIn profile",
                    "title": title_line,
                    "company": company,
                    "department": "",
                    "seniority": "",
                    "linkedin_url": url,
                    "email": "",
                    "email_verified": False,
                    "source": "linkedin_search",
                    "role_bucket": bucket,
                    "fit_reason": _fit_reason(bucket, title_line or "profile", company),
                    "source_actor": actor_id,
                }
            )

        email_actor = (settings.apify_email_actor_id or "").strip()
        if email_actor and contacts and email_top_k > 0:
            contacts.sort(key=lambda c: _score_contact(c, role_tokens), reverse=True)
            topk = [c["linkedin_url"] for c in contacts[:email_top_k] if c.get("linkedin_url")]
            if topk:
                email_items = _run_apify_actor(
                    email_actor,
                    {
                        "profiles": topk,
                        "company": company,
                        "location": location,
                    },
                )
                apify_called += 1
                by_linkedin: dict[str, str] = {}
                for item in email_items:
                    if not isinstance(item, dict):
                        continue
                    li = _normalize_linkedin_url(str(item.get("linkedin_url") or item.get("linkedin") or ""))
                    em = str(item.get("email") or item.get("work_email") or "").strip().lower()
                    if li and em:
                        by_linkedin[li] = em
                for c in contacts:
                    li = c.get("linkedin_url") or ""
                    if li in by_linkedin:
                        c["email"] = by_linkedin[li]
                        c["email_verified"] = True
                        c["source"] = "apollo"
                        emails_enriched += 1

    # DB fallback: fill remaining slots from existing contacts table
    apify_urls = {c.get("linkedin_url") or "" for c in contacts}
    if len(contacts) < max_contacts:
        slots = max_contacts - len(contacts)
        fallback = _db_fallback_contacts(company, role_tokens, slots, apify_urls)
        contacts.extend(fallback)

    deduped: list[dict[str, Any]] = []
    seen_contact_keys: set[str] = set()
    for c in contacts:
        key = (
            _normalize_linkedin_url(str(c.get("linkedin_url") or ""))
            or str(c.get("email") or "").strip().lower()
            or f"{str(c.get('name') or '').strip().lower()}::{str(c.get('title') or '').strip().lower()}"
        )
        if not key or key in seen_contact_keys:
            continue
        seen_contact_keys.add(key)
        deduped.append(c)
    contacts = deduped
    contacts.sort(key=lambda c: _score_contact(c, role_tokens), reverse=True)
    contacts = contacts[:max_contacts]

    if not contacts:
        status = "failed"
    elif not apify_available and contacts:
        status = "fallback_only"
    elif len(contacts) >= min_contacts:
        status = "ok"
    else:
        status = "partial"

    if ttl_seconds > 0 and contacts:
        _ENRICHMENT_CACHE[cache_key] = (time.time() + ttl_seconds, contacts)

    return {
        "status": status,
        "contacts": contacts,
        "count": len(contacts),
        "db_reused": db_reused,
        "apify_called": apify_called,
        "emails_enriched": emails_enriched,
    }
