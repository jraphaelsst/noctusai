"""Gateway charges for the receivables the seed contracts organ books.

The seed contracts organ books a monthly RECEIVABLE per contract (finance ``fin_entries``, idempotent per contract +
cycle). This module is the host's seam on top of that, three small pieces:

* ``OrbityContractsBilling`` -- a ``ContractsBilling`` that books through the seed ``SupabaseContractsBilling`` and then
  records the receivable's gateway state in ``billing_charges`` (one row per entry); on cancel it KEEPS a receivable the
  operator chose to preserve and queues the gateway-side cancel of one that already exists at the gateway.
* ``process_charges`` -- the worker body (the ``orbity_billing_process`` job): claims queued rows with
  ``billing_reserve_charges`` (SKIP LOCKED + stuck-row recovery), creates the Asaas charge and records the outcome
  (generated / retrying with backoff / failed + the last error), then drains the pending gateway cancels.
* ``plan_charge`` -- the pure decision "does this receivable go to the gateway?".

Honesty rules (the reason for every branch below):

* NO gateway configured / client opted out / method not gateway-shaped => the row is ``skipped`` WITH the reason: the
  receivable stays a plain receivable. Nothing is ever faked.
* Every attempt sends the SAME idempotency reference (``orbity:<entry_id>``) and asks the gateway to reuse a charge that
  already carries it (``CheckoutRequest.reuse_existing``): a timeout after the gateway accepted the POST is retried
  without a second charge. A row left in ``generating`` by a crashed worker is recovered by the reserve RPC.
* Missing CPF/CNPJ / e-mail is a PERMANENT failure with a message the operator can act on, never a retry loop.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from noctusai_lib.domain.commerce.errors import GatewayNotConfigured
from noctusai_lib.domain.contracts.billing import CANCELLED, KEPT_SETTLED, SupabaseContractsBilling
from noctusai_lib.domain.finance._common import Scope as FinanceScope
from noctusai_lib.domain.finance._common import month_start
from noctusai_lib.domain.finance.booking import SupabaseFinanceBooking
from noctusai_lib.domain.finance.entries import find_by_source
from noctusai_lib.integrations.payments.checkout import CheckoutRequest
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.billing import CONTRACTS_CFG, FINANCE_CFG, GATEWAY_NAME, gateway_is_configured

logger = logging.getLogger(__name__)

BR_TZ = ZoneInfo("America/Sao_Paulo")

CHARGES = "billing_charges"
ENTRIES = FINANCE_CFG.table("entries")
CONTRACTS = CONTRACTS_CFG.table("contracts")
CLIENTS = "clients"

#: Failed attempts allowed before a row is ``failed`` for good.
MAX_ATTEMPTS = 5
#: Minutes to wait before attempt N+1 after attempt N failed transiently (upstream's schedule).
RETRY_DELAYS_MINUTES = (0, 2, 10, 30, 120)
#: A row 'generating' for longer than this was abandoned by a crashed worker.
STALE_MINUTES = 10

#: ``clients.default_billing_type`` values that go to the gateway, and the Asaas method each one means.
GATEWAY_METHODS = {"pix": "pix", "boleto": "boleto"}

QUEUED, GENERATING, RETRYING, GENERATED, FAILED, SKIPPED = "queued", "generating", "retrying", "generated", "failed", "skipped"
_CANCELLABLE_BEFORE_GATEWAY = (QUEUED, RETRYING, FAILED)

_UUID_HEAD = re.compile(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}):")


class BillingError(Exception):
    """A refusal the router turns into an HTTP error (``status`` + stable ``code`` + pt-BR ``message``)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def external_ref_for(entry_id: Any) -> str:
    """The idempotency / conciliation reference SENT to the gateway on every attempt for this receivable."""
    return f"orbity:{entry_id}"


def contract_id_of(source_ref: Optional[str]) -> Optional[str]:
    """The contract id inside a contracts ``source_ref`` (``<contract_id>:<period>[:<kind>]``)."""
    m = _UUID_HEAD.match(source_ref or "")
    return m.group(1).lower() if m else None


def today_br() -> date:
    return datetime.now(BR_TZ).date()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── the pure decision ───────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChargePlan:
    status: str          # queued | skipped
    method: Optional[str]
    reason: Optional[str]


