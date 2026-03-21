"""Adzuna Jobs API scraper.

Free API — register at https://developer.adzuna.com
Free tier: 250 requests/day, 50 results/page.

One scraper instance is shared per run (companies/adzuna-jobs.yaml).
It queries each profile's representative titles and deduplicates by URL.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional, Set

import requests
from loguru import logger

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter

_API_BASE = "https://api.adzuna.com/v1/api/jobs/us/search/1"

# One representative search term per profile — broad enough to catch variants
_PROFILE_QUERIES = {
    "ML Engineer":      ["machine learning engineer", "AI engineer", "LLM engineer",
                         "MLOps engineer", "generative AI engineer"],
    "Data Scientist":   ["data scientist", "applied scientist", "decision scientist",
                         "AI scientist"],
    "Data Engineer":    ["data engineer", "analytics engineer", "ETL engineer",
                         "data platform engineer"],
}


class AdzunaScraper(BaseScraper):
    """Queries the Adzuna Jobs API for all configured search profiles."""

    def scrape(self) -> List[Job]:
        jb = self.config.job_boards
        if not jb.adzuna_app_id or not jb.adzuna_app_key:
            logger.warning(
                "[Adzuna] Credentials not set. Add adzuna_app_id / adzuna_app_key "
                "to job_boards in config.yaml (free at developer.adzuna.com)"
            )
            return []

        days_old = max(1, self.config.hours_threshold // 24)
        all_jobs: List[Job] = []
        seen_urls: Set[str] = set()

        # Build query list from configured profiles; fall back to _PROFILE_QUERIES
        queries: List[str] = []
        for profile in self.config.profiles:
            key = profile.name
            if key in _PROFILE_QUERIES:
                queries.extend(_PROFILE_QUERIES[key])
            else:
                # Use first title from unknown profile
                if profile.target_job_titles:
                    queries.append(profile.target_job_titles[0])

        # Deduplicate query strings
        seen_q: Set[str] = set()
        unique_queries = [q for q in queries if not (q in seen_q or seen_q.add(q))]

        for query in unique_queries:
            jobs = self._fetch_query(query, jb.adzuna_app_id, jb.adzuna_app_key,
                                     days_old, seen_urls)
            all_jobs.extend(jobs)
            time.sleep(0.5)  # be polite — free tier has rate limits

        logger.info(f"[Adzuna] {len(all_jobs)} jobs from {len(unique_queries)} queries")
        return all_jobs

    def _fetch_query(self, query: str, app_id: str, app_key: str,
                     days_old: int, seen_urls: Set[str]) -> List[Job]:
        try:
            resp = requests.get(
                _API_BASE,
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "what": query,
                    "max_days_old": days_old,
                },
                headers={"Content-Type": "application/json"},
                timeout=self.config.scraper.timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Adzuna] Query '{query}' failed: {e}")
            return []

        jobs: List[Job] = []
        for item in data.get("results", []):
            apply_url = item.get("redirect_url", "")
            if not apply_url or apply_url in seen_urls:
                continue
            seen_urls.add(apply_url)

            title = item.get("title", "").strip()
            if not title or self.has_excluded_keyword(title):
                continue

            date_posted = _parse_date(item.get("created", ""))
            if date_posted and not self.is_recent(date_posted):
                continue

            # API returns a short snippet — fetch the real page for full description
            description = self.fetch_full_description(apply_url) or item.get("description", "")
            if self.has_excluded_keyword(description):
                continue

            loc_raw = item.get("location", {})
            location_raw = loc_raw.get("display_name", "") if isinstance(loc_raw, dict) else ""
            loc_info = parse_location(location_raw)
            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            skills = extract_skills(description)
            exp_level = infer_experience_level(title, description)
            if not self.passes_experience_filter(exp_level, description):
                continue

            co_raw = item.get("company", {})
            company_name = co_raw.get("display_name", "Unknown") if isinstance(co_raw, dict) else "Unknown"

            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary_range: Optional[str] = None
            if salary_min and salary_max:
                salary_range = f"${int(salary_min):,} – ${int(salary_max):,}"
            elif salary_min:
                salary_range = f"${int(salary_min):,}+"

            jobs.append(Job(
                title=title,
                company=company_name,
                company_size_tier="Unknown",
                location=loc_info["location"] or location_raw,
                usa_based=loc_info["usa_based"],
                remote_type=loc_info["remote_type"],
                visa_sponsorship=self.detect_visa_sponsorship(description),
                salary_range=salary_range,
                date_posted=date_posted,
                apply_url=apply_url,
                description=description,
                ats_platform="Adzuna",
                required_skills=skills,
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            ))

        logger.debug(f"[Adzuna] '{query}' → {len(jobs)} jobs")
        return jobs


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
