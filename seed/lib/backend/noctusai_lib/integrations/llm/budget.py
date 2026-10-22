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
  - **Spend**: aggregated across every product's `<schema>.llm_usage`
    table for the current month-to-date. USD cost is converted to BRL via
    `LLM_USD_TO_BRL` env var (default 5.0; admins update when FX moves
    beyond their tolerance).
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

# Map product slug → schema (mirrors core/admin_llm_usage.py). Extend when a
# new product gets `<schema>.llm_usage`.
_PRODUCT_SCHEMAS: dict[str, str] = {
    "erp-imobiliario": "erp",
    "therapy-platform": "therapy",
    "social-wiring": "social_wiring",
}


# ---------------------------------------------------------------------------
# Module-level injection point
# ---------------------------------------------------------------------------

# Products inject their admin Supabase client here at startup so the budget
# module can read org_settings + per-product llm_usage without each call site
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


async def compute_spend_usd(
    org_id: str, *, start_iso: Optional[str] = None, end_iso: Optional[str] = None
) -> float:
    """Sum `cost_estimate_usd` across every product's `llm_usage` table for
    the given org and time window."""
    if not _admin_client_factory or not org_id:
        return 0.0
    if not start_iso or not end_iso:
        start_iso, end_iso = _month_window()
    db = _admin_client_factory()

    # Sequential on purpose, but in ONE worker thread (not parked on the loop): `.schema(x)`
    # mutates the shared client, so running the per-schema reads concurrently would race.
    def _sum() -> float:
        total = 0.0
        for product, schema in _PRODUCT_SCHEMAS.items():
            try:
                # Paged: PostgREST caps every response at 1 000 rows, so the old `.limit(50_000)`
                # silently under-counted a busy month (KB § PATTERNS/backend/postgrest-row-cap.md).
                def fetch_page(start: int, end: int, _schema: str = schema) -> Any:
                    return (
                        db.schema(_schema)
                        .table("llm_usage")
                        .select("id,cost_estimate_usd")
                        .eq("org_id", org_id)
                        .gte("at", start_iso)
                        .lte("at", end_iso)
                        .order("id")
                        .range(start, end)
                        .execute()
                        .data
                    )

                for row in iter_paged_rows(fetch_page, label=f"llm spend {product}/{org_id}"):
                    total += float(row.get("cost_estimate_usd") or 0)
            except Exception as exc:
                logger.warning(
                    "llm.budget.compute_spend_usd: %s/%s read failed for org=%s: %s",
                    product, schema, org_id, exc,
                )
                continue
        return total

    return await anyio.to_thread.run_sync(_sum)


async def compute_status(org_id: str) -> dict[str, Any]:
    """Return `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}`.

    `status` is `'unset' | 'ok' | 'warn' | 'hard_stop'`. Always returns a
    dict; raises only `LLMBudgetNotConfigured` (missing budget storage).
    """
    soft = _soft_pct()
    hard = _hard_pct()
    rate = _usd_to_brl()

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

    spent_usd = await compute_spend_usd(org_id)
    spent_brl = spent_usd * rate
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
