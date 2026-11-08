"""Anthropic usage/cost snapshot: replace-window sync into `ai_anthropic_*` (core migration 112).

* Every window is pulled COMPLETELY (all pages) before the store is touched; the store then deletes the
  window's days and inserts the pulled rows in ONE transaction (RPC `ai_replace_anthropic_*_window`). A bare
  upsert would keep rows a revision removed.
* Windows per run: the revision window (current month; also the previous month through day 7), then a
  backfill from 2026-01-01 in chunks <= 31 days, resuming from the last `ok` window (the job doubles as the
  gap catch-up: a run after downtime fills what is missing).
* Unavailable (no key / Individual Org) is recorded as status `unavailable`; platform admins are notified once,
  on the status change. Any real failure is recorded as `error` and RAISES, so `scheduler_runs` records
  `error` and the run ledger's `scheduler_job_failed` alert fires.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional, Protocol

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from .anthropic_client import (
    AnthropicAdminClient,
    CostRow,
    RateLimitRow,
    SourceError,
    SourceUnavailable,
    UsageRow,
)

logger = logging.getLogger(__name__)

COVERAGE_START = date(2026, 1, 1)
CHUNK_DAYS = 31
FINAL_AFTER_DAYS = 7
SOURCE = "anthropic"


def dims_key(*parts: Optional[str]) -> str:
    return hashlib.sha1("|".join(p or "" for p in parts).encode(), usedforsecurity=False).hexdigest()


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def is_final(day: date, data_refreshed_at: datetime) -> bool:
    """Final once the day's month end + 7 days is earlier than data_refreshed_at."""
    return month_end(day) + timedelta(days=FINAL_AFTER_DAYS) < data_refreshed_at.astimezone(timezone.utc).date()


def contiguous_coverage(windows: list[tuple[date, date]]) -> Optional[date]:
    """Last day covered contiguously from COVERAGE_START by the given ok windows (None = nothing)."""
    covered = COVERAGE_START - timedelta(days=1)
    for w_from, w_to in sorted(windows):
        if w_from <= covered + timedelta(days=1) and w_to > covered:
            covered = w_to
    return None if covered < COVERAGE_START else covered


def plan_windows(today: date, covered_to: Optional[date]) -> list[tuple[date, date]]:
    """Revision window(s) first, then the backfill chunks the store does not cover yet."""
    cur_start = today.replace(day=1)
    rev_start = (cur_start - timedelta(days=1)).replace(day=1) if today.day <= FINAL_AFTER_DAYS else cur_start
    windows = [(rev_start, today)]
    start = COVERAGE_START if covered_to is None else max(COVERAGE_START, covered_to + timedelta(days=1))
    while start < rev_start:
        end = min(start + timedelta(days=CHUNK_DAYS - 1), rev_start - timedelta(days=1))
        windows.append((start, end))
        start = end + timedelta(days=1)
    return windows


def usage_to_db(rows: list[UsageRow], refreshed: datetime, now: datetime) -> list[dict]:
    """Aggregate to the PK grain (the API may split a key across rows) and shape for the RPC."""
    acc: dict[tuple, dict] = {}
    for r in rows:
        k = (r.day, dims_key(r.model, r.workspace_id, r.api_key_id, r.service_tier, r.context_window))
        cur = acc.get(k)
        if cur is None:
            acc[k] = cur = {
                "day": r.day.isoformat(), "dims_key": k[1], "model": r.model or "", "workspace_id": r.workspace_id or "",
                "api_key_id": r.api_key_id or "", "service_tier": r.service_tier or "",
                "context_window": r.context_window or "", "uncached_input": 0, "cache_write_5m": 0,
                "cache_write_1h": 0, "cache_read": 0, "output_tokens": 0, "web_search_requests": None,
                "requests": None, "data_refreshed_at": refreshed.isoformat(),
                "is_final": is_final(r.day, refreshed), "synced_at": now.isoformat(),
            }
        for f in ("uncached_input", "cache_write_5m", "cache_write_1h", "cache_read", "output_tokens"):
            cur[f] += getattr(r, f)
        for f in ("web_search_requests", "requests"):
            v = getattr(r, f)
            if v is not None:
                cur[f] = (cur[f] or 0) + v
    return list(acc.values())


