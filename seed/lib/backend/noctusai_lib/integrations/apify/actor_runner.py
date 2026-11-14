"""Generic Apify actor runner: `run_actor(actor_id, input, timeout, max_items)` -> dataset items + usage.

Sibling of the Instagram scraper (which stays untouched). Flow: start the run
(`POST /acts/{id}/runs`), poll the run object until terminal, read the dataset
items. The run object is what exposes compute units + USD, so callers can record
cost per run (measurement-by-design). The token travels ONLY in the
Authorization header; every call goes through the `apify` rate bucket.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable
from urllib.parse import quote

import httpx

from noctusai_lib.integrations import rate_limit

from .types import ApifyError, ApifyNotConfigured, ApifyRateLimited, ApifyRunFailed

logger = logging.getLogger(__name__)

API_BASE = "https://api.apify.com/v2"
BUCKET = "apify"
MAX_ITEMS_HARD_CAP = 10_000
_TERMINAL_OK = "SUCCEEDED"
_TERMINAL = {_TERMINAL_OK, "FAILED", "ABORTED", "TIMED-OUT"}
_POLL_WAIT_S = 30


class ApifyActorTimeout(ApifyRunFailed):
    """The run did not reach a terminal state within `timeout_s` (it is aborted best-effort)."""


@dataclass(frozen=True)
class ActorRunUsage:
    """Cost of one run. `None` = the platform did not report it; never invented."""

    run_id: Optional[str] = None
    compute_units: Optional[Decimal] = None
    usd: Optional[Decimal] = None
    results: int = 0


@dataclass(frozen=True)
class ActorRunResult:
    items: list[dict] = field(default_factory=list)
    usage: ActorRunUsage = field(default_factory=ActorRunUsage)
    actor_id: str = ""
    status: str = _TERMINAL_OK


@runtime_checkable
class ActorRunner(Protocol):
    def run_actor(
        self, actor_id: str, input: Optional[Mapping[str, Any]] = None, *,
        timeout_s: float = 240, max_items: int = 100,
    ) -> ActorRunResult: ...


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _actor_path(actor_id: str) -> str:
    """`user/name` -> `user~name` (the REST form); ids and bare names pass through."""
    actor_id = (actor_id or "").strip()
    if not actor_id or any(c in actor_id for c in " ?#\\") or actor_id.count("/") > 1:
        raise ValueError(f"invalid apify actor id: {actor_id!r}")
    return quote(actor_id.replace("/", "~"), safe="~")


class RealActorRunner:
    def __init__(
        self, *, token: str, transport: Optional[httpx.BaseTransport] = None,
        sleep: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
    ) -> None:
        if not token:
            raise ApifyNotConfigured("apify token not configured")
        self._token = token
        self._transport = transport
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic

    # -- http -------------------------------------------------------------
    def _request(self, method: str, url: str, *, params: Optional[dict] = None,
                 json: Any = None, timeout_s: float = 60) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}"}

        def _once() -> httpx.Response:
            try:
                with httpx.Client(timeout=timeout_s, transport=self._transport) as client:
                    resp = client.request(method, url, params=params, json=json, headers=headers)
            except httpx.TimeoutException:
                raise ApifyRunFailed("apify request timed out") from None
            except httpx.HTTPError as exc:
                raise ApifyRunFailed(f"apify transport error ({type(exc).__name__})") from None
            if resp.status_code == 429:
                raise ApifyRateLimited(
                    "apify rate limited",
                    retry_after_s=rate_limit.parse_retry_after(resp.headers.get("retry-after")),
                )
            if resp.status_code not in (200, 201):
                raise ApifyRunFailed(f"apify returned HTTP {resp.status_code}")
            return resp

        return rate_limit.paced_call(
            _once, bucket=BUCKET,
            is_retryable=lambda e: isinstance(e, ApifyRateLimited),
            retry_after=lambda e: getattr(e, "retry_after_s", None),
        )

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            raise ApifyRunFailed("apify returned a non-JSON body") from None

    @staticmethod
    def _run_obj(body: Any) -> dict:
        run = body.get("data") if isinstance(body, dict) else None
        if not isinstance(run, dict):
            raise ApifyRunFailed("apify returned an unexpected run shape")
        return run

    # -- port -------------------------------------------------------------
    def run_actor(
        self, actor_id: str, input: Optional[Mapping[str, Any]] = None, *,
        timeout_s: float = 240, max_items: int = 100,
    ) -> ActorRunResult:
        cap = max(1, min(int(max_items), MAX_ITEMS_HARD_CAP))
        path = _actor_path(actor_id)
        deadline = self._monotonic() + timeout_s
        run = self._run_obj(self._json(self._request(
            "POST", f"{API_BASE}/acts/{path}/runs",
            params={"timeout": int(timeout_s), "maxItems": cap}, json=dict(input or {}),
        )))
        if not run.get("id"):
            raise ApifyRunFailed("apify returned an unexpected run shape")
        run_id = str(run["id"])
        while run.get("status") not in _TERMINAL:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                self._abort(run_id)
                raise ApifyActorTimeout(f"apify actor run {run_id} exceeded {timeout_s:.0f}s")
            run = self._run_obj(self._json(self._request(
                "GET", f"{API_BASE}/actor-runs/{run_id}",
                params={"waitForFinish": int(min(_POLL_WAIT_S, max(1, remaining)))},
            )))
        status = str(run.get("status"))
        if status != _TERMINAL_OK:
            raise ApifyRunFailed(f"apify actor run {run_id} ended {status}")
        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            raise ApifyRunFailed("apify run has no dataset")
        raw = self._json(self._request(
            "GET", f"{API_BASE}/datasets/{quote(str(dataset_id), safe='')}/items",
            params={"format": "json", "clean": "true", "limit": cap},
        ))
        if not isinstance(raw, list):
            raise ApifyRunFailed("apify returned an unexpected dataset shape")
        items = [i for i in raw if isinstance(i, dict)]
        if len(items) != len(raw):
            logger.warning("apify dataset for run %s had %d non-object items (dropped)", run_id, len(raw) - len(items))
        usage_map = run.get("usage") if isinstance(run.get("usage"), dict) else {}
        usage = ActorRunUsage(
            run_id=run_id,
            compute_units=_dec(run["usageCompute"] if run.get("usageCompute") is not None
                               else usage_map.get("ACTOR_COMPUTE_UNITS")),
            usd=_dec(run.get("usageTotalUsd")),
            results=len(items),
        )
        return ActorRunResult(items=items, usage=usage, actor_id=actor_id, status=status)

    def _abort(self, run_id: str) -> None:
        try:
            self._request("POST", f"{API_BASE}/actor-runs/{run_id}/abort", timeout_s=15)
        except ApifyError as exc:  # best effort; the timeout error is what the caller sees
            logger.warning("apify abort of run %s failed: %s", run_id, exc)


class FakeActorRunner:
    """Deterministic runner: items per actor id, recorded calls, optional scripted error."""

    def __init__(
        self, items_by_actor: Optional[Mapping[str, list[dict]]] = None, *,
        compute_units: Decimal = Decimal("0.01"), usd: Optional[Decimal] = Decimal("0.004"),
        raises: Optional[ApifyError] = None,
    ) -> None:
        self._items = {k: list(v) for k, v in (items_by_actor or {}).items()}
        self._cu, self._usd, self._raises = compute_units, usd, raises
        self.calls: list[dict] = []

    def run_actor(
        self, actor_id: str, input: Optional[Mapping[str, Any]] = None, *,
        timeout_s: float = 240, max_items: int = 100,
    ) -> ActorRunResult:
        _actor_path(actor_id)  # same id validation as Real
        self.calls.append({"actor_id": actor_id, "input": dict(input or {}),
                           "timeout_s": timeout_s, "max_items": max_items})
        if self._raises is not None:
            raise self._raises
        if actor_id not in self._items:
            raise ApifyRunFailed(f"fake actor {actor_id!r} has no scripted items")
        cap = max(1, min(int(max_items), MAX_ITEMS_HARD_CAP))
        items = [dict(i) for i in self._items[actor_id][:cap]]
        usage = ActorRunUsage(run_id=f"fake-run-{len(self.calls)}", compute_units=self._cu,
                              usd=self._usd, results=len(items))
        return ActorRunResult(items=items, usage=usage, actor_id=actor_id)
