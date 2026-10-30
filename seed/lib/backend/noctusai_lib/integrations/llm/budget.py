"""
Per-org LLM cost guardrails — ai-expansion Phase 18 (X4).

Wraps three concerns into one module:

  - **Storage**: monthly budget lives in `public.org_settings` (core's
    table — products have no `<schema>.org_settings`; the read is explicit
    `.schema("public")`, never the product-pinned client's own schema) under
    key `monthly_llm_budget_brl` (string-encoded decimal). When the row is
    absent the org has no budget configured (effectively unlimited). A
    MISSING TABLE (PGRST205) is not "no budget": it is a configuration error
    (`LLMBudgetNotConfigured`, logged at ERROR once per process).
  - **Spend**: read from the ONE central ledger `public.ai_usage` (roadmap
    D25, core migration 091) for the current month-to-date — every product's
    calls, no per-product schema map. Each row already carries `cost_brl`
    converted at write time from the latest BCB PTAX; a row without it
    (never expected) falls back to `cost_usd × LLM_USD_TO_BRL` (default 5.0).
  - **Enforcement**: `enforce_budget(org_id)` is called by
    `chat_completion` (and `chat_completion_stream`) before provider
    dispatch. Soft-warn threshold (default 80%) logs WARN; hard-stop
    threshold (default 100%) raises `LLMBudgetExceeded`.

Threshold tuning at runtime:

    LLM_BUDGET_SOFT_PCT = float env, default 0.8
    LLM_BUDGET_HARD_PCT = float env, default 1.0

The current implementation is fail-open: when the org has no budget set
OR the budget lookup fails (DB error / missing settings), the guard
returns silently and the LLM call proceeds. Document this in Sentry to
distinguish "no budget configured" from "guard is broken".

Read path: a Supabase admin client is used (service role) so RLS doesn't
block the cross-product aggregation. Callers pass it via `db_client_factory`.
The default factory is set by the seed app at startup (see
`configure_budget_module(...)`).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import anyio.to_thread

from noctusai_lib.integrations.persistence import iter_paged_rows

from .exceptions import LLMBudgetExceeded, LLMBudgetNotConfigured

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_SOFT_PCT = 0.80
_DEFAULT_HARD_PCT = 1.00
_DEFAULT_USD_TO_BRL = 5.0
_BUDGET_KEY = "monthly_llm_budget_brl"
_BUDGET_SCHEMA = "public"
#: Ensures the "storage is missing" ERROR is logged once per process.
_config_error_logged = False

#: The central ledger (`noctusai_lib.integrations.llm.ledger`).
_LEDGER_SCHEMA = "public"
_LEDGER_TABLE = "ai_usage"


# ---------------------------------------------------------------------------
# Module-level injection point
# ---------------------------------------------------------------------------

# Products inject their admin Supabase client here at startup so the budget
# module can read org_settings + the central public.ai_usage ledger without each call site
# threading the client through. None means "guard disabled".
_admin_client_factory: Optional[Callable[[], Any]] = None


def configure_budget_module(
    *, admin_client_factory: Optional[Callable[[], Any]]
) -> None:
    """Wire the admin client factory the budget module uses for reads.

    Called by `noctusai_seed.app.create_product_app(...)` once per process.
    Pass `None` to fully disable budget enforcement (e.g. in tests).
    """
    global _admin_client_factory
    _admin_client_factory = admin_client_factory


def is_configured() -> bool:
    return _admin_client_factory is not None


# ---------------------------------------------------------------------------
# Threshold helpers
# ---------------------------------------------------------------------------

def _soft_pct() -> float:
    raw = os.environ.get("LLM_BUDGET_SOFT_PCT")
    try:
        return float(raw) if raw else _DEFAULT_SOFT_PCT
    except ValueError:
        logger.warning("llm.budget: LLM_BUDGET_SOFT_PCT=%r is not a float; using default %s", raw, _DEFAULT_SOFT_PCT)
        return _DEFAULT_SOFT_PCT


def _hard_pct() -> float:
    raw = os.environ.get("LLM_BUDGET_HARD_PCT")
    try:
        return float(raw) if raw else _DEFAULT_HARD_PCT
    except ValueError:
        logger.warning("llm.budget: LLM_BUDGET_HARD_PCT=%r is not a float; using default %s", raw, _DEFAULT_HARD_PCT)
        return _DEFAULT_HARD_PCT


def _usd_to_brl() -> float:
    raw = os.environ.get("LLM_USD_TO_BRL")
    try:
        return float(raw) if raw else _DEFAULT_USD_TO_BRL
    except ValueError:
        logger.warning("llm.budget: LLM_USD_TO_BRL=%r is not a float; using default %s", raw, _DEFAULT_USD_TO_BRL)
        return _DEFAULT_USD_TO_BRL


def _reset_config_error_for_tests() -> None:
    global _config_error_logged
    _config_error_logged = False


def _month_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return start.isoformat(), now.isoformat()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _is_missing_table(exc: Exception) -> bool:
    """PostgREST PGRST205 — the relation does not exist / is not exposed."""
    text = str(exc)
    return "PGRST205" in text or "Could not find the table" in text


def _raise_not_configured(exc: Exception) -> None:
    global _config_error_logged
    if not _config_error_logged:
        _config_error_logged = True
        logger.error(
            "llm.budget: %s.org_settings is unreadable (%s) — the budget guard "
            "is misconfigured; every LLM call will fail until the table is "
            "reachable.",
            _BUDGET_SCHEMA,
            exc,
        )
    raise LLMBudgetNotConfigured(str(exc)) from exc


async def fetch_budget_brl(org_id: str) -> Optional[float]:
    """Return the org's monthly budget in BRL, or `None` when unset."""
    if not _admin_client_factory or not org_id:
        return None
    try:
        db = _admin_client_factory()
        # Off the event loop. The cross-schema `.schema()` call stays inside ONE thunk so the
        # re-pin and the query happen back to back on the same worker.
        def _read():
            return (
                db.schema(_BUDGET_SCHEMA)
                .table("org_settings")
                .select("value")
                .eq("org_id", org_id)
                .eq("key", _BUDGET_KEY)
                .limit(1)
                .execute()
            )

        result = await anyio.to_thread.run_sync(_read)
    except Exception as exc:
        if _is_missing_table(exc):
            _raise_not_configured(exc)
        logger.warning(
            "llm.budget.fetch_budget_brl: org_settings read failed for org=%s: %s",
            org_id,
            exc,
        )
        return None
    rows = result.data or []
    if not rows:
        return None
    raw = rows[0].get("value")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError) as exc:
        logger.warning(
            "llm.budget.fetch_budget_brl: malformed value %r for org=%s (%s)",
            raw,
            org_id,
            exc,
        )
        return None


