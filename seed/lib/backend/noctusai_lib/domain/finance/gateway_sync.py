"""Gateway sync: pull the gateway's account statement into its `kind='gateway'` account.

`ChargeOperations.list_balance_transactions` is the gateway's own statement. Per line:

* **charge / refund** -- the commerce bridge (`booking.book_settlement`, keyed on
  `external_ref`) is the one that books them against an entry. A line whose settlement is
  already there is COUNTED, never touched; one that is not is returned for REVIEW. Booking a
  charge here would invent an entry-less payment and double-book it the moment the bridge
  catches up.
* **fee** -- booked as an `adjustment` OUT ledger row, but only when it cannot also be in the
  charge's own settlement (`fee_cents`): a fee for a charge that is settled with
  `fee_cents > 0` is already booked; one for a charge not yet settled waits (review).
* **transfer** (payout to the bank) -- one `transfer` ledger leg on the gateway account; the
  bank's own leg arrives with the bank statement.
* **chargeback / adjustment / other** -- review (money moved that no entry explains).

Idempotency without a new column: every ledger row this module books gets a DETERMINISTIC
id (`uuid5(org, account, gateway-line-id, kind)`), so re-pulling an overlapping window finds
its own rows and skips them.

Cursor (`fin_gateway_sync.cursor`, TEXT): JSON `{"since": "YYYY-MM-DD", "page": <gateway cursor>|null}`.
`page` is persisted after every page, so a failure mid-run resumes where it stopped;
when a run completes, `since` moves to the newest line seen minus one day (an overlap, so a
late-arriving line is not missed -- the overlap is harmless because of the idempotency above).
Failures land in `last_error` as a GENERIC code (never the provider's body -- contract §0).

NOC-REMEDIATE[finance-gateway-review-queue]: the "review" list is returned by each sync and
is not persisted -- a line that falls out of the overlap window before someone looks at it is
not listed again. Destination: a `fin_gateway_review` table + endpoint when the first host
has a UI for it (commerce P4 slice F). -- 2026-10-14
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Callable, Optional, Union
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.payments.charges import ChargeOperations
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import BalanceTransaction
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from ._common import Scope, first, now_iso, to_date, today
from .accounts import get_account
from .config import FinanceConfig
from .errors import FinanceError, invalid
from .types import AccountKind, LedgerDirection, LedgerOrigin, SettlementKind

logger = logging.getLogger(__name__)

SYNC_NAMESPACE = uuid.UUID("5f6a1f0e-7c0b-4b6e-9a53-3a1f6d2c4e11")
MAX_PAGES_PER_RUN = 50
MAX_REVIEW_ROWS = 500
DEFAULT_LOOKBACK_DAYS = 30
OVERLAP_DAYS = 1
BR_TZ = ZoneInfo("America/Sao_Paulo")

CONTA_NAO_GATEWAY = "conta_nao_gateway"
SINCRONIZACAO_FALHOU = "sincronizacao_falhou"

#: a `ChargeOperations`, or `gateway_name -> ChargeOperations` (a host with several gateways)
OperationsSource = Union[ChargeOperations, Callable[[str], ChargeOperations]]


def resolve_operations(source: OperationsSource, gateway: str) -> ChargeOperations:
    if hasattr(source, "list_balance_transactions"):
        return source  # type: ignore[return-value]
    if callable(source):
        return source(gateway)
    raise TypeError("get_charge_operations must yield a ChargeOperations or a callable gateway -> ChargeOperations")


# ─── cursor state ────────────────────────────────────────────────────────────


def _read_state(s: Scope, account_id: str) -> dict:
    row = first(s.tbl("gateway_sync").select("*").eq("org_id", s.org_id).eq("account_id", account_id).limit(1).execute())
    return row or {}


def _decode_cursor(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


_KEEP: Any = object()  # "leave the stored cursor alone" (None means "clear it")


def _save_state(s: Scope, account_id: str, *, cursor: Any = _KEEP, synced: bool = False, error: Optional[str] = None) -> None:
    patch: dict[str, Any] = {"last_error": error}
    if cursor is not _KEEP:
        patch["cursor"] = json.dumps(cursor) if cursor is not None else None
    if synced:
        patch["last_synced_at"] = now_iso()
    exists = s.tbl("gateway_sync").select("account_id").eq("org_id", s.org_id).eq("account_id", account_id).limit(1).execute()
    if exists.data:
        s.tbl("gateway_sync").update(patch).eq("org_id", s.org_id).eq("account_id", account_id).execute()
    else:
        s.tbl("gateway_sync").insert({"account_id": account_id, "org_id": s.org_id, **patch}).execute()


def generic_error(exc: BaseException) -> str:
    """A storable description of a failure that can never carry a provider's body or a secret."""
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    bits = [type(exc).__name__]
    if code:
        bits.append(f"code={str(code)[:60]}")
    if status:
        bits.append(f"status={status}")
    return " ".join(bits)


