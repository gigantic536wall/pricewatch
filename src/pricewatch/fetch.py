"""A polite HTTP fetcher for shop pages.

- obeys robots.txt (and its Crawl-delay)
- waits between two requests to the same host
- limits how many pages are loaded at the same time
- retries temporary failures (timeouts, 429, 5xx) with backoff, honouring Retry-After
"""

from __future__ import annotations

import asyncio
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings, get_settings

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


class Fetcher:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        backoff: float = 1.0,
        max_wait: float = 60.0,
    ):
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": self.settings.user_agent, "Accept-Language": "de,en;q=0.8"},
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.max_wait = max_wait

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- politeness ---------------------------------------------------------------------------

    async def _sleep(self, seconds: float) -> None:  # separate method so tests can skip waiting
        await asyncio.sleep(seconds)

    async def _robots_for(self, origin: str) -> RobotFileParser | None:
        """robots.txt of a site; None means "everything allowed"."""
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None
        try:
            response = await self._client.get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            parser = None  # robots.txt unreachable: like Google, treat the site as crawlable
        else:
            parser = RobotFileParser()
            if response.status_code in (401, 403):
                parser.disallow_all = True
            elif response.status_code >= 500:
                parser.disallow_all = True  # server trouble: don't crawl now
            elif response.status_code >= 400:
                parser = None  # no robots.txt
            else:
                parser.parse(response.text.splitlines())
        self._robots[origin] = parser
        return parser

    def _host_delay(self, robots: RobotFileParser | None) -> float:
        crawl_delay = robots.crawl_delay(self.settings.user_agent) if robots else None
        return max(self.settings.per_host_delay, float(crawl_delay or 0))

    async def _wait_for_host(self, host: str, delay: float) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = last + delay - time.monotonic()
            if wait > 0:
                await self._sleep(wait)
        self._last_request[host] = time.monotonic()

    # ---- public API ---------------------------------------------------------------------------

    async def get(self, url: str) -> str:
        """HTML of the page, or FetchError."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise FetchError(f"Not an http(s) URL: {url}")
        origin = f"{parts.scheme}://{parts.netloc}"

        async with self._semaphore:
            robots = await self._robots_for(origin) if self.settings.respect_robots_txt else None
            if robots is not None and not robots.can_fetch(self.settings.user_agent, url):
                raise FetchError("Blocked by robots.txt")

            delay = self._host_delay(robots)
            lock = self._host_locks.setdefault(parts.netloc, asyncio.Lock())
            last_error: FetchError | None = None

            for attempt in range(1, self.max_attempts + 1):
                async with lock:
                    await self._wait_for_host(parts.netloc, delay)
                    try:
                        response = await self._client.get(url)
                    except httpx.TimeoutException:
                        last_error = FetchError("Timeout", retryable=True)
                        response = None
                    except httpx.HTTPError as e:
                        last_error = FetchError(f"Network error: {type(e).__name__}", retryable=True)
                        response = None

                if response is not None:
                    if response.status_code < 400:
                        return response.text
                    retryable = response.status_code in RETRYABLE_STATUS
                    last_error = FetchError(f"HTTP {response.status_code}", retryable=retryable)
                    if not retryable:
                        raise last_error
                    wait = _retry_after_seconds(response)
                else:
                    wait = None

                if attempt < self.max_attempts:
                    if wait is None:
                        wait = self.backoff * 2 ** (attempt - 1)  # exponential backoff: 1 s, 2 s, 4 s …
                    await self._sleep(min(wait, self.max_wait))

            assert last_error is not None
            raise last_error
