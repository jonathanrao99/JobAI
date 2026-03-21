"""Generic scraper — BeautifulSoup + Playwright fallback for custom ATS."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import threading

import requests
from bs4 import BeautifulSoup
from loguru import logger

from backend.scrapers.base import BaseScraper, Job, infer_experience_level
from backend.utils.location_parser import parse_location, passes_location_filter
from backend.utils.rate_limiter import RateLimiter

_rl = RateLimiter()

# Playwright is not thread-safe — only one browser instance at a time
_playwright_lock = threading.Lock()

# Common career path suffixes to try
_CAREER_PATHS = ["/careers", "/jobs", "/join", "/openings", "/positions", "/work-with-us"]

# Patterns that hint at the date of posting in HTML text
_DATE_PATTERNS = [
    r"posted\s+(\d+)\s+day",
    r"(\d+)\s+day[s]?\s+ago",
    r"posted\s+(today|yesterday)",
    r"(\d{4}-\d{2}-\d{2})",
    r"(\w+\s+\d{1,2},?\s+\d{4})",
]

# ---------------------------------------------------------------------------
# Garbage-filtering constants
# ---------------------------------------------------------------------------

# Exact title matches (lowercased) that are navigation / policy / non-job links
_NAV_TITLES_EXACT = {
    "jobs", "careers", "job", "career", "benefits", "university",
    "my profile", "profile", "search roles", "search jobs",
    "see open roles", "open positions", "view open roles", "open roles",
    "view previous applications", "previous applications",
    "early talent", "talent community", "student opportunities",
    "life at stripe", "life at", "how we operate", "our culture",
    "know your rights", "job categories", "all departments",
    "english", "deutsch", "nederlands", "français", "español",
    "workable", "helpsvgs not supported by this browser",
    "canada general integrated accessibility standards policy",
    "robinhood applicant privacy policy page", "applicant privacy policy",
    "apply", "sign in", "log in", "login", "register", "create account",
    "back", "next", "previous", "load more", "show more", "see all jobs",
    "filter", "filters", "sort by", "reset", "clear", "search",
}

# Substrings in titles that indicate non-job content
_NAV_SUBSTRINGS = [
    "privacy policy",
    "accessibility standard",
    "know your rights",
    "workplace discrimination",
    "cookie",
    "terms of service",
    "terms and conditions",
    "equal opportunity",
    "eeo statement",
    "affirmative action",
    "accommodation request",
    "talent network",
    "join our network",
    "job alert",
    "set up job alert",
    "no jobs found",
    "no open positions",
    # Common navigation fragments that show up as "fake job titles".
    "open jobs",
    "available jobs",
    "see jobs",
    "see details",
    "play all",
    "apply",
    "svg not supported",
]

# URL path endings that indicate list/search pages rather than individual job postings
_BAD_URL_ENDINGS = {
    "/jobs", "/careers", "/search", "/openings", "/positions",
    "/opportunities", "/apply", "/explore", "/browse",
    "/jobs/", "/careers/", "/search/", "/openings/", "/positions/",
}

# URL substrings that indicate non-job pages
_BAD_URL_SUBSTRINGS = [
    "/hc/",           # Help center
    "/legal/",        # Legal pages
    "/dist/legal/",   # Distributed legal
    "/help/",         # Help pages
    "actioncenter",   # Action center (EEO)
    "/blog/",         # Blog
    "/press/",        # Press releases
    "/news/",         # News
    "/about/",        # About pages
    "cookie",         # Cookie policy
    "privacy",        # Privacy policy
    "terms",          # Terms of service
    "accessibility",  # Accessibility statements
    "#",              # Fragment-only (anchor links, modals)
]

# URL substrings or query params that strongly suggest a real individual job posting
_JOB_URL_HINTS = [
    "/job/",
    "/jobs/",
    "/position/",
    "/opening/",
    "/role/",
    "/posting/",
    "/listing/",
    "/req/",
    "/requisition/",
    "gh_jid=",        # Greenhouse job ID param
    "jid=",
    "job_id=",
    "jobId=",
    "jobid=",
    "_jr",            # Workday job requisition
    "/jr",
    "/jd/",
    "lever.co",
    "ashbyhq.com",
    "greenhouse.io",
    "workday.com",
    "smartrecruiters.com",
    "icims.com",
    "taleo.net",
    "successfactors",
    "jobvite.com",
    "brassring.com",
    "bamboohr.com",
]

# Locale path patterns (e.g. /au/jobs, /en-gb/careers)
_LOCALE_RE = re.compile(
    r"^/[a-z]{2}(?:-[a-z]{2,4})?/"   # /au/ or /en-gb/ or /nl-be/
    r"(?:jobs|careers|openings|positions)/?$",
    re.IGNORECASE,
)


def _is_garbage_title(title: str) -> bool:
    """Return True if the title looks like a navigation element, not a job."""
    t = title.strip().lower()
    if not t or len(t) < 5:
        return True
    if t in _NAV_TITLES_EXACT:
        return True
    for sub in _NAV_SUBSTRINGS:
        if sub in t:
            return True
    # Titles that are ALL CAPS short words are usually buttons/labels
    if title.isupper() and len(title.split()) <= 3:
        return True
    return False


def _is_garbage_url(url: str) -> bool:
    """Return True if the URL clearly points to a list/policy page, not a job."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()

    # Locale-prefixed list pages
    if _LOCALE_RE.match(parsed.path):
        return True

    # PDF links
    if path.endswith(".pdf"):
        return True

    # Ends with a list-page suffix
    for ending in _BAD_URL_ENDINGS:
        if path == ending.rstrip("/") or path.endswith(ending.rstrip("/")):
            return True

    # Contains a bad substring in path or query
    full = (parsed.path + "?" + parsed.query).lower()
    for bad in _BAD_URL_SUBSTRINGS:
        if bad in full:
            return True

    return False


