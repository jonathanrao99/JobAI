"""Base scraper and Job data model. From jonathanrao99/apply."""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from backend.scrapers.apply_config import ApplyScraperConfig

# Keywords that suggest experience level in job titles / descriptions
_LEVEL_PATTERNS = [
    (r"\b(vp|vice president|director|head of)\b", "Director+"),
    (r"\b(principal|distinguished|fellow)\b", "Principal"),
    (r"\b(staff)\b", "Staff"),
    (r"\b(senior|sr\.?)\b", "Senior"),
    (r"\b(mid[- ]?level|mid[- ]?senior|associate)\b", "Mid"),
    (r"\b(junior|jr\.?|entry[- ]?level|new grad|fresh|intern)\b", "Entry"),
]


def infer_experience_level(title: str, description: str = "") -> str:
    combined = f"{title} {description[:500]}".lower()
    for pattern, level in _LEVEL_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return level
    return "Mid"  # default


def extract_skills(description: str) -> List[str]:
    """Very lightweight skill extraction from description text."""
    SKILL_TOKENS = [
        "python", "go", "golang", "rust", "java", "scala", "kotlin",
        "c++", "c#", "typescript", "javascript", "sql", "postgresql",
        "mysql", "mongodb", "redis", "elasticsearch", "kafka", "spark",
        "flink", "airflow", "dbt", "terraform", "kubernetes", "docker",
        "aws", "gcp", "azure", "pytorch", "tensorflow", "jax", "triton",
        "cuda", "llm", "transformer", "bert", "gpt", "rag", "langchain",
        "react", "vue", "angular", "node.js", "fastapi", "django",
        "flask", "graphql", "grpc", "protobuf", "ray", "dask",
        "mlflow", "wandb", "hugging face", "vllm", "onnx",
        "machine learning", "deep learning", "nlp", "computer vision",
        "reinforcement learning", "data engineering", "data pipeline",
        "ci/cd", "github actions", "jenkins", "datadog", "prometheus",
    ]
    lower = description.lower()
    found = []
    for skill in SKILL_TOKENS:
        if skill in lower:
            found.append(skill)
    return found


@dataclass
class Job:
    title: str
    company: str
    company_size_tier: str
    location: str
    usa_based: str                 # "Yes" | "No" | "Unknown"
    remote_type: str               # "Remote" | "Hybrid" | "On-site" | "Remote-USA-Only" | "Remote-Worldwide"
    visa_sponsorship: str          # "Yes" | "No" | "Not Mentioned"
    salary_range: Optional[str]
    date_posted: Optional[datetime]
    apply_url: str
    description: str
    ats_platform: str
    required_skills: List[str] = field(default_factory=list)
    experience_level: str = "Mid"
    cross_day_duplicate: bool = False
    city: str = ""
    state: str = ""
    # Match fields (filled in by matcher)
    best_resume: str = ""
    match_score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    unmatched_keywords: List[str] = field(default_factory=list)
    resume_suggestions: str = ""
    # Pipeline metadata
    job_id: str = ""          # MD5 of apply_url (set on first access via property)
    date_scraped: Optional[datetime] = None
    profile: str = ""         # which search profile matched this job

    def __post_init__(self):
        if not self.job_id:
            key = self.apply_url.strip() if self.apply_url.strip() else f"{self.title}|{self.company}"
            self.job_id = hashlib.md5(key.encode()).hexdigest()
        if self.date_scraped is None:
            self.date_scraped = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "company_size_tier": self.company_size_tier,
            "location": self.location,
            "usa_based": self.usa_based,
            "remote_type": self.remote_type,
            "visa_sponsorship": self.visa_sponsorship,
            "salary_range": self.salary_range or "",
            "date_posted": self.date_posted.isoformat() if self.date_posted else "",
            "date_scraped": self.date_scraped.isoformat() if self.date_scraped else "",
            "apply_url": self.apply_url,
            "description": self.description,
            "ats_platform": self.ats_platform,
            "required_skills": ", ".join(self.required_skills),
            "experience_level": self.experience_level,
            "cross_day_duplicate": self.cross_day_duplicate,
            "city": self.city,
            "state": self.state,
            "best_resume": self.best_resume,
            "match_score": self.match_score,
            "matched_keywords": ", ".join(self.matched_keywords),
            "unmatched_keywords": ", ".join(self.unmatched_keywords),
            "resume_suggestions": self.resume_suggestions,
            "profile": self.profile,
        }


