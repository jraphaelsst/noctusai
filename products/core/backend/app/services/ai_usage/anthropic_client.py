"""Anthropic Admin usage/cost analytics adapter: Protocol + Fake + Real + factory.

Real talks raw httpx to the beta endpoints (header `anthropic-beta: analytics-usage-cost-2026-08-24`):
`/v1/organizations/analytics/usage`, `/analytics/cost`, `/v1/organizations/rate_limits`. Costs arrive as
decimal CENTS strings and stay cents here (the BE converts to USD at read time).

Failure vocabulary (the sync job maps it to `ai_source_sync_runs`):
* `SourceUnavailable(reason_code)` — no admin key, or 403 (an Individual Org has no Admin API).
* `SourceError(reason_code, http_status)` — http_4xx / http_5xx / schema_drift.
The key is never logged, never put in an exception message and never part of `repr`.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

BETA_HEADER = "analytics-usage-cost-2026-08-24"
API_VERSION = "2026-10-21"
BASE_URL = "https://api.anthropic.com"
USAGE_GROUP_BY = ("model", "workspace_id", "api_key_id", "service_tier", "context_window")
COST_GROUP_BY = ("model", "workspace_id", "api_key_id", "cost_type", "token_type")
PAGE_LIMIT = 1000
MAX_PAGES = 500
MAX_429_RETRIES = 4


class SourceUnavailable(Exception):
    """The source cannot be read at all (no_admin_key | individual_org)."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class SourceError(Exception):
    """A real failure (http_4xx | http_5xx | schema_drift)."""

    def __init__(self, reason_code: str, message: str = "", http_status: Optional[int] = None):
        super().__init__(f"{reason_code}: {message}" if message else reason_code)
        self.reason_code = reason_code
        self.http_status = http_status


@dataclass(frozen=True)
class UsageRow:
    day: date
    model: Optional[str] = None
    workspace_id: Optional[str] = None
    api_key_id: Optional[str] = None
    service_tier: Optional[str] = None
    context_window: Optional[str] = None
    uncached_input: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0
    output_tokens: int = 0
    web_search_requests: Optional[int] = None
    requests: Optional[int] = None


@dataclass(frozen=True)
class CostRow:
    day: date
    model: Optional[str] = None
    workspace_id: Optional[str] = None
    api_key_id: Optional[str] = None
    cost_type: Optional[str] = None
    token_type: Optional[str] = None
    amount_cents: Decimal = Decimal(0)
    list_amount_cents: Optional[Decimal] = None


@dataclass(frozen=True)
class RateLimitRow:
    scope: str  # 'org' | 'workspace'
    workspace_id: Optional[str]
    model_group: str
    metric: str
    limit: int


@dataclass(frozen=True)
class Pull:
    rows: list
    data_refreshed_at: datetime


class AnthropicAdminClient(Protocol):
    def fetch_usage(self, start: date, end: date) -> Pull: ...  # inclusive days (UTC)

    def fetch_cost(self, start: date, end: date) -> Pull: ...

    def fetch_rate_limits(self) -> list[RateLimitRow]: ...


# ── Fake ────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class FakeAnthropicClient:
    """Deterministic in-memory adapter. `usage`/`cost` are filtered to the requested window like the API."""

    usage: list[UsageRow] = field(default_factory=list)
    cost: list[CostRow] = field(default_factory=list)
    rate_limits: list[RateLimitRow] = field(default_factory=list)
    data_refreshed_at: datetime = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    unavailable: Optional[str] = None
    error: Optional[SourceError] = None
    calls: list[tuple] = field(default_factory=list)

    def _guard(self) -> None:
        if self.unavailable:
            raise SourceUnavailable(self.unavailable)
        if self.error:
            raise self.error

    def fetch_usage(self, start: date, end: date) -> Pull:
        self.calls.append(("usage", start, end))
        self._guard()
        return Pull([r for r in self.usage if start <= r.day <= end], self.data_refreshed_at)

    def fetch_cost(self, start: date, end: date) -> Pull:
        self.calls.append(("cost", start, end))
        self._guard()
        return Pull([r for r in self.cost if start <= r.day <= end], self.data_refreshed_at)

    def fetch_rate_limits(self) -> list[RateLimitRow]:
        self.calls.append(("rate_limits",))
        self._guard()
        return list(self.rate_limits)


