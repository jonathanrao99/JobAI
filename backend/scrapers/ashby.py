"""Ashby ATS scraper — GraphQL list + JSON-LD individual page for dates/descriptions."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter
from backend.utils.rate_limiter import RateLimiter

_rl = RateLimiter()

_GQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

# jobBoardWithTeams returns brief listings (id, title, location, compensation)
# Individual job pages have JSON-LD with datePosted and full description
_GQL_LIST = """
query jobBoardWithTeams($slug: String!) {
  jobBoardWithTeams(organizationHostedJobsPageName: $slug) {
    jobPostings {
      id
      title
      locationName
      workplaceType
      compensationTierSummary
    }
  }
}
"""


class AshbyScraper(BaseScraper):

    def scrape(self) -> List[Job]:
        slug = self.company.get("ats_slug") or self._infer_slug_from_url()
        if not slug:
            logger.warning(f"[Ashby] No slug for {self.company['name']}, skipping")
            return []

        logger.info(f"[Ashby] Fetching job list for: {slug}")

        try:
            postings = self._fetch_list(slug)
        except Exception as e:
            logger.error(f"[Ashby] {self.company['name']} list failed: {e}")
            return []

        jobs: List[Job] = []
        company_job_count = 0

        for item in postings:
            if company_job_count >= self.config.max_jobs_per_company:
                break

            title = item.get("title", "")
            if not title or self.has_excluded_keyword(title):
                continue

            job_id = item.get("id", "")
            job_url = f"https://jobs.ashbyhq.com/{slug}/{job_id}"

            # Fetch individual page for datePosted + description via JSON-LD
            detail = self._fetch_job_detail(job_url)
            if not detail:
                continue

            date_posted = _parse_date(detail.get("datePosted"))
            if not self.is_recent(date_posted):
                continue

            # Build location: prefer JSON-LD jobLocation, fallback to list field
            loc_addresses = detail.get("jobLocation") or []
            if loc_addresses:
                first = loc_addresses[0].get("address", {}) if isinstance(loc_addresses, list) else {}
                location_raw = ", ".join(filter(None, [
                    first.get("addressLocality", ""),
                    first.get("addressRegion", ""),
                    first.get("addressCountry", ""),
                ]))
            else:
                location_raw = item.get("locationName", "")

            workplace = item.get("workplaceType", "") or ""
            if "remote" in workplace.lower():
                location_raw = f"Remote - {location_raw}".strip(" -")
            elif "hybrid" in workplace.lower():
                location_raw = f"Hybrid - {location_raw}".strip(" -")

            loc_info = parse_location(location_raw)
            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            description = _strip_html(detail.get("description", ""))
            if self.has_excluded_keyword(description):
                continue

            # Salary from JSON-LD baseSalary or list compensationTierSummary
            salary = _extract_salary_from_jsonld(detail) or item.get("compensationTierSummary")

            skills = extract_skills(description)
            exp_level = infer_experience_level(title, description)
            if not self.passes_experience_filter(exp_level, description):
                continue
            visa = self.detect_visa_sponsorship(description)

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
                apply_url=job_url,
                description=description,
                ats_platform="Ashby",
                required_skills=skills,
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            )
            jobs.append(job)
            company_job_count += 1
            time.sleep(0.4)  # polite delay between individual page fetches

        logger.info(f"[Ashby] {self.company['name']}: {len(jobs)} recent jobs found (of {len(postings)} listed)")
        return jobs

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _fetch_list(self, slug: str) -> list:
        _rl.wait("ashbyhq.com")
        payload = {
            "operationName": "jobBoardWithTeams",
            "query": _GQL_LIST,
            "variables": {"slug": slug},
        }
        resp = requests.post(
            _GQL_URL,
            json=payload,
            headers=_rl.get_headers({"Content-Type": "application/json"}),
            timeout=self.config.scraper.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.debug(f"[Ashby] GraphQL errors for {slug}: {data['errors']}")
        board = (data.get("data") or {}).get("jobBoardWithTeams") or {}
        return board.get("jobPostings", [])

    def _fetch_job_detail(self, url: str) -> Optional[dict]:
        """Fetch individual Ashby job page and parse JSON-LD for datePosted + description."""
        try:
            _rl.wait("ashbyhq.com")
            resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds)
            if not resp.ok:
                return None

            matches = re.findall(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                resp.text, re.DOTALL | re.IGNORECASE,
            )
            for raw in matches:
                try:
                    d = json.loads(raw.strip())
                    if d.get("@type") == "JobPosting":
                        return d
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"[Ashby] detail fetch failed for {url}: {e}")
        return None


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_salary_from_jsonld(d: dict) -> Optional[str]:
    salary = d.get("baseSalary")
    if not salary:
        return None
    val = salary.get("value", {})
    min_v = val.get("minValue")
    max_v = val.get("maxValue")
    currency = salary.get("currency", "USD")
    unit = val.get("unitText", "")
    if min_v and max_v:
        return f"${int(min_v):,} – ${int(max_v):,} {currency}/{unit}".strip("/")
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
