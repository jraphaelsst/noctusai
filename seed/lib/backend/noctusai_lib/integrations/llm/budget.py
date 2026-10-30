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

The monthly-budget part is fail-open: when the org has no budget set
OR the budget lookup fails (DB error / missing settings), the guard
returns silently and the LLM call proceeds. Document this in Sentry to
distinguish "no budget configured" from "guard is broken".

**Prepaid credits (core migration 093) are fail-CLOSED** — `enforce_credits`
runs first inside `enforce_budget`:

  - reads ``public.credit_wallets`` for the org through a short TTL cache
    (``LLM_CREDITS_CACHE_TTL_S``, default 15 s);
  - no wallet ⇒ today's behaviour; ``byok`` / ``postpaid_trusted`` ⇒ never
    refused; ``prepaid`` with ``balance <= -overdraft_limit`` ⇒
    `LLMCreditsExhausted` (HTTP 402) BEFORE the provider call;
  - the wallet read FAILS ⇒ refuse with `LLMCreditsUnverifiable` (503) unless
    this process last saw the org as something other than prepaid (no wallet /
    byok / trusted) — an unknown or prepaid org is never served on an unknown
    balance. Every such refusal is marked: ERROR log + (rate-limited) an
    in-app notification row for the platform admins;
  - the TABLE is missing (PGRST205, migration not applied) ⇒ no wallet can
    exist, so no org is prepaid: today's behaviour, logged at ERROR once.

The balance lags the usage by at most the debit job's cadence (core,
every minute) plus this cache TTL — the documented overdraft exposure.

Read path: a Supabase admin client is used (service role) so RLS doesn't
block the cross-product aggregation. Callers pass it via `db_client_factory`.
The default factory is set by the seed app at startup (see
`configure_budget_module(...)`).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import anyio.to_thread

from noctusai_lib.integrations.persistence import iter_paged_rows

from .exceptions import (
    LLMBudgetExceeded,
    LLMBudgetNotConfigured,
    LLMCreditsExhausted,
    LLMCreditsUnverifiable,
)

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
    # A new client means a new source of truth: drop what the old one told us.
    with _credit_lock:
        _credit_cache.clear()
        _credit_last_mode.clear()


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
# Prepaid credits (core migration 093) — fail-CLOSED
# ---------------------------------------------------------------------------

_CREDIT_TABLE = "credit_wallets"
_CREDIT_SCHEMA = "public"
_DEFAULT_CREDIT_TTL_S = 15.0
_CREDIT_MARK_EVERY_S = 600.0
#: Sentinel: this process never read the org's wallet successfully.
_UNKNOWN = "__unknown__"

_credit_lock = threading.Lock()
#: org_id -> (expires_at_monotonic, wallet row | None)
_credit_cache: dict[str, tuple[float, Optional[dict]]] = {}
#: org_id -> last successfully read mode (None = no wallet). Never expires.
_credit_last_mode: dict[str, Optional[str]] = {}
#: org_id -> monotonic time of the last "unverifiable" platform-admin mark.
_credit_marked_at: dict[str, float] = {}
_credit_table_missing_logged = False
_clock: Callable[[], float] = time.monotonic


def _credit_ttl() -> float:
    raw = os.environ.get("LLM_CREDITS_CACHE_TTL_S")
    try:
        return float(raw) if raw else _DEFAULT_CREDIT_TTL_S
    except ValueError:
        logger.warning("llm.credits: LLM_CREDITS_CACHE_TTL_S=%r is not a float; using %s", raw, _DEFAULT_CREDIT_TTL_S)
        return _DEFAULT_CREDIT_TTL_S


def _reset_credit_state_for_tests(clock: Optional[Callable[[], float]] = None) -> None:
    global _credit_table_missing_logged, _clock
    with _credit_lock:
        _credit_cache.clear()
        _credit_last_mode.clear()
        _credit_marked_at.clear()
    _credit_table_missing_logged = False
    _clock = clock or time.monotonic


