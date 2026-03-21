"""Parse and classify job location strings. From jonathanrao99/apply."""
from __future__ import annotations

import re
from typing import Tuple

# US state abbreviations and full names
_US_STATES_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
}

_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}

_REMOTE_KEYWORDS = {
    "remote", "work from home", "wfh", "fully remote", "100% remote",
    "distributed", "anywhere",
}

_HYBRID_KEYWORDS = {"hybrid", "partial remote", "flexible", "flex"}

_ONSITE_KEYWORDS = {"on-site", "onsite", "on site", "in-office", "in office", "in person"}

_USA_KEYWORDS = {
    "united states", "usa", "us", "u.s.", "u.s.a.", "america",
}


def parse_location(raw: str) -> dict:
    """
    Returns a dict with keys:
      location       : cleaned display string
      usa_based      : "Yes" | "No" | "Unknown"
      remote_type    : "Remote" | "Hybrid" | "On-site" | "Remote-USA-Only" | "Remote-Worldwide"
      state          : two-letter state code if US, else ""
      city           : city name if parseable, else ""
    """
    if not raw or not raw.strip():
        return _unknown()

    text = raw.strip()
    lower = text.lower()

    is_remote = any(kw in lower for kw in _REMOTE_KEYWORDS)
    is_hybrid = any(kw in lower for kw in _HYBRID_KEYWORDS)
    is_onsite = any(kw in lower for kw in _ONSITE_KEYWORDS)
    usa_based = _detect_usa(lower, text)

    if is_remote:
        if "worldwide" in lower or "global" in lower or "international" in lower:
            remote_type = "Remote-Worldwide"
        elif usa_based == "Yes":
            remote_type = "Remote-USA-Only"
        elif usa_based == "No":
            remote_type = "Remote-Worldwide"
        else:
            remote_type = "Remote"
    elif is_hybrid:
        remote_type = "Hybrid"
    elif is_onsite:
        remote_type = "On-site"
    else:
        remote_type = "On-site"

    city, state = _extract_city_state(text)
    if state and state.upper() in _US_STATES_ABBR:
        usa_based = "Yes"

    return {
        "location": text,
        "usa_based": usa_based,
        "remote_type": remote_type,
        "city": city,
        "state": state.upper() if state else "",
    }


def _detect_usa(lower: str, text: str) -> str:
    if any(kw in lower for kw in _USA_KEYWORDS):
        return "Yes"
    if any(name in lower for name in _US_STATE_NAMES):
        return "Yes"
    match = re.search(r",\s*([A-Z]{2})\b", text)
    if match and match.group(1) in _US_STATES_ABBR:
        return "Yes"
    non_us = ["canada", "uk", "united kingdom", "europe", "india", "germany",
              "france", "australia", "singapore", "london", "toronto", "berlin"]
    if any(c in lower for c in non_us):
        return "No"
    return "Unknown"


def _extract_city_state(text: str) -> Tuple[str, str]:
    match = re.search(r"([A-Za-z\s\.]+),\s*([A-Z]{2})\b", text)
    if match:
        city = match.group(1).strip()
        state = match.group(2).strip()
        if state in _US_STATES_ABBR:
            return city, state
    return "", ""


def _unknown() -> dict:
    return {
        "location": "",
        "usa_based": "Unknown",
        "remote_type": "On-site",
        "city": "",
        "state": "",
    }


def passes_location_filter(loc_info: dict, filter_cfg) -> bool:
    """Returns True if the job should be included based on location_filter config."""
    usa = loc_info["usa_based"]
    remote_type = loc_info["remote_type"]
    if remote_type == "Remote-Worldwide":
        return bool(filter_cfg.allow_remote_worldwide)
    if filter_cfg.usa_only:
        if usa == "No":
            return False
        if usa == "Unknown" and not filter_cfg.allow_unknown_location:
            return False
    if filter_cfg.target_states:
        state = loc_info["state"]
        if state and state not in filter_cfg.target_states:
            if remote_type not in ("Remote", "Remote-USA-Only"):
                return False
    return True