def plan_charge(client: Optional[dict], gateway_ready: bool) -> ChargePlan:
    """Does a receivable of ``client`` go to the gateway? ``skipped`` always carries the reason the operator reads."""
    if not client:
        return ChargePlan(SKIPPED, None, "Cliente não encontrado para este recebível.")
    if not client.get("billing_automation_enabled"):
        return ChargePlan(SKIPPED, None, "Cobrança automática desligada para este cliente.")
    kind = str(client.get("default_billing_type") or "").strip().lower()
    method = GATEWAY_METHODS.get(kind)
    if method is None:
        shown = kind or "não definida"
        return ChargePlan(SKIPPED, None, f"A forma de cobrança do cliente ({shown}) não usa gateway.")
    if not gateway_ready:
        return ChargePlan(SKIPPED, method, "Gateway de cobrança não configurado para esta organização.")
    return ChargePlan(QUEUED, method, None)


def backoff_minutes(attempt: int) -> int:
    """Wait before the attempt AFTER attempt number ``attempt`` (1-based) failed transiently."""
    return RETRY_DELAYS_MINUTES[max(0, min(attempt - 1, len(RETRY_DELAYS_MINUTES) - 1))]


# ── the store ─────────────────────────────────────────────────────────────────────────────────────────────────


def _first(res: Any) -> Optional[dict]:
    rows = getattr(res, "data", None) or []
    return rows[0] if rows else None