# ─── per-line handling ───────────────────────────────────────────────────────


def _local_day(bt: BalanceTransaction) -> date:
    at = bt.occurred_at
    if at.tzinfo is not None:
        at = at.astimezone(BR_TZ)
    return at.date()


def _det_id(org_id: str, account_id: str, bt: BalanceTransaction, tag: str) -> str:
    return str(uuid.uuid5(SYNC_NAMESPACE, f"{org_id}:{account_id}:{bt.id_at_gateway}:{tag}"))


def _settlement_for(s: Scope, kind: str, *refs: Optional[str]) -> Optional[dict]:
    for ref in refs:
        if ref:
            row = first(
                s.tbl("settlements").select("*").eq("org_id", s.org_id).eq("kind", kind).eq("external_ref", ref).limit(1).execute()
            )
            if row:
                return row
    return None


def _book_ledger(s: Scope, account_id: str, bt: BalanceTransaction, *, origin: str, tag: str, description: str, **extra: Any) -> bool:
    """Insert the deterministic ledger row for `bt`; False when it was already there."""
    row_id = _det_id(s.org_id, account_id, bt, tag)
    if s.tbl("ledger").select("id").eq("org_id", s.org_id).eq("id", row_id).limit(1).execute().data:
        return False
    cents = bt.amount.amount_cents
    s.tbl("ledger").insert(
        {
            "id": row_id,
            "org_id": s.org_id,
            "account_id": account_id,
            "occurred_on": _local_day(bt).isoformat(),
            "direction": LedgerDirection.IN.value if cents > 0 else LedgerDirection.OUT.value,
            "amount_cents": abs(cents),
            "origin": origin,
            "description": description[:200],
            "created_at": now_iso(),
            **extra,
        }
    ).execute()
    return True


def _review(bt: BalanceTransaction, reason: str) -> dict:
    return {
        "id": bt.id_at_gateway,
        "kind": bt.kind,
        "occurred_on": _local_day(bt).isoformat(),
        "amount_cents": bt.amount.amount_cents,
        "charge_id": bt.charge_id_at_gateway,
        "description": (bt.description or "")[:200],
        "reason": reason,
    }


