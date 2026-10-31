"""Crustdata REST adapter (plan v2 §6, §20).

One async client with a per-endpoint rolling limiter, a development cache keyed
by (endpoint, body hash, API version), a polymorphic error normalizer, and an
attempt record for every call carrying `x-credits-used` and the run mode.

Modes:
- LIVE makes real calls (and writes the dev cache when `use_cache`).
- CACHED serves dev-cache hits and falls through to a live call on a miss;
  every attempt carries the mode it was actually served in.
- FIXTURE replays `fixtures/<name>/crustdata/*.json` and never needs a key.

Retry policy (§6.3): 429 waits the reset plus jitter, at most 3 tries; 5xx and
network errors get one retry if the deadline allows; everything else raises.
Request headers are never logged (the key is in `authorization`).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from proofroom import config
from proofroom.errors import ConfigError, CrustError

log = logging.getLogger(__name__)

LIVE, CACHED, FIXTURE = "LIVE", "CACHED", "FIXTURE"
MODES = (LIVE, CACHED, FIXTURE)

# Effective rpm measured in day-check 1.1 (event key, 31 Oct 10:12 IST).
RPM = {
    "/company/identify": 30,
    "/company/enrich": 15,
    "/person/search": 30,
    "/person/enrich": 15,
    "/web/search/live": 10,
    "/web/enrich/live": 10,
    "/account/credits": 300,
    "/account/endpoints": 300,
}
MAX_429_TRIES = 3
REQUEST_TIMEOUT_S = 30.0
MIN_TIME_FOR_RETRY_S = 15.0


def normalize_error(status: int, body: str | bytes | None) -> CrustError:
    """Map every non-2xx body to one CrustError (§6.3).

    1. `error` is an object  -> its type, message and metadata.
    2. `error` is a string   -> that is the type; message from description|reason.
    3. only a top-level `message` -> type `unauthorized`.
    4. not JSON (or JSON of another shape) -> `http_<status>`, first 200 chars.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    body = body or ""
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return CrustError(status, f"http_{status}", body[:200])

    denied = _as_str_list(data.get("denied_fields"))
    err = data.get("error")
    if isinstance(err, dict):
        meta = err.get("metadata")
        if isinstance(meta, dict):
            denied = denied or _as_str_list(meta.get("denied_fields"))
        return CrustError(status, str(err.get("type") or f"http_{status}"),
                          str(err.get("message") or ""), denied)
    if isinstance(err, str) and err:
        msg = data.get("description") or data.get("reason") or data.get("message") or ""
        return CrustError(status, err, str(msg), denied)
    if isinstance(data.get("message"), str):
        return CrustError(status, "unauthorized", data["message"], denied)
    return CrustError(status, f"http_{status}", body[:200], denied)


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


@dataclass
class Attempt:
    """One HTTP attempt. Failed attempts are kept, never dropped (CLAUDE.md §3)."""

    endpoint: str
    mode: str
    status: int
    seconds: float
    credits_used: str  # exact decimal string from `x-credits-used`, or "unknown"
    cache_key: str
    error: dict | None = None
    ratelimit_remaining: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class RateLimiter:
    """Rolling one-minute window for one endpoint, shared process-wide."""

    def __init__(self, rpm: int, clock: Callable[[], float] = time.monotonic):
        if rpm < 1:
            raise ValueError("rpm must be >= 1")
        self.rpm = rpm
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= 60:
            self._calls.popleft()

    def wait_needed(self) -> float:
        now = self._clock()
        self._prune(now)
        return 0.0 if len(self._calls) < self.rpm else 60 - (now - self._calls[0]) + 0.05

    async def acquire(self) -> None:
        async with self._lock:
            while (wait := self.wait_needed()) > 0:
                log.info("rate limiter: waiting %.1fs", wait)
                await asyncio.sleep(wait)
            self._calls.append(self._clock())


_LIMITERS: dict[str, RateLimiter] = {}


def limiter_for(endpoint: str) -> RateLimiter:
    if endpoint not in _LIMITERS:
        _LIMITERS[endpoint] = RateLimiter(RPM.get(endpoint, 10))
    return _LIMITERS[endpoint]


