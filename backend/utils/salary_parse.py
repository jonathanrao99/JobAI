"""
Extract annual salary min/max (USD) from free-text job descriptions.

Handles Dice-style blocks, inline ranges, and common ATS phrasing.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


def parse_salary_range_from_text(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Return (salary_min, salary_max) as integer annual USD, or (None, None).

    Tries, in order:
    - "Minimum Salary" ... "$ ..." ... "Maximum Salary" ... "$ ..." (Dice)
    - "Salary:" / "Compensation:" line with two dollar amounts
    - "USD X ... Y per year" / annually
    - First pair of $ amounts separated by a dash in the opening section
    """
    if not text or not isinstance(text, str):
        return None, None
    t = text.strip()
    if len(t) < 12:
        return None, None

    def money(s: str) -> Optional[float]:
        try:
            return float(re.sub(r"[,$\s]", "", s.strip()))
        except (ValueError, TypeError):
            return None

    def sane_pair(a: float, b: float) -> bool:
        hi = max(a, b)
        return 5000 <= hi <= 10_000_000

    # 1) Dice / structured: Minimum Salary ... $ ... Maximum Salary ... $
    m = re.search(
        r"minimum\s+salary\s*[\r\n\s]*\$\s*([\d,]+(?:\.\d+)?)"
        r"[\s\S]{0,6000}?"
        r"maximum\s+salary\s*[\r\n\s]*\$\s*([\d,]+(?:\.\d+)?)",
        t,
        re.IGNORECASE,
    )
    if m:
        a, b = money(m.group(1)), money(m.group(2))
        if a is not None and b is not None and sane_pair(a, b):
            lo, hi = int(min(a, b)), int(max(a, b))
            return lo, hi

    # 2) Salary: $X ... - ... $Y (same line or nearby)
    for pat in (
        r"salary\s*:\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[^$]{0,500}[-–—]\s*\$?\s*([\d,]+(?:\.\d+)?)",
        r"compensation\s*:\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[^$]{0,500}[-–—]\s*\$?\s*([\d,]+(?:\.\d+)?)",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            a, b = money(m.group(1)), money(m.group(2))
            if a is not None and b is not None and sane_pair(a, b):
                return int(min(a, b)), int(max(a, b))

    # 3) USD 170,000.00 to 210,000.00 per year (header-style)
    m = re.search(
        r"USD\s*([\d,]+(?:\.\d+)?)\s*(?:to|[-–—])\s*([\d,]+(?:\.\d+)?)\s*(?:per\s*year|annually|/yr|a\s*year)",
        t[:8000],
        re.IGNORECASE,
    )
    if m:
        a, b = money(m.group(1)), money(m.group(2))
        if a is not None and b is not None and sane_pair(a, b):
            return int(min(a, b)), int(max(a, b))

    # 4) Loose: $X ... - ... $Y (avoid matching tiny numbers — require comma or 5+ digit)
    head = t[:16000]
    m = re.search(
        r"\$\s*([\d,]{4,}(?:\.\d+)?)\s*[^$]{0,320}[-–—]\s*\$\s*([\d,]{4,}(?:\.\d+)?)",
        head,
        re.IGNORECASE,
    )
    if m:
        a, b = money(m.group(1)), money(m.group(2))
        if a is not None and b is not None and sane_pair(a, b):
            return int(min(a, b)), int(max(a, b))

    return None, None
