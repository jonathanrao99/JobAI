"""SmartRecruiters ATS scraper — uses public REST API."""
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


class SmartRecruitersScraper(BaseScraper):
    BASE = "https://api.smartrecruiters.com/v1/companies"

    def scrape(self) -> List[Job]:
        slug = self.company.get("ats_slug") or self._infer_slug_from_url()
        if not slug:
            logger.warning(f"[SmartRecruiters] No slug for {self.company['name']}, skipping")
            return []

        logger.info(f"[SmartRecruiters] Fetching {self.company['name']} (slug={slug})")

        jobs: List[Job] = []
        offset = 0
        limit = 100
        company_job_count = 0

        while True:
            if company_job_count >= self.config.max_jobs_per_company:
                break
            try:
                data = self._fetch_page(slug, offset, limit)
            except Exception as e:
                logger.error(f"[SmartRecruiters] {self.company['name']}: {e}")
                break

            postings = data.get("content", [])
            if not postings:
                break

            for item in postings:
                if company_job_count >= self.config.max_jobs_per_company:
                    break

                created_on = item.get("releasedDate") or item.get("createdon", "")
                date_posted = _parse_date(created_on)
                if not self.is_recent(date_posted):
                    continue

                title = item.get("name", "") or item.get("title", "")
                if self.has_excluded_keyword(title):
                    continue

                loc = item.get("location", {})
                location_raw = ", ".join(filter(None, [
                    loc.get("city", ""),
                    loc.get("region", ""),
                    loc.get("country", ""),
                ]))
                if item.get("typeOfHire") and "remote" in str(item.get("typeOfHire", "")).lower():
                    location_raw = f"Remote - {location_raw}".strip(" -")

                loc_info = parse_location(location_raw)
                if not passes_location_filter(loc_info, self.config.location_filter):
                    continue

                job_id = item.get("id", "")
                apply_url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}"

                # Fetch full description
                description = self._fetch_description(slug, job_id)
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
                    ats_platform="SmartRecruiters",
                    required_skills=skills,
                    experience_level=exp_level,
                    city=loc_info["city"],
                    state=loc_info["state"],
                )
                jobs.append(job)
                company_job_count += 1

            total = data.get("totalFound", 0)
            offset += limit
            if offset >= total:
                break

        logger.info(f"[SmartRecruiters] {self.company['name']}: {len(jobs)} recent jobs found")
        return jobs

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _fetch_page(self, slug: str, offset: int, limit: int) -> dict:
        url = f"{self.BASE}/{slug}/postings?limit={limit}&offset={offset}"
        _rl.wait("smartrecruiters.com")
        resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def _fetch_description(self, slug: str, job_id: str) -> str:
        if not job_id:
            return ""
        url = f"{self.BASE}/{slug}/postings/{job_id}"
        try:
            _rl.wait("smartrecruiters.com")
            resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds)
            if resp.ok:
                data = resp.json()
                sections = data.get("jobAd", {}).get("sections", {})
                parts = []
                for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
                    html = sections.get(key, {}).get("text", "")
                    if html:
                        parts.append(_strip_html(html))
                return " ".join(parts)
        except Exception as e:
            logger.debug(f"[SmartRecruiters] description fetch failed for {job_id}: {e}")
        return ""


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


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
    m = re.search(
        r"\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?\s*(?:per year|\/yr|annually|\/hour|\/hr)?",
        text, re.IGNORECASE,
    )
    return m.group().strip() if m else None