# ── Real ────────────────────────────────────────────────────────────────────────────────────────────────────
def _parse_ts(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SourceError("schema_drift", f"bad timestamp: {value!r}") from exc


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SourceError("schema_drift", f"bad decimal: {value!r}") from exc


def _opt(group: dict, key: str) -> Optional[str]:
    v = group.get(key)
    return None if v in (None, "") else str(v)


def parse_usage_row(raw: dict) -> UsageRow:
    try:
        u = raw["usage"]
        cc = u.get("cache_creation") or {}
        g = raw["group"]
        return UsageRow(
            day=_parse_ts(raw["starting_at"]).date(),
            model=_opt(g, "model"), workspace_id=_opt(g, "workspace_id"), api_key_id=_opt(g, "api_key_id"),
            service_tier=_opt(g, "service_tier"), context_window=_opt(g, "context_window"),
            uncached_input=int(u["uncached_input_tokens"]),
            cache_write_5m=int(cc.get("ephemeral_5m_input_tokens", 0) or 0),
            cache_write_1h=int(cc.get("ephemeral_1h_input_tokens", 0) or 0),
            cache_read=int(u["cache_read_input_tokens"]),
            output_tokens=int(u["output_tokens"]),
            web_search_requests=(u.get("server_tool_use") or {}).get("web_search_requests"),
            requests=u.get("requests"),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SourceError("schema_drift", f"usage row: {type(exc).__name__}") from exc


def parse_cost_row(raw: dict) -> CostRow:
    try:
        c = raw["cost"]
        if c.get("currency") != "USD":
            raise SourceError("schema_drift", "cost currency is not USD")
        g = raw["group"]
        la = c.get("list_amount")
        return CostRow(
            day=_parse_ts(raw["starting_at"]).date(),
            model=_opt(g, "model"), workspace_id=_opt(g, "workspace_id"), api_key_id=_opt(g, "api_key_id"),
            cost_type=_opt(g, "cost_type"), token_type=_opt(g, "token_type"),
            amount_cents=_dec(c["amount"]), list_amount_cents=None if la is None else _dec(la),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise SourceError("schema_drift", f"cost row: {type(exc).__name__}") from exc


class RealAnthropicClient:
    """Raw-httpx adapter. Retries live HERE (and only here): 429 honours Retry-After, else jittered backoff."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout_s: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._key = (api_key or "").strip()
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=httpx.Timeout(timeout_s), transport=transport)
        self._sleep = sleep

    def __repr__(self) -> str:  # never expose the key
        return f"RealAnthropicClient(base_url={self._base!r}, key={'set' if self._key else 'unset'})"

    def _headers(self) -> dict:
        return {
            "x-api-key": self._key,
            "anthropic-version": API_VERSION,
            "anthropic-beta": BETA_HEADER,
            "user-agent": "NoctusAI-usage-sync/1.0 (https://noctusai.com)",
        }

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict:
        if not self._key:
            raise SourceUnavailable("no_admin_key")
        for attempt in range(MAX_429_RETRIES + 1):
            try:
                resp = self._client.get(self._base + path, params=params, headers=self._headers())
            except httpx.HTTPError as exc:
                raise SourceError("http_5xx", f"transport: {type(exc).__name__}") from exc
            if resp.status_code == 429 and attempt < MAX_429_RETRIES:
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except ValueError:
                    wait = min(60.0, 2.0 ** attempt)
                wait += random.uniform(0, 1.0)
                logger.warning("anthropic admin API 429 on %s; retry %d in %.1fs", path, attempt + 1, wait)
                self._sleep(wait)
                continue
            break
        if resp.status_code == 403:
            raise SourceUnavailable("individual_org")
        if resp.status_code >= 500:
            raise SourceError("http_5xx", http_status=resp.status_code)
        if resp.status_code >= 400:
            raise SourceError("http_4xx", http_status=resp.status_code)
        try:
            body = resp.json()
        except ValueError as exc:
            raise SourceError("schema_drift", "response is not JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise SourceError("schema_drift", "response lacks data[]")
        return body

    def _pull(self, path: str, group_by: tuple, start: date, end: date, parse: Callable[[dict], Any]) -> Pull:
        base = [
            ("starting_at", f"{start.isoformat()}T00:00:00Z"),
            ("ending_at", f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z"),
            ("time_bucket_width", "1d"),
            ("limit", str(PAGE_LIMIT)),
        ] + [("group_by[]", g) for g in group_by]
        rows: list = []
        refreshed: Optional[datetime] = None
        page: Optional[str] = None
        for _ in range(MAX_PAGES):
            body = self._get(path, base + ([("page", page)] if page else []))
            rows.extend(parse(r) for r in body["data"])
            if body.get("data_refreshed_at"):
                refreshed = _parse_ts(body["data_refreshed_at"])
            if not body.get("has_more"):
                if refreshed is None:
                    raise SourceError("schema_drift", "response lacks data_refreshed_at")
                return Pull(rows, refreshed)
            page = body.get("next_page")
            if not page:
                raise SourceError("schema_drift", "has_more without next_page")
        raise SourceError("schema_drift", f"more than {MAX_PAGES} pages")

    def fetch_usage(self, start: date, end: date) -> Pull:
        return self._pull("/v1/organizations/analytics/usage", USAGE_GROUP_BY, start, end, parse_usage_row)

    def fetch_cost(self, start: date, end: date) -> Pull:
        return self._pull("/v1/organizations/analytics/cost", COST_GROUP_BY, start, end, parse_cost_row)

    def fetch_rate_limits(self) -> list[RateLimitRow]:
        out: list[RateLimitRow] = []
        page: Optional[str] = None
        for _ in range(MAX_PAGES):
            body = self._get("/v1/organizations/rate_limits", [("page", page)] if page else [])
            try:
                for entry in body["data"]:
                    grp = entry["group"]
                    name = grp.get("display_name") or grp["type"]
                    for lim in entry["limits"]:
                        out.append(RateLimitRow("org", None, str(name), str(lim["type"]), int(lim["value"])))
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise SourceError("schema_drift", f"rate limit entry: {type(exc).__name__}") from exc
            page = body.get("next_page") if body.get("has_more") else None
            if not page:
                return out
        raise SourceError("schema_drift", f"more than {MAX_PAGES} pages")


def make_anthropic_client(api_key: Optional[str] = None, *, fake: Optional[FakeAnthropicClient] = None):
    """Factory: an explicit Fake wins (tests); otherwise Real with the admin key from settings."""
    if fake is not None:
        return fake
    if api_key is None:
        from app.config import settings

        api_key = settings.anthropic_admin_api_key
    return RealAnthropicClient(api_key or "")