async def _ledger_spend(
    org_id: str, *, start_iso: Optional[str] = None, end_iso: Optional[str] = None
) -> tuple[float, float]:
    """``(spent_usd, spent_brl)`` of `org_id` in the window, from
    ``public.ai_usage`` (paged — PostgREST caps every response at 1 000 rows,
    KB § PATTERNS/backend/postgrest-row-cap.md). Raises on a read failure —
    `enforce_budget` owns the fail-open posture."""
    if not _admin_client_factory or not org_id:
        return 0.0, 0.0
    if not start_iso or not end_iso:
        start_iso, end_iso = _month_window()
    db = _admin_client_factory()
    rate = _usd_to_brl()

    def _sum() -> tuple[float, float]:
        usd = brl = 0.0

        # The cross-schema `.schema()` call stays inside the per-page thunk so the re-pin
        # and the query run back to back on the same worker.
        def fetch_page(start: int, end: int) -> Any:
            return (
                db.schema(_LEDGER_SCHEMA)
                .table(_LEDGER_TABLE)
                .select("id,cost_usd,cost_brl")
                .eq("org_id", org_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        for row in iter_paged_rows(fetch_page, label=f"llm spend {org_id}"):
            row_usd = float(row.get("cost_usd") or 0)
            usd += row_usd
            row_brl = row.get("cost_brl")
            brl += float(row_brl) if row_brl is not None else row_usd * rate
        return usd, brl

    return await anyio.to_thread.run_sync(_sum)


async def compute_spend_usd(
    org_id: str, *, start_iso: Optional[str] = None, end_iso: Optional[str] = None
) -> float:
    """Sum ``cost_usd`` of the org's ``public.ai_usage`` rows in the window
    (all products). Returns 0.0 and logs when the ledger is unreadable."""
    try:
        usd, _brl = await _ledger_spend(org_id, start_iso=start_iso, end_iso=end_iso)
    except Exception as exc:
        logger.warning("llm.budget.compute_spend_usd: ai_usage read failed for org=%s: %s", org_id, exc)
        return 0.0
    return usd


async def compute_status(org_id: str) -> dict[str, Any]:
    """Return `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}`.

    `status` is `'unset' | 'ok' | 'warn' | 'hard_stop'`. Always returns a
    dict; raises only `LLMBudgetNotConfigured` (missing budget storage).
    """
    soft = _soft_pct()
    hard = _hard_pct()

    budget_brl = await fetch_budget_brl(org_id)
    if budget_brl is None or budget_brl <= 0:
        return {
            "spent_brl": 0.0,
            "budget_brl": 0.0,
            "used_pct": 0.0,
            "status": "unset",
            "soft_pct": soft,
            "hard_pct": hard,
        }

    try:
        _spent_usd, spent_brl = await _ledger_spend(org_id)
    except Exception as exc:
        logger.warning("llm.budget.compute_status: ai_usage read failed for org=%s: %s", org_id, exc)
        spent_brl = 0.0
    used_pct = (spent_brl / budget_brl) if budget_brl else 0.0

    if used_pct >= hard:
        status = "hard_stop"
    elif used_pct >= soft:
        status = "warn"
    else:
        status = "ok"

    return {
        "spent_brl": round(spent_brl, 2),
        "budget_brl": round(budget_brl, 2),
        "used_pct": round(used_pct, 4),
        "status": status,
        "soft_pct": soft,
        "hard_pct": hard,
    }


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


async def enforce_budget(org_id: Optional[str]) -> None:
    """Raise `LLMBudgetExceeded` if the org's hard threshold is crossed.
    Logs WARN at the soft threshold. Returns silently otherwise.

    Fail-open posture: if `org_id` is None, the module isn't configured,
    or a transient read fails, this returns silently (a MISSING budget table
    is a configuration error and raises `LLMBudgetNotConfigured` instead) (LLM call proceeds). The
    rationale is that a flaky budget check should not break user-facing
    AI features — it's a guardrail, not a hard gate.
    """
    if not org_id or not _admin_client_factory:
        return
    try:
        status = await compute_status(org_id)
    except LLMBudgetNotConfigured:
        raise
    except Exception as exc:
        logger.warning(
            "llm.budget.enforce_budget: status read failed for org=%s: %s",
            org_id,
            exc,
        )
        return

    if status["status"] == "hard_stop":
        raise LLMBudgetExceeded(
            org_id=org_id,
            spent_brl=status["spent_brl"],
            budget_brl=status["budget_brl"],
        )
    if status["status"] == "warn":
        logger.warning(
            "llm.budget.warn: org=%s spent_brl=%.2f budget_brl=%.2f used_pct=%.2f",
            org_id,
            status["spent_brl"],
            status["budget_brl"],
            status["used_pct"],
        )


# Type alias for the chat module's import.
EnforceBudgetFn = Callable[[Optional[str]], Awaitable[None]]