def cost_to_db(rows: list[CostRow], refreshed: datetime, now: datetime) -> list[dict]:
    acc: dict[tuple, dict] = {}
    for r in rows:
        k = (r.day, dims_key(r.model, r.workspace_id, r.api_key_id, r.cost_type, r.token_type))
        cur = acc.get(k)
        if cur is None:
            acc[k] = cur = {
                "day": r.day.isoformat(), "dims_key": k[1], "model": r.model or "", "workspace_id": r.workspace_id or "",
                "api_key_id": r.api_key_id or "", "cost_type": r.cost_type or "", "token_type": r.token_type or "",
                "amount_cents": "0", "list_amount_cents": None, "currency": "USD",
                "data_refreshed_at": refreshed.isoformat(), "is_final": is_final(r.day, refreshed),
                "synced_at": now.isoformat(),
            }
        cur["amount_cents"] = str(Decimal(cur["amount_cents"]) + r.amount_cents)
        if r.list_amount_cents is not None:
            prev = cur["list_amount_cents"]
            cur["list_amount_cents"] = str(
                (Decimal(prev) if prev is not None else 0) + r.list_amount_cents
            )
    return list(acc.values())


class SyncStore(Protocol):
    def replace_usage(self, start: date, end: date, rows: list[dict]) -> tuple[int, int]: ...
    def replace_cost(self, start: date, end: date, rows: list[dict]) -> tuple[int, int]: ...
    def replace_rate_limits(self, rows: list[dict]) -> tuple[int, int]: ...
    def record_run(self, run: dict) -> None: ...
    def ok_usage_windows(self) -> list[tuple[date, date]]: ...
    def last_run(self) -> Optional[dict]: ...


class SupabaseSyncStore:
    """Real store over the service-role client; the replace is one RPC = one transaction."""

    def __init__(self, db: Any):
        self.db = db

    def _rpc(self, name: str, params: dict) -> tuple[int, int]:
        data = self.db.rpc(name, params).execute().data
        if isinstance(data, list):
            data = data[0] if data else {}
        data = data or {}
        return int(data.get("deleted", 0)), int(data.get("written", 0))

    def replace_usage(self, start, end, rows):
        return self._rpc("ai_replace_anthropic_usage_window", {"p_from": start.isoformat(), "p_to": end.isoformat(), "p_rows": rows})

    def replace_cost(self, start, end, rows):
        return self._rpc("ai_replace_anthropic_cost_window", {"p_from": start.isoformat(), "p_to": end.isoformat(), "p_rows": rows})

    def replace_rate_limits(self, rows):
        return self._rpc("ai_replace_anthropic_rate_limits", {"p_rows": rows})

    def record_run(self, run: dict) -> None:
        self.db.table("ai_source_sync_runs").insert(run).execute()

    def ok_usage_windows(self) -> list[tuple[date, date]]:
        def page(start: int, end: int):
            return (
                self.db.table("ai_source_sync_runs").select("id,window_from,window_to")
                .eq("source", SOURCE).eq("endpoint", "usage").eq("status", "ok")
                .order("id").range(start, end).execute().data
            )

        return [
            (date.fromisoformat(r["window_from"]), date.fromisoformat(r["window_to"]))
            for r in iter_paged_rows(page, id_key="id", label="ai_source_sync_runs")
            if r.get("window_from") and r.get("window_to")
        ]

    def last_run(self) -> Optional[dict]:
        rows = (
            self.db.table("ai_source_sync_runs").select("status,reason_code")
            .eq("source", SOURCE).order("id", desc=True).limit(1).execute().data
        ) or []
        return rows[0] if rows else None


@dataclass
class InMemorySyncStore:
    """Fake store with the SAME replace semantics as the RPC (delete window days, insert pulled rows)."""

    usage: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    rate_limits: list = field(default_factory=list)
    runs: list = field(default_factory=list)

    def _replace(self, table: dict, start: date, end: date, rows: list[dict]) -> tuple[int, int]:
        doomed = [k for k in table if start <= date.fromisoformat(k[0]) <= end]
        for k in doomed:
            del table[k]
        for r in rows:
            table[(r["day"], r["dims_key"])] = r
        return len(doomed), len(rows)

    def replace_usage(self, start, end, rows):
        return self._replace(self.usage, start, end, rows)

    def replace_cost(self, start, end, rows):
        return self._replace(self.cost, start, end, rows)

    def replace_rate_limits(self, rows):
        deleted = len(self.rate_limits)
        self.rate_limits = list(rows)
        return deleted, len(rows)

    def record_run(self, run):
        self.runs.append(run)

    def ok_usage_windows(self):
        return [(date.fromisoformat(r["window_from"]), date.fromisoformat(r["window_to"]))
                for r in self.runs if r["endpoint"] == "usage" and r["status"] == "ok" and r.get("window_from")]

    def last_run(self):
        return self.runs[-1] if self.runs else None


