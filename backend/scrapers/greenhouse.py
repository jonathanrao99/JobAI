"""Greenhouse ATS scraper — uses the new boards-api.greenhouse.io REST API."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter
from backend.utils.rate_limiter import RateLimiter

_rl = RateLimiter()

# New Greenhouse public API (boards.greenhouse.io/slug/jobs.json is dead)
_NEW_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseScraper(BaseScraper):

    def scrape(self) -> List[Job]:
        slug = self.company.get("ats_slug") or self._infer_slug_from_url()
        if not slug:
            logger.warning(f"[Greenhouse] No slug for {self.company['name']}, skipping")
            return []

        url = _NEW_API.format(slug=slug)
        logger.info(f"[Greenhouse] Fetching {url}")

        try:
            raw = self._fetch_jobs(url)
        except Exception as e:
            logger.error(f"[Greenhouse] {self.company['name']}: {e}")
            return []

        jobs: List[Job] = []
        raw_jobs = raw.get("jobs", [])
        company_job_count = 0

        for item in raw_jobs:
            if company_job_count >= self.config.max_jobs_per_company:
                break

            # Prefer first_published (when job first went live) over updated_at
            date_posted = (
                _parse_date(item.get("first_published"))
                or _parse_date(item.get("updated_at"))
            )
            if not self.is_recent(date_posted):
                continue

            title = item.get("title", "")
            if self.has_excluded_keyword(title):
                continue

            loc_raw = item.get("location", {})
            location_raw = loc_raw.get("name", "") if isinstance(loc_raw, dict) else str(loc_raw)
            loc_info = parse_location(location_raw)

            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            apply_url = item.get("absolute_url", "")

            # Description is inline in ?content=true response (HTML-encoded)
            description = _strip_html(item.get("content", "") or "")

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
                ats_platform="Greenhouse",
                required_skills=skills,
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            )
            jobs.append(job)
            company_job_count += 1

        logger.info(f"[Greenhouse] {self.company['name']}: {len(jobs)} recent jobs found (of {len(raw_jobs)} total)")
        return jobs

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _fetch_jobs(self, url: str) -> dict:
        _rl.wait("greenhouse.io")
        resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds)
        resp.raise_for_status()
        return resp.json()


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _strip_html(html: str) -> str:
    from html import unescape
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    # Greenhouse double-encodes: &lt;div&gt; → need to unescape first
    html = unescape(html)
    p = _Parser()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


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
