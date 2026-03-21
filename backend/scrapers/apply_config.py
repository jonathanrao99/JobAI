"""
Scraper config for apply-style pipeline (company YAML + ATS scrapers).
Loaded from config.yaml in project root. Source: jonathanrao99/apply.
"""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class RateLimit:
    requests_per_second: float = 2.0
    min_delay_seconds: float = 0.5
    max_delay_seconds: float = 2.0


@dataclass
class ScraperSettings:
    timeout_seconds: int = 30
    max_retries: int = 3
    headless: bool = True
    user_agent_rotation: bool = True


@dataclass
class LocationFilter:
    usa_only: bool = True
    allow_remote_worldwide: bool = False
    allow_unknown_location: bool = True
    target_states: List[str] = field(default_factory=list)


@dataclass
class Profile:
    name: str
    target_job_titles: List[str]
    experience_levels: List[str]
    max_years_required: Optional[int]
    min_match_score: int

    def matches_title(self, job_title: str) -> bool:
        title_lower = job_title.lower()
        return any(t.lower() in title_lower for t in self.target_job_titles)


@dataclass
class JobBoardConfig:
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""


@dataclass
class ApplyScraperConfig:
    """Config used by ATS scrapers (companies/ + scrapers from apply fork)."""
    target_job_titles: List[str]
    target_locations: List[str]
    min_match_score: int
    experience_levels: List[str]
    my_years_experience: Optional[int]
    max_years_required: Optional[int]
    exclude_keywords: List[str]
    max_jobs_per_company: int
    resume_folder: str
    hours_threshold: int
    location_filter: LocationFilter
    output_dir: str
    db_dir: str
    log_level: str
    log_file: str
    company_updates_log: str
    rate_limit: RateLimit
    scraper: ScraperSettings
    job_boards: JobBoardConfig = field(default_factory=JobBoardConfig)
    profiles: List[Profile] = field(default_factory=list)


def load_apply_config(path: Optional[str] = None) -> ApplyScraperConfig:
    """Load apply-style config from config.yaml (project root) or given path."""
    if path is None:
        path = str(Path(__file__).resolve().parents[2] / "config.yaml")
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    lf_raw = raw.get("location_filter", {})
    rl_raw = raw.get("rate_limit", {})
    sc_raw = raw.get("scraper", {})
    jb_raw = raw.get("job_boards", {})

    profiles = []
    for p in raw.get("profiles", []):
        profiles.append(Profile(
            name=p.get("name", "General"),
            target_job_titles=p.get("target_job_titles", []),
            experience_levels=p.get("experience_levels", []),
            max_years_required=p.get("max_years_required"),
            min_match_score=p.get("min_match_score", 50),
        ))

    return ApplyScraperConfig(
        target_job_titles=raw.get("target_job_titles", []),
        target_locations=raw.get("target_locations", []),
        min_match_score=raw.get("min_match_score", 50),
        experience_levels=raw.get("experience_levels", []),
        my_years_experience=raw.get("my_years_experience"),
        max_years_required=raw.get("max_years_required"),
        exclude_keywords=raw.get("exclude_keywords", []),
        max_jobs_per_company=raw.get("max_jobs_per_company", 10),
        resume_folder=raw.get("resume_folder", "./resumes"),
        hours_threshold=raw.get("hours_threshold", 24),
        location_filter=LocationFilter(
            usa_only=lf_raw.get("usa_only", True),
            allow_remote_worldwide=lf_raw.get("allow_remote_worldwide", False),
            allow_unknown_location=lf_raw.get("allow_unknown_location", True),
            target_states=lf_raw.get("target_states", []),
        ),
        output_dir=raw.get("output_dir", "./output"),
        db_dir=raw.get("db_dir", "./db"),
        log_level=raw.get("log_level", "INFO"),
        log_file=raw.get("log_file", "./logs/scraper.log"),
        company_updates_log=raw.get("company_updates_log", "./logs/company_updates.log"),
        rate_limit=RateLimit(
            requests_per_second=rl_raw.get("requests_per_second", 2.0),
            min_delay_seconds=rl_raw.get("min_delay_seconds", 0.5),
            max_delay_seconds=rl_raw.get("max_delay_seconds", 2.0),
        ),
        scraper=ScraperSettings(
            timeout_seconds=sc_raw.get("timeout_seconds", 30),
            max_retries=sc_raw.get("max_retries", 3),
            headless=sc_raw.get("headless", True),
            user_agent_rotation=sc_raw.get("user_agent_rotation", True),
        ),
        job_boards=JobBoardConfig(
            adzuna_app_id=jb_raw.get("adzuna_app_id", ""),
            adzuna_app_key=jb_raw.get("adzuna_app_key", ""),
            jooble_api_key=jb_raw.get("jooble_api_key", ""),
        ),
        profiles=profiles,
    )