async def _read_wallet(org_id: str) -> Optional[dict]:
    """The org's wallet row, or None (no wallet / table not deployed). Raises on any
    other read failure — `enforce_credits` owns the fail-closed posture."""
    global _credit_table_missing_logged
    assert _admin_client_factory is not None
    db = _admin_client_factory()

    def _read():
        return (
            db.schema(_CREDIT_SCHEMA)
            .table(_CREDIT_TABLE)
            .select("mode,balance_credits,overdraft_limit_credits")
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )

    try:
        result = await anyio.to_thread.run_sync(_read)
    except Exception as exc:
        if _is_missing_table(exc):
            if not _credit_table_missing_logged:
                _credit_table_missing_logged = True
                logger.error(
                    "llm.credits: %s.%s is not deployed (%s) — no org can hold a prepaid wallet; "
                    "credit enforcement is inactive until core migration 093 is applied.",
                    _CREDIT_SCHEMA, _CREDIT_TABLE, exc,
                )
            return None
        raise
    rows = result.data or []
    return rows[0] if rows else None


def _mark_unverifiable(org_id: str, exc: Exception) -> None:
    """ERROR log every time; at most every 10 min per org, a bell notification for the
    platform admins (best effort — the database just failed us; a failed mark is logged)."""
    logger.error("llm.credits.unverifiable: org=%s wallet read failed — AI call refused: %s", org_id, exc)
    now = _clock()
    with _credit_lock:
        last = _credit_marked_at.get(org_id)
        if last is not None and now - last < _CREDIT_MARK_EVERY_S:
            return
        _credit_marked_at[org_id] = now
    try:
        db = _admin_client_factory() if _admin_client_factory else None
        if db is None:
            return
        core = db.schema(_CREDIT_SCHEMA)
        admins = core.table("noctus_users").select("id").eq("role", "admin").execute().data or []
        rows = [
            {
                "user_id": str(a["id"]),
                "type": "system",
                "title": "Créditos de IA: saldo não verificável",
                "message": f"A leitura da carteira da org {org_id} falhou; chamadas de IA dela foram recusadas.",
                "metadata": {"tipo": "creditos_guarda_indisponivel", "org_id": org_id, "erro": str(exc)[:300]},
            }
            for a in admins
            if a.get("id")
        ]
        if rows:
            core.table("notifications").insert(rows).execute()
    except Exception as mark_exc:  # noqa: BLE001 — the refusal already happened; the mark is best-effort, logged
        logger.error("llm.credits: could not record the unverifiable mark for org=%s: %s", org_id, mark_exc)


async def enforce_credits(org_id: Optional[str]) -> None:
    """Refuse a PREPAID org at/below its overdraft floor (HTTP 402) — fail-closed.

    No-op when `org_id` is None or the module is not configured (tests / CLI)."""
    if not org_id or not _admin_client_factory:
        return
    now = _clock()
    with _credit_lock:
        cached = _credit_cache.get(org_id)
    if cached is not None and cached[0] > now:
        wallet = cached[1]
    else:
        try:
            wallet = await _read_wallet(org_id)
        except Exception as exc:
            with _credit_lock:
                last_mode = _credit_last_mode.get(org_id, _UNKNOWN)
            if last_mode in (_UNKNOWN, "prepaid"):
                await anyio.to_thread.run_sync(_mark_unverifiable, org_id, exc)
                raise LLMCreditsUnverifiable(org_id, str(exc)) from exc
            logger.warning(
                "llm.credits: wallet read failed for org=%s (last seen mode=%s, not prepaid) — proceeding: %s",
                org_id, last_mode, exc,
            )
            return
        with _credit_lock:
            _credit_cache[org_id] = (now + _credit_ttl(), wallet)
            _credit_last_mode[org_id] = wallet.get("mode") if wallet else None
    if not wallet or wallet.get("mode") != "prepaid":
        return
    balance = float(wallet.get("balance_credits") or 0)
    overdraft = float(wallet.get("overdraft_limit_credits") or 0)
    if balance <= -overdraft:
        raise LLMCreditsExhausted(org_id, balance, overdraft)


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
    # Prepaid credits first — fail-CLOSED (raises LLMCreditsExhausted / LLMCreditsUnverifiable).
    await enforce_credits(org_id)
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