def _looks_like_job_url(url: str) -> bool:
    """Return True if the URL contains hints of an individual job posting."""
    lower = url.lower()
    for hint in _JOB_URL_HINTS:
        if hint.lower() in lower:
            return True

    # Last path segment looks like a numeric or alphanumeric ID (e.g. /12345, /abc-engineer-12345)
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if segments:
        last = segments[-1]
        # Contains digits (IDs usually have numbers)
        if re.search(r"\d{3,}", last):
            return True
        # Slug-style job title (multiple hyphen-separated words ≥ 3)
        if len(last.split("-")) >= 3:
            return True

    return False


class GenericScraper(BaseScraper):

    def scrape(self) -> List[Job]:
        url = self.company.get("career_url", "")
        if not url:
            logger.warning(f"[Generic] No career URL for {self.company['name']}, skipping")
            return []

        logger.info(f"[Generic] Scraping {self.company['name']} at {url}")

        # First try lightweight requests + BS4
        jobs = self._scrape_requests(url)
        if jobs:
            return jobs

        # Fallback to Playwright for JS-heavy pages
        logger.info(f"[Generic] Requests failed, trying Playwright for {self.company['name']}")
        return self._scrape_playwright(url)

    def _scrape_requests(self, url: str) -> List[Job]:
        try:
            _rl.wait(re.sub(r"https?://", "", url).split("/")[0])
            resp = requests.get(url, headers=_rl.get_headers(), timeout=self.config.scraper.timeout_seconds,
                                allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"[Generic/requests] {self.company['name']}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_jobs_from_soup(soup, url)

    def _scrape_playwright(self, url: str) -> List[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        jobs: List[Job] = []
        with _playwright_lock:  # one browser at a time across all threads
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.config.scraper.headless)
                    page = browser.new_page(user_agent=_rl.get_user_agent())
                    # Keep generic Playwright scraping bounded so slow companies don't stall the run.
                    page.set_default_timeout(15_000)
                    page.set_default_navigation_timeout(15_000)
                    page.goto(url, wait_until="networkidle", timeout=15_000)
                    time.sleep(2)
                    html = page.content()
                    browser.close()

                soup = BeautifulSoup(html, "lxml")
                jobs = self._parse_jobs_from_soup(soup, url)
            except Exception as e:
                logger.error(f"[Generic/Playwright] {self.company['name']}: {e}")

        return jobs

    def _parse_jobs_from_soup(self, soup: BeautifulSoup, base_url: str) -> List[Job]:
        """Heuristically find job listings in a BS4 soup."""
        jobs: List[Job] = []
        company_job_count = 0

        # Look for common job listing containers
        selectors = [
            "a[href*='/job']", "a[href*='/jobs/']", "a[href*='/career']",
            "a[href*='/opening']", "a[href*='/position']",
            "[class*='job-title']", "[class*='posting-title']",
            "[class*='position-title']", "h2 a", "h3 a",
        ]

        anchors = []
        for sel in selectors:
            try:
                found = soup.select(sel)
                if found:
                    anchors.extend(found)
                    break
            except Exception:
                continue

        seen_urls: set[str] = set()
        skipped_garbage = 0

        for anchor in anchors:
            if company_job_count >= self.config.max_jobs_per_company:
                break

            title = anchor.get_text(strip=True)

            # --- Garbage title filter ---
            if _is_garbage_title(title):
                skipped_garbage += 1
                continue

            if len(title) > 200:
                continue

            href = anchor.get("href", "")
            if not href:
                continue
            full_url = urljoin(base_url, href)

            # --- Garbage URL filter ---
            if _is_garbage_url(full_url):
                skipped_garbage += 1
                continue

            # --- URL quality check: must look like an individual job posting ---
            if not _looks_like_job_url(full_url):
                logger.debug(f"[Generic] Skipping non-job URL: {full_url} (title: {title!r})")
                skipped_garbage += 1
                continue

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            if self.has_excluded_keyword(title):
                continue

            # Try to find a date near this element
            parent_text = ""
            parent = anchor.parent
            for _ in range(3):
                if parent:
                    parent_text = parent.get_text(" ", strip=True)
                    parent = parent.parent

            date_posted = _extract_date_from_text(parent_text)
            if date_posted and not self.is_recent(date_posted):
                continue
            # If we can't find a date, include with a warning
            if date_posted is None:
                logger.debug(f"[Generic] No date for '{title}' at {self.company['name']}, including tentatively")

            # Try to find location nearby
            location_raw = _extract_location_from_text(parent_text)
            loc_info = parse_location(location_raw)
            if not passes_location_filter(loc_info, self.config.location_filter):
                continue

            exp_level = infer_experience_level(title)
            if not self.passes_experience_filter(exp_level):
                continue

            job = Job(
                title=title,
                company=self.company["name"],
                company_size_tier=self.company.get("size_tier", "Unknown"),
                location=loc_info["location"] or location_raw,
                usa_based=loc_info["usa_based"],
                remote_type=loc_info["remote_type"],
                visa_sponsorship="Not Mentioned",
                salary_range=None,
                date_posted=date_posted,
                apply_url=full_url,
                description="",
                ats_platform="Custom",
                required_skills=[],
                experience_level=exp_level,
                city=loc_info["city"],
                state=loc_info["state"],
            )
            jobs.append(job)
            company_job_count += 1

        if skipped_garbage:
            logger.debug(f"[Generic] {self.company['name']}: skipped {skipped_garbage} garbage links")
        logger.info(f"[Generic] {self.company['name']}: {len(jobs)} jobs found (dates unverified)")
        return jobs


def _extract_date_from_text(text: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    lower = text.lower()

    if "today" in lower or "just posted" in lower:
        return now
    if "yesterday" in lower:
        return now - timedelta(days=1)

    m = re.search(r"(\d+)\s+day[s]?\s+ago", lower)
    if m:
        return now - timedelta(days=int(m.group(1)))

    m = re.search(r"(\d+)\s+hour[s]?\s+ago", lower)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    # ISO date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Month Day, Year
    from dateutil import parser as dateparser
    m = re.search(r"([A-Za-z]+ \d{1,2},?\s+\d{4})", text)
    if m:
        try:
            return dateparser.parse(m.group(1)).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    return None


def _extract_location_from_text(text: str) -> str:
    """Try to pull a location snippet from surrounding text."""
    # Look for "City, ST" or "Remote"
    m = re.search(r"\b(remote|hybrid|on[- ]site)\b", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*[A-Z]{2})\b", text)
    if m:
        return m.group(1)
    return ""