def handle_line(s: Scope, account_id: str, bt: BalanceTransaction, tally: dict) -> None:
    """Classify one gateway line: already booked / book it / put it up for review."""
    if bt.amount.currency != "BRL":
        tally["review"].append(_review(bt, "moeda_nao_suportada"))
        return
    if bt.amount.amount_cents == 0:
        return
    charge = bt.charge_id_at_gateway
    if bt.kind == "charge":
        if _settlement_for(s, SettlementKind.PAYMENT.value, charge, bt.id_at_gateway):
            tally["already_booked"] += 1
        else:
            tally["review"].append(_review(bt, "sem_baixa_no_comercio"))
    elif bt.kind == "refund":
        if _settlement_for(s, SettlementKind.REFUND.value, bt.id_at_gateway, charge):
            tally["already_booked"] += 1
        else:
            tally["review"].append(_review(bt, "estorno_sem_baixa"))
    elif bt.kind == "fee":
        paid = _settlement_for(s, SettlementKind.PAYMENT.value, charge) if charge else None
        if charge and paid is None:
            tally["review"].append(_review(bt, "tarifa_aguardando_baixa"))
        elif paid is not None and int(paid.get("fee_cents") or 0) > 0:
            tally["already_booked"] += 1  # the settlement's own fee ledger row is the books' record of it
        elif _book_ledger(s, account_id, bt, origin=LedgerOrigin.ADJUSTMENT.value, tag="fee",
                          description=f"Tarifa do gateway: {bt.description or bt.id_at_gateway}"):
            tally["booked_fees"] += 1
        else:
            tally["already_booked"] += 1
    elif bt.kind == "transfer":
        group = _det_id(s.org_id, account_id, bt, "transfer-group")
        if _book_ledger(s, account_id, bt, origin=LedgerOrigin.TRANSFER.value, tag="transfer",
                        description=f"Repasse do gateway: {bt.description or bt.id_at_gateway}", transfer_group=group):
            tally["booked_transfers"] += 1
        else:
            tally["already_booked"] += 1
    else:  # chargeback / adjustment / other: money moved that no entry explains
        tally["review"].append(_review(bt, f"{bt.kind}_para_revisao"))


# ─── the sync ────────────────────────────────────────────────────────────────


def _blank(account_id: str) -> dict:
    return {"account_id": account_id, "status": "ok", "pages": 0, "fetched": 0, "booked_fees": 0,
            "booked_transfers": 0, "already_booked": 0, "review": [], "review_total": 0, "error": None}


def sync_gateway_account(
    s: Scope,
    operations: OperationsSource,
    account_id: Any,
    *,
    since: Optional[date] = None,
    max_pages: int = MAX_PAGES_PER_RUN,
) -> dict:
    """Pull one gateway account's statement. Never raises for a gateway/line failure: it records
    `last_error`, keeps the cursor where it stopped and returns `status: "error"`."""
    account = get_account(s, account_id)
    if account["kind"] != AccountKind.GATEWAY.value or not account.get("gateway"):
        raise invalid("account_id", "A conta não é uma conta de gateway.", code=CONTA_NAO_GATEWAY)
    aid = str(account["id"])
    out = _blank(aid)
    state = _decode_cursor(_read_state(s, aid).get("cursor"))
    if since is not None:
        since_day, page = since, None  # an explicit window restarts pagination (offsets are only valid per `since`)
    else:
        since_day = to_date(state.get("since")) or to_date(account.get("opening_date")) or today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        page = state.get("page")
    newest: Optional[date] = None
    review_total = 0
    try:
        ops = resolve_operations(operations, str(account["gateway"]))
        for _ in range(max_pages):
            result = ops.list_balance_transactions(since=since_day, cursor=page)
            tally = {"already_booked": 0, "booked_fees": 0, "booked_transfers": 0, "review": []}
            for bt in result.items:
                handle_line(s, aid, bt, tally)
                day = _local_day(bt)
                newest = day if newest is None or day > newest else newest
            out["pages"] += 1
            out["fetched"] += len(result.items)
            for key in ("already_booked", "booked_fees", "booked_transfers"):
                out[key] += tally[key]
            review_total += len(tally["review"])
            out["review"].extend(tally["review"][: max(0, MAX_REVIEW_ROWS - len(out["review"]))])
            page = result.next_cursor
            if page is None:
                break
            _save_state(s, aid, cursor={"since": since_day.isoformat(), "page": page}, error=None)
        if page is None:
            resume_from = max(since_day, (newest or since_day) - timedelta(days=OVERLAP_DAYS))
            _save_state(s, aid, cursor={"since": resume_from.isoformat(), "page": None}, synced=True, error=None)
        else:
            out["status"] = "partial"  # page budget spent; the next run continues from the saved page
    except Exception as exc:
        out["status"] = "error"
        out["error"] = generic_error(exc)
        # a gateway error's text may echo the provider's body: log its generic code only, a traceback for our own bugs
        logger.warning("finance gateway sync %s failed: %s", aid, out["error"], exc_info=not isinstance(exc, PaymentGatewayError))
        try:
            _save_state(s, aid, cursor={"since": since_day.isoformat(), "page": page}, error=out["error"])
        except Exception:
            logger.exception("finance gateway sync %s: could not record last_error", aid)
    out["review_total"] = review_total
    return out


