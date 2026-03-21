"""Rate limiter with user-agent rotation. From jonathanrao99/apply."""
from __future__ import annotations

import random
import time
from threading import Lock
from typing import Optional

_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


class RateLimiter:
    """Thread-safe rate limiter with per-domain state and UA rotation."""

    def __init__(
        self,
        requests_per_second: float = 2.0,
        min_delay: float = 0.5,
        max_delay: float = 2.0,
        rotate_user_agents: bool = True,
    ):
        self.min_interval = 1.0 / requests_per_second
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_call: dict[str, float] = {}
        self._lock = Lock()
        self._user_agents = self._load_user_agents(rotate_user_agents)

    def _load_user_agents(self, rotate: bool) -> list[str]:
        if not rotate:
            return [_FALLBACK_UAS[0]]
        try:
            from fake_useragent import UserAgent
            ua = UserAgent()
            return [ua.random for _ in range(20)]
        except Exception:
            return _FALLBACK_UAS.copy()

    def wait(self, domain: str = "default") -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(domain, 0.0)
            elapsed = now - last
            wait_time = max(self.min_interval - elapsed, self.min_delay)
            jitter = random.uniform(0, self.max_delay - self.min_delay)
            total_wait = wait_time + jitter
            if total_wait > 0:
                time.sleep(total_wait)
            self._last_call[domain] = time.monotonic()

    def get_user_agent(self) -> str:
        return random.choice(self._user_agents)

    def get_headers(self, extra: Optional[dict] = None) -> dict:
        headers = {
            "User-Agent": self.get_user_agent(),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        if extra:
            headers.update(extra)
        return headers