class BaseScraper(ABC):
    def __init__(self, company: dict, config: "ApplyScraperConfig"):
        self.company = company
        self.config = config

    @abstractmethod
    def scrape(self) -> List[Job]:
        pass

    def is_recent(self, dt: Optional[datetime]) -> bool:
        """Return True if dt is within the configured hours threshold."""
        if dt is None:
            return False
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours_old = (now - dt).total_seconds() / 3600
        return hours_old <= self.config.hours_threshold

    def has_excluded_keyword(self, text: str) -> bool:
        lower = text.lower()
        return any(kw.lower() in lower for kw in self.config.exclude_keywords)

    def fetch_full_description(self, url: str) -> str:
        """
        Fetch the full job description from a URL.
        Strategy:
          1. Follow redirect to get the final URL.
          2. If the final URL is a known ATS (Greenhouse, Lever, Ashby),
             hit their JSON API for a clean description.
          3. Fall back to HTML parsing for unknown career pages.
        Returns empty string on any failure.
        """
        if not url:
            return ""
        try:
            import requests as _req
            _headers = {"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )}
            resp = _req.get(url, headers=_headers,
                            timeout=self.config.scraper.timeout_seconds,
                            allow_redirects=True)
            if not resp.ok:
                return ""
            final_url = resp.url

            # ---- 1. Known ATS APIs ----------------------------------------
            # Greenhouse
            m = re.search(r"boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?(\w+)/jobs/(\d+)", final_url)
            if m:
                api = f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}?content=true"
                try:
                    r2 = _req.get(api, timeout=self.config.scraper.timeout_seconds)
                    if r2.ok:
                        from html import unescape
                        from html.parser import HTMLParser

                        class _P(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.parts = []

                            def handle_data(self, d):
                                self.parts.append(d)

                        raw = unescape(r2.json().get("content", ""))
                        p = _P()
                        p.feed(raw)
                        return re.sub(r"\s+", " ", " ".join(p.parts)).strip()[:6000]
                except Exception:
                    pass

            # Lever
            m = re.search(r"jobs\.lever\.co/([^/?#]+)/([a-f0-9-]{36})", final_url)
            if m:
                api = f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}"
                try:
                    r2 = _req.get(api, timeout=self.config.scraper.timeout_seconds)
                    if r2.ok:
                        data = r2.json()
                        plain = data.get("descriptionPlain") or data.get("description", "")
                        return re.sub(r"\s+", " ", plain).strip()[:6000]
                except Exception:
                    pass

            # Ashby — JSON-LD on individual page
            if "ashbyhq.com" in final_url:
                try:
                    from bs4 import BeautifulSoup
                    import json as _json
                    soup2 = BeautifulSoup(resp.text, "lxml")
                    for script in soup2.find_all("script", type="application/ld+json"):
                        try:
                            ld = _json.loads(script.string or "")
                            if isinstance(ld, dict) and ld.get("description"):
                                return re.sub(r"\s+", " ", ld["description"]).strip()[:6000]
                        except Exception:
                            pass
                except Exception:
                    pass

            # ---- 2. Generic HTML fallback ---------------------------------
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "header", "footer",
                              "aside", "form", "button"]):
                tag.decompose()

            for selector in [
                "[class*='description']", "[id*='description']",
                "[class*='job-desc']",    "[id*='job-desc']",
                "[class*='posting-body']","[class*='job-detail']",
                "[class*='job-content']", "[class*='job-body']",
                "article", "main",
            ]:
                el = soup.select_one(selector)
                if el:
                    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
                    if len(text) > 300:
                        return text[:6000]

            # Largest block with sentence-like content
            best = ""
            for el in soup.find_all(["div", "section", "main"]):
                text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
                if len(text) > len(best) and len(text) > 300 and text.count(".") >= 3:
                    best = text
            if best:
                return best[:6000]

        except Exception as e:
            logger.debug(f"fetch_full_description failed for {url}: {e}")
        return ""

    def passes_experience_filter(self, experience_level: str, description: str = "") -> bool:
        """
        Returns False (skip this job) if:
          1. experience_levels is set and this job's level is not in it, OR
          2. max_years_required is set and the description explicitly asks for more years.
        """
        # Level filter — only applies when experience_levels list is non-empty
        allowed = self.config.experience_levels
        if allowed and experience_level not in allowed:
            return False

        # Years filter — scan description for explicit "N+ years" requirements
        max_yrs = self.config.max_years_required
        if max_yrs is not None and description:
            for m in re.finditer(r"(\d+)\+?\s*(?:or more\s+)?years?", description, re.IGNORECASE):
                n = int(m.group(1))
                if n > max_yrs:
                    return False

        return True

    def detect_visa_sponsorship(self, description: str) -> str:
        lower = description.lower()
        if any(kw in lower for kw in ["visa sponsorship", "will sponsor", "sponsorship available"]):
            return "Yes"
        if any(kw in lower for kw in ["no sponsorship", "not sponsor", "cannot sponsor",
                                       "us citizen", "green card", "authorized to work"]):
            return "No"
        return "Not Mentioned"

    def _infer_slug_from_url(self) -> str:
        """Try to extract ATS slug from the career URL."""
        url = self.company.get("career_url", "")
        if not url:
            return self.company.get("name", "").lower().replace(" ", "-")

        # Greenhouse: boards.greenhouse.io/{slug}
        import re
        m = re.search(r"boards\.greenhouse\.io/([^/?#]+)", url)
        if m:
            return m.group(1)

        # Lever: jobs.lever.co/{slug}
        m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
        if m:
            return m.group(1)

        # Ashby: jobs.ashbyhq.com/{slug}
        m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
        if m:
            return m.group(1)

        # SmartRecruiters: jobs.smartrecruiters.com/{slug}
        m = re.search(r"jobs\.smartrecruiters\.com/(?:ni/)?([^/?#]+)", url)
        if m:
            return m.group(1)

        return self.company.get("name", "").lower().replace(" ", "-")