def cache_key(endpoint: str, body: Any) -> str:
    """Stable key over (endpoint, canonical body hash, API version)."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    raw = f"{endpoint}|{hashlib.sha256(canon.encode()).hexdigest()}|{config.CRUSTDATA_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _slug(endpoint: str) -> str:
    return endpoint.strip("/").replace("/", "_")


def _reset_seconds(headers: httpx.Headers) -> float:
    """Seconds to wait after a 429. `x-ratelimit-reset` was observed as a raw 60, not
    an epoch (day-check 1.10), so both forms are accepted; the wait is capped at 60 s."""
    for name in ("retry-after", "x-ratelimit-reset"):
        raw = headers.get(name)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 10_000:  # epoch seconds
            value -= time.time()
        return max(0.5, min(value, 60.0))
    return 5.0


class Crustdata:
    """Async Crustdata client. Use as `async with Crustdata(mode) as c: ...`."""

    def __init__(self, mode: str = LIVE, *, use_cache: bool = True, fixture: str = "",
                 deadline: float | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 cache_dir: Path | None = None, fixtures_dir: Path | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 limiters: bool = True):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if mode == FIXTURE and not fixture:
            raise ValueError("FIXTURE mode needs a fixture name")
        if mode != FIXTURE and not config.crustdata_key():
            raise ConfigError("CRUSTDATA_API_KEY is not set (environment or .env)")
        self.mode = mode
        self.use_cache = use_cache and mode != FIXTURE
        self.deadline = deadline  # a time.monotonic() value; None means no deadline
        self.cache_dir = cache_dir or config.CACHE_DIR / "crustdata"
        self.fixture_dir = (fixtures_dir or config.FIXTURES_DIR) / fixture / "crustdata"
        self.attempts: list[Attempt] = []
        self._sleep = sleep
        self._transport = transport
        self._limiters = limiters
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "Crustdata":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=config.CRUSTDATA_BASE,
                headers={"authorization": f"Bearer {config.crustdata_key()}",
                         "x-api-version": config.CRUSTDATA_VERSION,
                         "content-type": "application/json"},
                timeout=httpx.Timeout(REQUEST_TIMEOUT_S, connect=10.0),
                transport=self._transport,
            )
        return self._client

    def time_left(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - time.monotonic()

    def _record(self, attempt: Attempt) -> None:
        self.attempts.append(attempt)
        if attempt.error:
            log.warning("crustdata %s %s -> %s %s", attempt.mode, attempt.endpoint,
                        attempt.status, attempt.error.get("type"))
        else:
            log.info("crustdata %s %s -> %s in %.2fs credits=%s", attempt.mode,
                     attempt.endpoint, attempt.status, attempt.seconds, attempt.credits_used)

    # ---- cache and fixtures -------------------------------------------------
    def _read_record(self, path: Path) -> dict | None:
        """Read a cache or fixture record; a corrupt file is logged and treated as a miss."""
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            log.warning("ignoring unreadable record %s: %s", path.name, e)
            return None
        if not isinstance(rec, dict) or "body" not in rec:
            log.warning("ignoring malformed record %s", path.name)
            return None
        return rec

    def _write_cache(self, path: Path, rec: dict) -> None:
        """Atomic write; a cache failure never fails the run."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as e:
            log.warning("dev cache write failed for %s: %s", path.name, e)

    # ---- core request -------------------------------------------------------
    async def request(self, method: str, endpoint: str, body: Any = None) -> Any:
        key = cache_key(endpoint, body)
        name = f"{_slug(endpoint)}-{key}.json"

        if self.mode == FIXTURE:
            rec = self._read_record(self.fixture_dir / name)
            if rec is None:
                err = CrustError(0, "fixture_missing", f"no fixture for {endpoint} ({key})")
                self._record(Attempt(endpoint, FIXTURE, 0, 0.0, "0", key, err.as_dict()))
                raise err
            status = int(rec.get("status", 200))
            self._record(Attempt(endpoint, FIXTURE, status, 0.0,
                                 str(rec.get("credits_used", "unknown")), key))
            return rec["body"]

        if self.mode == CACHED and self.use_cache:
            rec = self._read_record(self.cache_dir / name)
            if rec is not None:
                self._record(Attempt(endpoint, CACHED, int(rec.get("status", 200)), 0.0,
                                     "0", key))
                return rec["body"]

        data, status, credits = await self._live(method, endpoint, body, key)
        if self.use_cache:
            self._write_cache(self.cache_dir / name, {
                "endpoint": endpoint, "request": body, "status": status,
                "credits_used": credits, "body": data})
        return data

    async def _live(self, method: str, endpoint: str, body: Any,
                    key: str) -> tuple[Any, int, str]:
        tries_429 = 0
        retried = False  # one retry shared by 5xx and network errors
        while True:
            if self.time_left() <= 1:
                err = CrustError(0, "deadline", "no time left for retrieval")
                self._record(Attempt(endpoint, LIVE, 0, 0.0, "unknown", key, err.as_dict()))
                raise err
            if self._limiters:
                await limiter_for(endpoint).acquire()
            t0 = time.monotonic()
            timeout = max(1.0, min(REQUEST_TIMEOUT_S, self.time_left()))
            try:
                resp = await self._http().request(method, endpoint, json=body, timeout=timeout)
            except httpx.HTTPError as e:
                err = CrustError(0, "network", f"{type(e).__name__}: {e}"[:200])
                self._record(Attempt(endpoint, LIVE, 0, round(time.monotonic() - t0, 3),
                                     "unknown", key, err.as_dict()))
                if not retried and self.time_left() > MIN_TIME_FOR_RETRY_S:
                    retried = True
                    continue
                raise err from e

            secs = round(time.monotonic() - t0, 3)
            credits = resp.headers.get("x-credits-used", "unknown")
            remaining = resp.headers.get("x-ratelimit-remaining", "")

            if resp.is_success:
                try:
                    data = resp.json()
                except ValueError:
                    err = CrustError(resp.status_code, "invalid_json",
                                     resp.text[:200] or "empty body")
                    self._record(Attempt(endpoint, LIVE, resp.status_code, secs, credits, key,
                                         err.as_dict(), remaining))
                    raise err from None
                self._record(Attempt(endpoint, LIVE, resp.status_code, secs, credits, key,
                                     None, remaining))
                return data, resp.status_code, credits

            err = normalize_error(resp.status_code, resp.content)
            self._record(Attempt(endpoint, LIVE, resp.status_code, secs, credits, key,
                                 err.as_dict(), remaining))
            if resp.status_code == 429:
                tries_429 += 1
                wait = _reset_seconds(resp.headers) + random.uniform(0.2, 1.0)
                if tries_429 < MAX_429_TRIES and wait < self.time_left() - 1:
                    await self._sleep(wait)
                    continue
            elif resp.status_code >= 500 and not retried \
                    and self.time_left() > MIN_TIME_FOR_RETRY_S:
                retried = True
                continue
            raise err

    # ---- endpoints ----------------------------------------------------------
    async def credits(self) -> Any:
        return await self.request("GET", "/account/credits")

    async def identify_domain(self, domain: str) -> Any:
        return await self.request("POST", "/company/identify", {"domains": [_clean(domain)]})

    async def identify_names(self, names: list[str]) -> Any:
        clean = [n.strip() for n in names if n and n.strip()]
        if not clean:
            return []
        return await self.request("POST", "/company/identify", {"names": clean[:25]})

    async def company_enrich(self, company_id: int,
                             fields: tuple[str, ...] = ("basic_info", "funding", "people",
                                                        "news")) -> Any:
        return await self.request("POST", "/company/enrich", {
            "crustdata_company_ids": [int(company_id)], "fields": list(fields)})

    async def founder_search(self, company_id: int) -> Any:
        """S1 fallback with the PC-3 `founder` OR `cofounder` title filter.
        `fields` is always sent and excludes experience (0.13 vs 0.23 per result)."""
        title = "experience.employment_details.current.title"
        return await self.request("POST", "/person/search", {
            "filters": {"op": "and", "conditions": [
                {"field": "experience.employment_details.current.company_id", "type": "=",
                 "value": int(company_id)},
                {"op": "or", "conditions": [
                    {"field": title, "type": "(.)", "value": "founder"},
                    {"field": title, "type": "(.)", "value": "cofounder"}]}]},
            "fields": ["crustdata_person_id", "basic_profile", "social_handles"],
            "limit": 10})

    async def person_enrich(self, profile_urls: list[str]) -> Any:
        urls = [u for u in profile_urls if u][:3]
        if not urls:
            return []
        return await self.request("POST", "/person/enrich", {
            "professional_network_profile_urls": urls,
            "fields": ["basic_profile", "experience", "social_handles"]})

    async def web_search(self, query: str, *, sources: tuple[str, ...] = ("news",),
                         site: str = "", start_date: int | None = None) -> Any:
        body: dict[str, Any] = {"query": query, "sources": list(sources)}
        if site:
            body["site"] = site
        if start_date:
            body["start_date"] = int(start_date)
        return await self.request("POST", "/web/search/live", body)

    async def web_fetch(self, urls: list[str]) -> Any:
        clean = [u for u in urls if u][:3]
        if not clean:
            return []
        return await self.request("POST", "/web/enrich/live", {"urls": clean})


