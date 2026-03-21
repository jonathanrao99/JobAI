"""Jooble Jobs API scraper.

Free API — register at https://jooble.org/api/about
Free tier: limited daily requests; returns up to 20 results per call.

Protocol: POST https://jooble.org/api/{api_key}
Body JSON: {"keywords": "...", "location": "", "page": 1}
Response:  {"totalCount": N, "jobs": [...]}
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional, Set

import requests
from loguru import logger

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter

_API_BASE = "https://jooble.org/api/{key}"

_PROFILE_QUERIES = {
    "ML Engineer":      ["machine learning engineer", "AI engineer", "LLM engineer"],
    "Data Scientist":   ["data scientist", "applied scientist"],
    "Data Engineer":    ["data engineer", "analytics engineer"],
}


class JoobleScraper(BaseScraper):
    """Queries the Jooble Jobs API for all configured search profiles."""

    def scrape(self) -> List[Job]:
        jb = self.config.job_boards
        if not jb.jooble_api_key:
            logger.warning(
                "[Jooble] API key not set. Add jooble_api_key to job_boards "
                "in config.yaml (free at jooble.org/api/about)"
            )
            return []

        all_jobs: List[Job] = []
        seen_urls: Set[str] = set()

        queries: List[str] = []
        for profile in self.config.profiles:
            key = profile.name
            if key in _PROFILE_QUERIES:
                queries.extend(_PROFILE_QUERIES[key])
            elif profile.target_job_titles:
                queries.append(profile.target_job_titles[0])

        seen_q: Set[str] = set()
        unique_queries = [q for q in queries if not (q in seen_q or seen_q.add(q))]

        url = _API_BASE.format(key=jb.jooble_api_key)
        for query in unique_queries:
            jobs = self._fetch_query(url, query, seen_urls)
            all_jobs.extend(jobs)
            time.sleep(0.5)

        logger.info(f"[Jooble] {len(all_jobs)} jobs from {len(unique_queries)} queries")
        return all_jobs

    def _fetch_query(self, url: str, query: str, seen_urls: Set[str]) -> List[Job]:
        try:
            resp = requests.post(
                url,
                json={"keywords": query, "location": "united states", "page": 1},
                headers={"Content-Type": "application/json"},
                timeout=self.config.scraper.timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Jooble] Query '{query}' failed: {e}")
            return []

        jobs: List[Job] = []
        for item in data.get("jobs", []):
            apply_url = item.get("link", "")
            if not apply_url or apply_url in seen_urls:
                continue
            seen_urls.add(apply_url)

            title = item.get("title", "").strip()
            if not title or self.has_excluded_keyword(title):
                continue

            # Jooble "updated" field: "2024-01-15T00:00:00.0000000"
            date_posted = _parse_date(item.get("updated", ""))
            if date_posted and not self.is_recent(date_posted):
                continue

            # API returns a short snippet — fetch the real page for full description
            description = self.fetch_full_description(apply_url) or item.get("snippet", "")
            if self.has_excluded_keyword(description):
                continue

            location_raw = item.get("location", "")
            loc_info = parse_location(location_raw)
            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            skills = extract_skills(description)
            exp_level = infer_experience_level(title, description)
            if not self.passes_experience_filter(exp_level, description):
                continue

            salary_raw = item.get("salary", "")
            salary_range = salary_raw.strip() if salary_raw and salary_raw.strip() else None

            jobs.append(Job(
                title=title,
                company=item.get("company", "Unknown").strip(),
                company_size_tier="Unknown",
                location=loc_info["location"] or location_raw,
                usa_based=loc_info["usa_based"],
                remote_type=loc_info["remote_type"],
                visa_sponsorship=self.detect_visa_sponsorship(description),
                salary_range=salary_range,
                date_posted=date_posted,
                apply_url=apply_url,
                description=description,
                ats_platform="Jooble",
                required_skills=skills,
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            ))

        logger.debug(f"[Jooble] '{query}' → {len(jobs)} jobs")
        return jobs


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        # "2024-01-15T00:00:00.0000000" — truncate fractional seconds if needed
        clean = raw.split(".")[0]
        dt = datetime.fromisoformat(clean)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
