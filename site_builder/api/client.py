"""Shared MLB Stats API request plumbing.

錯誤處理約定：``get_json`` / ``get_text`` 在重試用盡後一律丟出 ``FetchError``
（requests 的例外基底），api/ 底下的函式不自行吞掉，交給 sync/ 的呼叫端決定
「保留舊值、下次重抓」；呼叫端只 catch ``FetchError``，程式 bug（KeyError 等）
不會被誤報成網路錯誤。
"""

import logging
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..constants import (
    API_BACKOFF_FACTOR,
    API_MAX_RETRIES,
    API_POOL_MAXSIZE,
    API_RATE_LIMIT,
    API_TIMEOUT,
)
from ..util.log import describe_exc

logger = logging.getLogger(__name__)

# HTTP 錯誤、連線/逾時、重試用盡（RetryError）、JSON 解析失敗都是它的子類別
FetchError = requests.exceptions.RequestException

# requests 以 preload_content=False 呼叫 urllib3，body 是在 urllib3 的 Retry
# 結束之後才讀：讀到一半斷線（ChunkedEncodingError）或 200 卻回殘缺內容
# （JSONDecodeError）都不會被 Retry 重試，由 _get_with_body_retry 補上。
_BODY_ERRORS = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
    requests.exceptions.JSONDecodeError,
)

BASE_URL = "https://statsapi.mlb.com/api/v1"


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

# A requests.Session is not guaranteed thread-safe, so each worker thread gets
# its own. Reusing a Session across a thread's many requests keeps the TCP/TLS
# connection alive (HTTP keep-alive) instead of paying the ~0.15s connect cost
# on every call.
_thread_local = threading.local()


class _LoggingRetry(Retry):
    """每次重試都記一行 WARNING 的 urllib3 Retry。

    urllib3 只把連線/讀取錯誤的重試記成 WARNING，因 429/5xx 狀態碼而重試時只記
    DEBUG，被限流時 log 完全看不到。urllib3 自己的重試訊息由
    ``util.log.setup_logging`` 濾掉，避免同一次重試印兩行。
    ``Retry.new()`` 以 ``type(self)`` 建立下一個實例，所以每一次 increment 都會經過這裡。
    """

    def increment(self, method=None, url=None, response=None, error=None,
                  _pool=None, _stacktrace=None):
        # 額度用完時 super() 直接丟 MaxRetryError，最終失敗由呼叫端記錄，這裡不重複
        new_retry = super().increment(method, url, response, error, _pool, _stacktrace)
        if response is not None and response.status:
            reason = f"HTTP {response.status}"
        elif error is not None:
            reason = describe_exc(error)
        else:
            reason = "unknown"
        host = f"https://{_pool.host}" if _pool is not None else ""
        logger.warning(
            "retry %d/%d %s %s%s (%s)",
            API_MAX_RETRIES - new_retry.total, API_MAX_RETRIES, method, host, url, reason,
        )
        return new_retry


def _build_session() -> requests.Session:
    """Create a Session whose adapter pools connections and retries safely.

    Retry policy (429/502/503/504, connect/read errors) with exponential
    backoff, jitter, and Retry-After support is delegated to urllib3's Retry
    rather than hand-rolled. Only idempotent GETs are retried.
    """
    session = requests.Session()
    retry = _LoggingRetry(
        total=API_MAX_RETRIES,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        backoff_factor=API_BACKOFF_FACTOR,
        backoff_jitter=API_BACKOFF_FACTOR,
        respect_retry_after_header=True,
        raise_on_status=True,
    )
    adapter = HTTPAdapter(pool_maxsize=API_POOL_MAXSIZE, max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _build_session()
        _thread_local.session = session
    return session


def _request(url: str, timeout: int = API_TIMEOUT) -> requests.Response:
    """Rate-limited GET that reuses this thread's pooled, retrying Session.

    Raises on HTTP errors (after retries are exhausted). Shared by both
    get_json and get_text so every outbound call is paced, pooled, and retried
    the same way.
    """
    _rate_limiter.acquire()
    resp = _session().get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def _get_with_body_retry(url: str, timeout: int, parse):
    """``parse(_request(url))``，body 讀取或解析失敗時以同樣的退避策略重試。"""
    for attempt in range(1, API_MAX_RETRIES + 2):
        try:
            return parse(_request(url, timeout))
        except _BODY_ERRORS as e:
            if attempt > API_MAX_RETRIES:
                raise
            logger.warning(
                "retry %d/%d GET %s (%s)", attempt, API_MAX_RETRIES, url, describe_exc(e)
            )
            # 與 urllib3 Retry 相同的指數退避：backoff_factor * 2^(n-1)
            time.sleep(API_BACKOFF_FACTOR * 2 ** (attempt - 1))


def get_json(url: str, timeout: int = API_TIMEOUT) -> dict:
    """GET *url* and return the parsed JSON body; raises FetchError after retries."""
    return _get_with_body_retry(url, timeout, lambda resp: resp.json())


def get_text(url: str, timeout: int = API_TIMEOUT) -> str:
    """GET *url* and return the raw text body; raises FetchError after retries.

    Used by scrapers (e.g. api/tjstats.py) that parse HTML rather than JSON,
    so they share the same pooling/retry/rate-limit plumbing as get_json.
    """
    return _get_with_body_retry(url, timeout, lambda resp: resp.text)
