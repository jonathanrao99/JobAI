"""Workday scraper — uses Workday's internal CXS JSON API (no Playwright needed for most)."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
from loguru import logger

from backend.scrapers.base import BaseScraper, Job, extract_skills, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter
from backend.utils.rate_limiter import RateLimiter

_rl = RateLimiter()

_WD_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Workday-Client": "2023.46.6",
}


def _parse_workday_url(url: str) -> Tuple[str, str, str]:
    """
    Returns (base_url, tenant_for_path, site_name) from a Workday career URL.

    Example:
      https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
        → ("https://nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite")

    The API path uses the company name WITHOUT the .wd{n} suffix.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Strip .wd5, .wd1, etc. to get just the company slug
    tenant_slug = re.sub(r"\.wd\d+$", "", host.replace(".myworkdayjobs.com", ""))
    path_parts = [p for p in parsed.path.split("/") if p]
    site = path_parts[0] if path_parts else "careers"
    base = f"{parsed.scheme}://{host}"
    return base, tenant_slug, site


class WorkdayScraper(BaseScraper):

    def scrape(self) -> List[Job]:
        career_url = self.company.get("career_url", "")
        if not career_url or "myworkdayjobs.com" not in career_url:
            logger.warning(f"[Workday] {self.company['name']}: no valid Workday URL")
            return []

        base_url, tenant, site = _parse_workday_url(career_url)
        logger.info(f"[Workday] {self.company['name']}: tenant={tenant}, site={site}")

        try:
            return self._scrape_api(base_url, tenant, site)
        except Exception as e:
            logger.warning(f"[Workday] API failed for {self.company['name']}: {e}. Trying Playwright...")
            try:
                return self._scrape_playwright(career_url)
            except Exception as e2:
                logger.error(f"[Workday] Both methods failed for {self.company['name']}: {e2}")
                return []

    def _scrape_api(self, base_url: str, tenant: str, site: str) -> List[Job]:
        search_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
        headers = {**_rl.get_headers(), **_WD_HEADERS}
        payload = {"limit": 20, "offset": 0, "searchText": ""}

        jobs: List[Job] = []
        offset = 0
        company_job_count = 0

        while True:
            if company_job_count >= self.config.max_jobs_per_company:
                break

            payload["offset"] = offset
            _rl.wait("myworkdayjobs.com")

            try:
                resp = requests.post(search_url, json=payload, headers=headers,
                                     timeout=self.config.scraper.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Search API failed: {e}")

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for item in postings:
                if company_job_count >= self.config.max_jobs_per_company:
                    break

                posted_on = item.get("postedOn", "")
                # Quick pre-filter on relative date string before fetching details
                quick_date = _parse_relative_date(posted_on)
                if quick_date is not None and not self.is_recent(quick_date):
                    continue

                title = item.get("title", "")
                if not title or self.has_excluded_keyword(title):
                    continue

                ext_path = item.get("externalPath", "")
                if not ext_path:
                    continue

                # Fetch full job details for description + precise date
                detail = self._fetch_detail(base_url, tenant, site, ext_path)
                if not detail:
                    continue

                info = detail.get("jobPostingInfo", {})
                date_posted = _parse_relative_date(info.get("postedOn", posted_on))
                if not self.is_recent(date_posted):
                    continue

                location_raw = (
                    info.get("location")
                    or info.get("locationsText")
                    or item.get("locationsText", "")
                )
                loc_info = parse_location(location_raw)
                if not passes_location_filter(loc_info, self.config.location_filter):
                    continue

                apply_url = info.get("externalUrl") or f"{base_url}{ext_path}"
                description = _strip_html(info.get("jobDescription", ""))

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
                    ats_platform="Workday",
                    required_skills=skills,
                    experience_level=exp_level,
                    city=loc_info["city"],
                    state=loc_info["state"],
                )
                jobs.append(job)
                company_job_count += 1
                time.sleep(0.3)

            total = data.get("total", 0)
            offset += len(postings)
            if offset >= total or offset >= 200:
                break

        logger.info(f"[Workday] {self.company['name']}: {len(jobs)} recent jobs found")
        return jobs

    def _fetch_detail(self, base_url: str, tenant: str, site: str, ext_path: str) -> Optional[dict]:
        # ext_path is like /job/Santa-Clara/Software-Engineer_JR123456
        # strip leading /job/ prefix for the API path
        job_part = ext_path.lstrip("/")  # job/City/Title_ID
        url = f"{base_url}/wday/cxs/{tenant}/{site}/{job_part}"
        try:
            _rl.wait("myworkdayjobs.com")
            resp = requests.get(url, headers={**_rl.get_headers(), **_WD_HEADERS},
                                timeout=self.config.scraper.timeout_seconds)
            if resp.ok:
                return resp.json()
        except Exception as e:
            logger.debug(f"[Workday] detail fetch failed for {ext_path}: {e}")
        return None

    def _scrape_playwright(self, url: str) -> List[Job]:
        """Playwright fallback — only used if API completely fails."""
        from playwright.sync_api import sync_playwright

        jobs: List[Job] = []
        company_job_count = 0

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.config.scraper.headless)
                page = browser.new_page(user_agent=_rl.get_user_agent())
                page.goto(url, wait_until="load", timeout=90_000)
                time.sleep(2)
                page.wait_for_selector("[data-automation-id='jobTitle']", timeout=30_000)

                for card in page.query_selector_all("[data-automation-id='jobTitle']"):
                    if company_job_count >= self.config.max_jobs_per_company:
                        break
                    title = card.inner_text().strip()
                    if not title or self.has_excluded_keyword(title):
                        continue
                    href = card.get_attribute("href") or ""
                    apply_url = href if href.startswith("http") else url
                    job = Job(
                        title=title,
                        company=self.company["name"],
                        company_size_tier=self.company.get("size_tier", "Unknown"),
                        location="",
                        usa_based="Unknown",
                        remote_type="On-site",
                        visa_sponsorship="Not Mentioned",
                        salary_range=None,
                        date_posted=datetime.now(timezone.utc),
                        apply_url=apply_url,
                        description="",
                        ats_platform="Workday",
                        required_skills=[],
                        experience_level=infer_experience_level(title),
                    )
                    jobs.append(job)
                    company_job_count += 1
                browser.close()
        except Exception as e:
            logger.error(f"[Workday/Playwright] {self.company['name']}: {e}")

        logger.info(f"[Workday/Playwright] {self.company['name']}: {len(jobs)} jobs")
        return jobs


def _parse_relative_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    now = datetime.now(timezone.utc)
    lower = text.lower()

    if any(w in lower for w in ["today", "just now", "0 day"]):
        return now
    if "yesterday" in lower:
        return now - timedelta(days=1)

    m = re.search(r"(\d+)\s+day", lower)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s+hour", lower)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s+minute", lower)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    # ISO fallback
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
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