def _run_row(endpoint: str, started: datetime, now: datetime, status: str, **kw: Any) -> dict:
    row = {
        "source": SOURCE, "endpoint": endpoint, "window_from": None, "window_to": None,
        "started_at": started.isoformat(), "finished_at": now.isoformat(), "status": status,
        "reason_code": None, "http_status": None, "rows_written": None, "rows_deleted": None,
        "data_refreshed_at": None,
    }
    row.update({k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in kw.items()})
    return row


def run_snapshot(
    client: AnthropicAdminClient,
    store: SyncStore,
    *,
    today: date,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    notify: Optional[Callable[[str, str, dict], Any]] = None,
) -> dict:
    """One sync run. Returns a summary; `unavailable` is a normal outcome (returned); a failure raises.

    `notify(title, message, metadata)` fires only when the source status CHANGES to unavailable.
    """
    previous = store.last_run()
    summary: dict = {"status": "ok", "windows": [], "rows_written": 0, "rows_deleted": 0}
    windows = plan_windows(today, contiguous_coverage(store.ok_usage_windows()))
    endpoint = "usage"
    window: Optional[tuple[date, date]] = None
    started = clock()
    try:
        for window in windows:
            start, end = window
            started = clock()
            endpoint = "usage"
            u = client.fetch_usage(start, end)
            endpoint = "cost"
            c = client.fetch_cost(start, end)
            now = clock()
            dw_u = store.replace_usage(start, end, usage_to_db(u.rows, u.data_refreshed_at, now))
            dw_c = store.replace_cost(start, end, cost_to_db(c.rows, c.data_refreshed_at, now))
            for ep, (deleted, written), refreshed in (("usage", dw_u, u.data_refreshed_at), ("cost", dw_c, c.data_refreshed_at)):
                store.record_run(_run_row(ep, started, clock(), "ok", window_from=start, window_to=end,
                                          rows_written=written, rows_deleted=deleted, data_refreshed_at=refreshed))
                summary["rows_written"] += written
                summary["rows_deleted"] += deleted
            summary["windows"].append([start.isoformat(), end.isoformat()])
        endpoint, window, started = "rate_limits", None, clock()
        limits = client.fetch_rate_limits()
        now = clock()
        rows = [{"scope": l.scope, "workspace_id_key": l.workspace_id or "", "model_group": l.model_group,
                 "metric": l.metric, "limit_value": l.limit, "synced_at": now.isoformat()} for l in limits]
        deleted, written = store.replace_rate_limits(rows)
        store.record_run(_run_row("rate_limits", started, clock(), "ok", rows_written=written, rows_deleted=deleted))
        return summary
    except SourceUnavailable as exc:
        store.record_run(_run_row(endpoint, started, clock(), "unavailable", reason_code=exc.reason_code,
                                  window_from=window[0] if window else None, window_to=window[1] if window else None))
        changed = not previous or previous.get("status") != "unavailable" or previous.get("reason_code") != exc.reason_code
        if changed and notify:
            notify(
                "Uso de IA (Anthropic): fonte indisponivel",
                f"A sincronizacao do uso/custo da Anthropic esta indisponivel ({exc.reason_code}).",
                {"reason_code": exc.reason_code},
            )
        logger.warning("anthropic usage snapshot unavailable: %s", exc.reason_code)
        return {**summary, "status": "unavailable", "reason_code": exc.reason_code}
    except SourceError as exc:
        store.record_run(_run_row(endpoint, started, clock(), "error", reason_code=exc.reason_code,
                                  http_status=exc.http_status,
                                  window_from=window[0] if window else None, window_to=window[1] if window else None))
        logger.error("anthropic usage snapshot failed (%s, window=%s): %s", endpoint, window, exc.reason_code)
        raise
    except Exception:
        store.record_run(_run_row(endpoint, started, clock(), "error"))
        logger.exception("anthropic usage snapshot failed (%s)", endpoint)
        raise