class ChargeStore:
    """Every query filters ``org_id`` explicitly (the client is the service role)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def charge_by_entry(self, org_id: str, entry_id: str) -> Optional[dict]:
        return _first(self._db.table(CHARGES).select("*").eq("org_id", str(org_id)).eq("entry_id", str(entry_id)).execute())

    def entry(self, org_id: str, entry_id: str) -> Optional[dict]:
        return _first(self._db.table(ENTRIES).select("*").eq("org_id", str(org_id)).eq("id", str(entry_id)).execute())

    def client(self, org_id: str, client_id: Optional[str]) -> Optional[dict]:
        if not client_id:
            return None
        return _first(self._db.table(CLIENTS).select("*").eq("org_id", str(org_id)).eq("id", str(client_id)).execute())

    def contract(self, org_id: str, contract_id: str) -> Optional[dict]:
        return _first(self._db.table(CONTRACTS).select("id,party_id,party_name").eq("org_id", str(org_id)).eq("id", contract_id).execute())

    def update_charge(self, org_id: str, charge_id: str, patch: dict) -> None:
        self._db.table(CHARGES).update(patch).eq("org_id", str(org_id)).eq("id", str(charge_id)).execute()

    def insert_charge(self, row: dict) -> bool:
        """False when a concurrent run inserted the same entry first (UNIQUE entry_id)."""
        try:
            self._db.table(CHARGES).insert(row).execute()
        except Exception as exc:  # noqa: BLE001 -- narrowed right below
            if is_unique_violation(exc):
                return False
            raise
        return True


def ensure_charge(db: Any, org_id: str, entry_id: str, *, client_id: Optional[str], contract_id: Optional[str],
                  gateway: Any = None) -> dict:
    """The ``billing_charges`` row of ``entry_id`` (created with the plan's status when it does not exist yet)."""
    store = ChargeStore(db)
    existing = store.charge_by_entry(org_id, entry_id)
    if existing is not None:
        return existing
    client = store.client(org_id, client_id)
    plan = plan_charge(client, gateway_is_configured(org_id, gateway) if client else False)
    row = {
        "id": str(uuid.uuid4()), "org_id": str(org_id), "entry_id": str(entry_id), "client_id": str(client_id) if client_id else None,
        "contract_id": str(contract_id) if contract_id else None, "gateway": GATEWAY_NAME if plan.status == QUEUED else None,
        "billing_method": plan.method, "external_ref": external_ref_for(entry_id),
        "generation_status": plan.status, "last_error": plan.reason,
    }
    if not store.insert_charge(row):
        return store.charge_by_entry(org_id, entry_id) or row
    return row


# ── the contracts-billing seam ───────────────────────────────────────────────────────────────────────────────


class OrbityContractsBilling:
    """``ContractsBilling`` = the seed one + the gateway state of each receivable it books."""

    def __init__(self, db: Any, *, gateway: Any = None, inner: Any = None) -> None:
        self._db = db
        self._gateway = gateway
        self._inner = inner or SupabaseContractsBilling(db, FINANCE_CFG)
        self._store = ChargeStore(db)

    def book_receivable(self, org_id: str, *, source_ref: str, **fields: Any) -> Optional[str]:
        entry_id = self._inner.book_receivable(org_id, source_ref=source_ref, **fields)
        if entry_id:
            contract_id = contract_id_of(source_ref)
            contract = self._store.contract(org_id, contract_id) if contract_id else None
            ensure_charge(self._db, org_id, entry_id, client_id=(contract or {}).get("party_id"), contract_id=contract_id,
                          gateway=self._gateway)
        return entry_id

    def cancel_receivable(self, org_id: str, *, source_ref: str) -> str:
        scope = FinanceScope(self._db, FINANCE_CFG, str(org_id))
        entry = find_by_source(scope, "contracts", source_ref)
        charge = self._store.charge_by_entry(org_id, entry["id"]) if entry else None
        if charge and charge.get("preserved_after_deactivation"):
            # The operator chose to KEEP this charge when inactivating the client: a contract termination must not undo it.
            return KEPT_SETTLED
        outcome = self._inner.cancel_receivable(org_id, source_ref=source_ref)
        if outcome == CANCELLED and charge:
            mark_cancelled(self._store, org_id, charge)
        return outcome


def mark_cancelled(store: ChargeStore, org_id: str, charge: dict) -> None:
    """A receivable was cancelled: cancel its gateway charge too (queued for the worker), or stop it ever being created."""
    if charge.get("external_id"):
        store.update_charge(org_id, charge["id"], {"gateway_cancel_status": "pending", "gateway_cancel_error": None})
    elif charge.get("generation_status") in _CANCELLABLE_BEFORE_GATEWAY:
        store.update_charge(org_id, charge["id"], {"generation_status": SKIPPED, "last_error": "Cancelada.", "next_attempt_at": None})


# ── manual actions ────────────────────────────────────────────────────────────────────────────────────────────


def requeue_charge(db: Any, org_id: str, entry_id: str, gateway: Any = None) -> dict:
    """Send a ``skipped`` / ``failed`` receivable to the gateway (after the operator fixed what blocked it)."""
    store = ChargeStore(db)
    charge = store.charge_by_entry(org_id, entry_id)
    if charge is None:
        raise BillingError(404, "cobranca_nao_encontrada", "Cobrança não encontrada.")
    if charge["generation_status"] in (GENERATED, GENERATING):
        raise BillingError(409, "cobranca_ja_gerada", "A cobrança já foi gerada no gateway (ou está sendo gerada).")
    entry = store.entry(org_id, entry_id)
    if entry is None or entry["status"] not in ("open", "partial"):
        raise BillingError(409, "recebivel_nao_aberto", "Só um recebível em aberto pode ser enviado ao gateway.")
    plan = plan_charge(store.client(org_id, charge.get("client_id")), gateway_is_configured(org_id, gateway))
    if plan.status != QUEUED:
        raise BillingError(409, "cobranca_nao_enfileirada", plan.reason or "Não foi possível enfileirar a cobrança.")
    patch = {"generation_status": QUEUED, "generation_attempts": 0, "last_error": None, "next_attempt_at": None,
             "gateway": GATEWAY_NAME, "billing_method": plan.method}
    store.update_charge(org_id, charge["id"], patch)
    return {**charge, **patch}


def create_extra_charge(db: Any, org_id: str, *, client_id: str, description: str, amount_cents: int, due_date: date,
                        gateway: Any = None) -> dict:
    """A one-off receivable for a client (outside any contract), tracked like a contract one."""
    store = ChargeStore(db)
    client = store.client(org_id, client_id)
    if client is None:
        raise BillingError(404, "cliente_nao_encontrado", "Cliente não encontrado.")
    if amount_cents <= 0:
        raise BillingError(422, "valor_invalido", "O valor deve ser maior que zero.")
    booking = SupabaseFinanceBooking(db, FINANCE_CFG)
    entry_id = booking.book_receivable(
        org_id, source="manual", source_ref=f"orbity-extra:{uuid.uuid4()}", description=description.strip(),
        counterparty_name=client.get("legal_name") or client.get("name"), counterparty_doc=client.get("document"),
        amount_cents=amount_cents, competence_month=month_start(due_date), due_date=due_date, category_hint="Serviços",
    )
    if not entry_id:
        raise BillingError(502, "financeiro_indisponivel", "Não foi possível lançar o recebível.")
    return ensure_charge(db, org_id, entry_id, client_id=client_id, contract_id=None, gateway=gateway) | {"entry_id": entry_id}


# ── the worker ────────────────────────────────────────────────────────────────────────────────────────────────


def _finish(store: ChargeStore, row: dict, patch: dict) -> None:
    store.update_charge(row["org_id"], row["id"], {**patch, "locked_at": None, "locked_by": None})


def _client_gaps(client: Optional[dict]) -> Optional[str]:
    if client is None:
        return "Cliente não encontrado."
    if not str(client.get("legal_name") or "").strip():
        return "Cliente sem Razão Social."
    if not "".join(ch for ch in str(client.get("document") or "") if ch.isalnum()):
        return "Cliente sem CPF/CNPJ (o gateway recusa uma cobrança sem documento do pagador)."
    if not str(client.get("email") or "").strip():
        return "Cliente sem e-mail (necessário para a cobrança no gateway)."
    return None


def process_one(db: Any, gateway: Any, row: dict, *, today: Optional[date] = None, max_attempts: int = MAX_ATTEMPTS) -> dict:
    """Generate the gateway charge of ONE reserved row and record the outcome. Never raises for a gateway failure."""
    store = ChargeStore(db)
    org_id, attempt = str(row["org_id"]), int(row.get("generation_attempts") or 1)
    now = _now()
    entry = store.entry(org_id, row["entry_id"])
    if entry is None or entry["status"] not in ("open", "partial"):
        _finish(store, row, {"generation_status": SKIPPED, "last_error": "O recebível não está mais em aberto.", "next_attempt_at": None})
        return {"entry_id": row["entry_id"], "status": SKIPPED}
    if row.get("external_id"):  # a previous attempt got through: idempotency hit, no second charge
        _finish(store, row, {"generation_status": GENERATED, "last_error": None, "next_attempt_at": None, "generated_at": now.isoformat()})
        return {"entry_id": row["entry_id"], "status": GENERATED, "external_id": row["external_id"]}
    client = store.client(org_id, row.get("client_id"))
    gap = _client_gaps(client)
    if gap:
        _finish(store, row, {"generation_status": FAILED, "last_error": gap, "next_attempt_at": None})
        return {"entry_id": row["entry_id"], "status": FAILED, "error": gap}
    try:
        checkout = gateway.hosted_checkout(org_id)
    except GatewayNotConfigured:
        msg = "Gateway de cobrança não configurado para esta organização."
        _finish(store, row, {"generation_status": SKIPPED, "last_error": msg, "next_attempt_at": None})
        return {"entry_id": row["entry_id"], "status": SKIPPED, "error": msg}
    today = today or today_br()
    request = CheckoutRequest(
        external_reference=row["external_ref"], email=str(client["email"]).strip(), name=str(client["legal_name"]).strip(),
        price=Money(int(entry["amount_cents"]) - int(entry.get("settled_cents") or 0)), billing_cycle=None,
        billing_method=row.get("billing_method") or "pix", tax_id="".join(ch for ch in str(client["document"]) if ch.isalnum()),
        description=str(entry["description"]), due_date=max(date.fromisoformat(str(entry["due_date"])[:10]), today),
        customer_reference=f"orbity-client:{client['id']}", reuse_existing=True,
    )
    try:
        session = checkout.create_checkout(request)
    except PaymentGatewayError as exc:
        transient = bool(exc.retryable) and attempt < max_attempts
        patch: dict[str, Any] = {"last_error": exc.message[:500]}
        if transient:
            patch.update(generation_status=RETRYING, next_attempt_at=(now + timedelta(minutes=backoff_minutes(attempt))).isoformat())
        else:
            patch.update(generation_status=FAILED, next_attempt_at=None)
        _finish(store, row, patch)
        logger.warning("billing: charge %s attempt %d %s: %s", row["entry_id"], attempt, patch["generation_status"], exc.message)
        return {"entry_id": row["entry_id"], "status": patch["generation_status"], "error": exc.message}
    patch = {
        "generation_status": GENERATED, "external_id": session.id_at_gateway, "invoice_url": session.checkout_url,
        "pix_payload": session.pix_qr.payload if session.pix_qr else None, "gateway": GATEWAY_NAME,
        "last_error": None, "next_attempt_at": None, "generated_at": now.isoformat(),
    }
    _finish(store, row, patch)
    # The receivable may have been cancelled WHILE the gateway call was in flight: the charge must not outlive it.
    current = store.entry(org_id, row["entry_id"])
    if current is not None and current["status"] == "cancelled":
        store.update_charge(org_id, row["id"], {"gateway_cancel_status": "pending", "gateway_cancel_error": None})
    return {"entry_id": row["entry_id"], "status": GENERATED, "external_id": session.id_at_gateway}


def cancel_pending_at_gateway(db: Any, gateway: Any, *, limit: int = 25, org_id: Optional[str] = None,
                              entry_ids: Optional[list[str]] = None) -> dict:
    """Cancel, at the gateway, the charges whose receivable was cancelled. Failures are RECORDED, never swallowed."""
    q = db.table(CHARGES).select("*").eq("gateway_cancel_status", "pending")
    if org_id:
        q = q.eq("org_id", str(org_id))
    rows = (q.limit(limit).execute().data or [])
    if entry_ids is not None:
        wanted = {str(e) for e in entry_ids}
        rows = [r for r in rows if str(r["entry_id"]) in wanted]
    store = ChargeStore(db)
    out = {"done": 0, "failed": 0, "pending": 0}
    for r in rows:
        org = str(r["org_id"])
        try:
            ops = gateway.charge_operations(org)
        except GatewayNotConfigured:
            store.update_charge(org, r["id"], {"gateway_cancel_error": "Gateway de cobrança não configurado: cancele a cobrança no painel do gateway."})
            out["pending"] += 1
            continue
        try:
            ops.cancel_charge(r["external_id"])
        except PaymentGatewayError as exc:
            if exc.status == 404 or exc.code == "resource_missing":
                store.update_charge(org, r["id"], {"gateway_cancel_status": "done", "gateway_cancel_error": None})
                out["done"] += 1
            elif exc.retryable:
                store.update_charge(org, r["id"], {"gateway_cancel_error": exc.message[:500]})
                out["pending"] += 1
            else:
                msg = ("A cobrança já foi paga no gateway: faça o estorno por lá." if exc.code == "charge_already_paid" else exc.message)[:500]
                store.update_charge(org, r["id"], {"gateway_cancel_status": "failed", "gateway_cancel_error": msg})
                out["failed"] += 1
            continue
        store.update_charge(org, r["id"], {"gateway_cancel_status": "done", "gateway_cancel_error": None})
        out["done"] += 1
    return out


def process_charges(db: Any, gateway: Any, *, limit: int = 5, worker_id: Optional[str] = None,
                    today: Optional[date] = None) -> dict:
    """The ``orbity_billing_process`` job body: recover stuck rows, claim, generate, then drain the gateway cancels."""
    worker = worker_id or f"orbity-billing-{uuid.uuid4().hex[:8]}"
    reserved = db.rpc("billing_reserve_charges", {"p_limit": limit, "p_worker": worker, "p_stale_minutes": STALE_MINUTES,
                                                   "p_max_attempts": MAX_ATTEMPTS}).execute().data or []
    counts: dict[str, int] = {"reserved": len(reserved), GENERATED: 0, RETRYING: 0, FAILED: 0, SKIPPED: 0}
    for row in reserved:
        try:
            result = process_one(db, gateway, row, today=today)
        except Exception:  # noqa: BLE001 -- one row's bug must not strand the rest; the stale-claim recovery retries it
            logger.exception("billing: charge %s crashed (left for stale-claim recovery)", row.get("entry_id"))
            continue
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    counts["gateway_cancel"] = cancel_pending_at_gateway(db, gateway)
    return counts


def has_billing_work(db: Any) -> bool:
    """Cheap pre-check for the job: anything queued / retrying / stuck / awaiting a gateway cancel?"""
    for status_filter in ((QUEUED, RETRYING), (GENERATING,)):
        rows = db.table(CHARGES).select("id").in_("generation_status", list(status_filter)).limit(1).execute().data
        if rows:
            return True
    return bool(db.table(CHARGES).select("id").eq("gateway_cancel_status", "pending").limit(1).execute().data)


__all__ = [
    "BillingError", "ChargePlan", "ChargeStore", "MAX_ATTEMPTS", "OrbityContractsBilling", "backoff_minutes",
    "cancel_pending_at_gateway", "contract_id_of", "create_extra_charge", "ensure_charge", "external_ref_for", "mark_cancelled",
    "has_billing_work", "plan_charge", "process_charges", "process_one", "requeue_charge",
]