def _clean(domain: str) -> str:
    d = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    if not d or "." not in d:
        raise ValueError(f"not a domain: {domain!r}")
    return d


def sum_credits(attempts: list[Attempt]) -> tuple[float, int]:
    """Total of known LIVE `x-credits-used`, and how many LIVE attempts had unknown cost."""
    total, unknown = 0.0, 0
    for a in attempts:
        if a.mode != LIVE:
            continue
        try:
            total += float(a.credits_used)
        except ValueError:
            unknown += 1
    return round(total, 4), unknown


def match_fetch_results(requested: list[str], results: Any) -> tuple[dict[str, dict], list[str]]:
    """Web Fetch order is not guaranteed: match by URL (§6.2). Returns successes by
    requested URL and the failed URLs (= requested minus succeeded), api-8."""
    ok: dict[str, dict] = {}
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict) or not item.get("success") or not item.get("url"):
            continue
        url = item["url"]
        for req in requested:
            if req not in ok and _same_url(req, url):
                ok[req] = item
                break
    return ok, [u for u in requested if u not in ok]


def _same_url(a: str, b: str) -> bool:
    def norm(u: str) -> str:
        u = u.strip().lower().split("#", 1)[0]
        for p in ("https://", "http://"):
            if u.startswith(p):
                u = u[len(p):]
        if u.startswith("www."):
            u = u[4:]
        return u.rstrip("/")
    return norm(a) == norm(b)