def sync_failed(result: dict) -> FinanceError:
    return FinanceError(
        SINCRONIZACAO_FALHOU,
        "A sincronização com o gateway falhou; ela será tentada novamente.",
        502,
        details={"last_error": result.get("error"), "partial": {k: result[k] for k in ("pages", "fetched")}},
    )


# ─── scheduled job ───────────────────────────────────────────────────────────

JOB_ID = "finance_gateway_sync"


def _gateway_accounts(db: Any, cfg: FinanceConfig) -> list[dict]:
    table = cfg.table("accounts")
    return list(
        iter_paged_rows(
            lambda start, end: db.table(table).select("id,org_id,gateway").eq("kind", AccountKind.GATEWAY.value)
            .eq("active", True).order("id").range(start, end).execute().data,
            label="finance gateway accounts",
        )
    )


def run_gateway_sync_all(db: Any, cfg: FinanceConfig, operations_for: Callable[[str, str], Optional[ChargeOperations]]) -> dict:
    """The `finance_gateway_sync` job body: EVERY org's active gateway account (service-role client).

    `operations_for(org_id, gateway)` returns the org's `ChargeOperations` (or `None` to skip an
    org with no credentials for that gateway). One failing account never starves the rest.
    """
    summary = {"accounts": 0, "synced": 0, "failed": 0, "skipped": 0, "review": 0}
    for row in _gateway_accounts(db, cfg):
        summary["accounts"] += 1
        org_id = str(row["org_id"])
        try:
            ops = operations_for(org_id, str(row["gateway"]))
            if ops is None:
                summary["skipped"] += 1
                continue
            result = sync_gateway_account(Scope(db, cfg, org_id), ops, row["id"])
        except Exception:
            summary["failed"] += 1
            logger.exception("finance: gateway sync of account %s crashed; retried next tick", row.get("id"))
            continue
        summary["review"] += result["review_total"]
        summary["synced" if result["status"] != "error" else "failed"] += 1
    return summary


def register_gateway_sync(
    cfg: FinanceConfig,
    *,
    get_db: Callable[[], Any],
    operations_for: Callable[[str, str], Optional[ChargeOperations]],
    scheduler: Any = None,
    job_id: str = JOB_ID,
    hours: int = 6,
) -> str:
    """Register the 6-hourly `finance_gateway_sync` job on the seed scheduler (call before `start_scheduler()`).

    `get_db` is called PER RUN (never captured). The job logs and swallows every exception: a failed
    tick must neither crash the scheduler nor de-register the job; failures are on each account's
    `last_error` and retried next tick. Re-registering the same `job_id` replaces the job.
    """
    from noctusai_lib.api import scheduler as seed_scheduler

    async def _job() -> None:
        try:
            summary = await asyncio.to_thread(lambda: run_gateway_sync_all(get_db(), cfg, operations_for))
            logger.info("finance gateway sync: %s", summary)
        except Exception:
            logger.error("finance gateway sync job %s failed", job_id, exc_info=True)

    (scheduler or seed_scheduler).register(job_id, _job, hours=hours)
    return job_id


__all__ = [
    "CONTA_NAO_GATEWAY",
    "JOB_ID",
    "SINCRONIZACAO_FALHOU",
    "generic_error",
    "handle_line",
    "register_gateway_sync",
    "run_gateway_sync_all",
    "sync_failed",
    "sync_gateway_account",
]
