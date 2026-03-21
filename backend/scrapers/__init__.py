"""ATS scrapers and company configs from jonathanrao99/apply. Use get_scraper(company, config) with ApplyScraperConfig."""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.scrapers.base import BaseScraper, Job

if TYPE_CHECKING:
    from backend.scrapers.apply_config import ApplyScraperConfig


def get_scraper(company: dict, config: "ApplyScraperConfig") -> BaseScraper:
    ats = company.get("ats", "custom").lower()
    if ats == "greenhouse":
        from backend.scrapers.greenhouse import GreenhouseScraper
        return GreenhouseScraper(company, config)
    elif ats == "lever":
        from backend.scrapers.lever import LeverScraper
        return LeverScraper(company, config)
    elif ats == "ashby":
        from backend.scrapers.ashby import AshbyScraper
        return AshbyScraper(company, config)
    elif ats == "workday":
        from backend.scrapers.workday import WorkdayScraper
        return WorkdayScraper(company, config)
    elif ats == "smartrecruiters":
        from backend.scrapers.smartrecruiters import SmartRecruitersScraper
        return SmartRecruitersScraper(company, config)
    elif ats == "adzuna":
        from backend.scrapers.adzuna import AdzunaScraper
        return AdzunaScraper(company, config)
    elif ats == "jooble":
        from backend.scrapers.jooble import JoobleScraper
        return JoobleScraper(company, config)
    else:
        from backend.scrapers.generic import GenericScraper
        return GenericScraper(company, config)


__all__ = ["get_scraper", "BaseScraper", "Job"]
