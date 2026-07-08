"""Shared MLB Stats API request plumbing."""

import threading
import time

import requests

from ..constants import API_RATE_LIMIT, API_TIMEOUT

BASE_URL = "https://statsapi.mlb.com/api/v1"
# The live feed (play-by-play) lives on the v1.1 API.
BASE_URL_V11 = "https://statsapi.mlb.com/api/v1.1"


class _RateLimiter:
    """Thread-safe limiter that paces calls to at most `rate` per second.

    Callers block in `acquire()` until their turn. Shared by every thread in
    both sync pipelines' ThreadPoolExecutors, so the *combined* request rate
    across all of them stays under the cap no matter how many workers exist.
    """

    def __init__(self, rate: float):
        self._interval = 1.0 / rate
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(self._next_slot, now)
            self._next_slot = start + self._interval
        wait = start - now
        if wait > 0:
            time.sleep(wait)


_rate_limiter = _RateLimiter(API_RATE_LIMIT)


def get_json(url: str, timeout: int = API_TIMEOUT) -> dict:
    """GET *url* and return the parsed JSON body; raises on HTTP errors."""
    _rate_limiter.acquire()
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
