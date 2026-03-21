"""Lever ATS scraper — uses the public v0 JSON API."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter
from backend.utils.rate_limiter import RateLimiter

_rl = RateLimiter()


class LeverScraper(BaseScraper):
    BASE = "https://api.lever.co/v0/postings"

    def scrape(self) -> List[Job]:
        slug = self.company.get("ats_slug") or self._infer_slug_from_url()
        if not slug:
            logger.warning(f"[Lever] No slug for {self.company['name']}, skipping")
            return []

        url = f"{self.BASE}/{slug}?mode=json&limit=500"
        logger.info(f"[Lever] Fetching {url}")

        try:
            postings = self._fetch_postings(url)
        except Exception as e:
            logger.error(f"[Lever] {self.company['name']}: {e}")
            return []

        jobs: List[Job] = []
        company_job_count = 0

        for item in postings:
            if company_job_count >= self.config.max_jobs_per_company:
                break

            # Lever timestamps are milliseconds since epoch
            created_ms = item.get("createdAt") or item.get("created_at")
            date_posted = _ms_to_dt(created_ms)

            if not self.is_recent(date_posted):
                continue

            title = item.get("text", "") or item.get("title", "")
            if self.has_excluded_keyword(title):
                continue

            # Location
            categories = item.get("categories", {})
            location_raw = (
                categories.get("location")
                or item.get("workplaceType", "")
                or ""
            )
            loc_info = parse_location(location_raw)

            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            apply_url = item.get("applyUrl") or item.get("hostedUrl") or ""

            # Description: Lever provides rich text blocks
            description = _extract_lever_description(item)
            if self.has_excluded_keyword(description):
                continue

            skills = extract_skills(description)
            exp_level = infer_experience_level(title, description)
            if not self.passes_experience_filter(exp_level, description):
                continue
            visa = self.detect_visa_sponsorship(description)
            salary = _extract_salary(description)

            job = Job(
                title=title,
                company=self.company["name"],
                company_size_tier=self.company.get("size_tier", "Unknown"),
                location=loc_info["location"] or location_raw,
                usa_based=loc_info["usa_based"],
                remote_type=loc_info["remote_type"],
                visa_sponsorship=visa,
                salary_range=salary,
                date_posted=date_posted,
                apply_url=apply_url,
                description=description,
                ats_platform="Lever",
                required_skills=skills,
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            )
            jobs.append(job)
            company_job_count += 1

        logger.info(f"[Lever] {self.company['name']}: {len(jobs)} recent jobs found")
        return jobs

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _fetch_postings(self, url: str) -> list:
        _rl.wait("lever.co")
        resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        # Lever returns list directly or {"data": [...]}
        if isinstance(data, list):
            return data
        return data.get("data", [])


def _ms_to_dt(ms) -> Optional[datetime]:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except Exception:
        return None


def _extract_lever_description(item: dict) -> str:
    """Extract and concatenate all text blocks from a Lever posting."""
    parts = []
    # descriptionPlain or description
    plain = item.get("descriptionPlain") or item.get("description", "")
    if plain:
        parts.append(plain)
    # lists block
    for block in item.get("lists", []):
        parts.append(block.get("text", ""))
        items_html = block.get("content", "")
        if items_html:
            parts.append(_strip_html(items_html))
    # additional block
    for block in item.get("additional", []):
        parts.append(block.get("text", ""))
        content = block.get("content", "")
        if content:
            parts.append(_strip_html(content))
    return " ".join(p for p in parts if p).strip()


def _strip_html(html: str) -> str:
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.out = []

        def handle_data(self, data):
            self.out.append(data)

    p = _P()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.out)).strip()


def _extract_salary(text: str) -> Optional[str]:
    patterns = [
        r"\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?\s*(?:per year|\/yr|annually|\/hour|\/hr)?",
        r"[\d,]+k?\s*[-–]\s*[\d,]+k?\s*(?:USD|per year|\/yr)?",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group().strip()
    return None
