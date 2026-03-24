"""
Normalize Apify actor dataset items into scraper_agent job dicts.

Each mapper returns None if the record is unusable (missing URL/title).
"""

from __future__ import annotations

from backend.utils.dedup import make_dedup_hash


def map_dice_item(item: dict, source_board: str = "dice") -> dict | None:
    """Maps output of shahidirfan/dice-job-scraper."""
    url = item.get("url") or item.get("detailsPageUrl") or ""
    if not url:
        return None
    loc = item.get("location") or ""
    work_setting = (item.get("workSetting") or "").lower()
    company = item.get("company") or item.get("companyName") or ""
    title = item.get("title") or ""
    return {
        "title": title,
        "company": company,
        "location": loc,
        "description": (item.get("description_text") or item.get("summary") or "")[:50000],
        "job_url": url,
        "source_board": source_board,
        "is_remote": "remote" in loc.lower() or "remote" in work_setting,
        "salary_min": None,
        "salary_max": None,
        "posted_at": item.get("posted") or item.get("firstActiveDate") or "",
        "dedup_hash": make_dedup_hash(company, title, loc),
    }


def map_flex_item(item: dict, source_board: str) -> dict | None:
    """
    Best-effort mapping for actors that expose common job fields.
    Extend or add named mappers when you integrate a specific Apify actor.
    """
    url = (
        item.get("url")
        or item.get("jobUrl")
        or item.get("link")
        or item.get("applyUrl")
        or item.get("job_link")
        or ""
    )
    title = item.get("title") or item.get("jobTitle") or item.get("name") or ""
    if not url or not title:
        return None
    company = (
        item.get("company")
        or item.get("companyName")
        or item.get("employer")
        or item.get("organization")
        or ""
    )
    loc = item.get("location") or item.get("jobLocation") or item.get("city") or ""
    desc = (
        item.get("description")
        or item.get("description_html")
        or item.get("snippet")
        or item.get("summary")
        or ""
    )
    if isinstance(desc, str):
        desc = desc[:50000]
    remote_hint = (item.get("remote") or item.get("isRemote") or item.get("workFromHome")) or False
    if isinstance(remote_hint, str):
        remote_hint = remote_hint.lower() in ("true", "yes", "1", "remote")
    is_remote = bool(remote_hint) or "remote" in str(loc).lower()
    posted = (
        item.get("posted_at")
        or item.get("postedAt")
        or item.get("date")
        or item.get("posted")
        or ""
    )
    return {
        "title": title,
        "company": company,
        "location": loc,
        "description": desc,
        "job_url": url,
        "source_board": source_board,
        "is_remote": is_remote,
        "salary_min": None,
        "salary_max": None,
        "posted_at": str(posted) if posted else "",
        "dedup_hash": make_dedup_hash(company, title, loc),
    }


MAPPERS = {
    "dice": map_dice_item,
    "flex": map_flex_item,
}


def get_mapper(name: str):
    key = (name or "flex").strip().lower()
    return MAPPERS.get(key, map_flex_item)
