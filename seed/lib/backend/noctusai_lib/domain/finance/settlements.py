"""Settlements (payments / refunds), their ledger rows, reversal, and transfers.

Money rules (contract §3.3):

- `settled_cents` = Σ unreversed payment settlements − Σ unreversed refund
  settlements; the entry status is re-derived from it every time.
- A settlement books ledger rows on its account: the settled amount (`settlement`)
  in the entry's direction -- IN for a receivable payment, OUT for a payable one,
  both flipped for a refund -- plus a `fee` OUT row when `fee_cents > 0`. The
  account's net effect of a receivable payment is therefore `amount - fee`.
- Settlements and ledger rows are NEVER deleted by the product: a reversal flips
  `reversed_*` on the settlement and books opposite ledger rows (`reverses_id`).
- A settlement with an `external_ref` is idempotent on `(kind, external_ref)`: a
  replay (webhook redelivery, bridge retry) returns the existing one and heals any
  missing ledger rows / entry total.

PostgREST has no multi-statement transaction, so the write order is chosen so every
partial failure converges on retry: ledger inserts are unique per
`(settlement_id, origin)` / `reverses_id`, and the entry total is always RE-DERIVED
from the settlement rows, never incremented.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, iso, new_id, now_iso, today
from .accounts import require_usable_account
from .entries import get_entry, status_for
from .errors import (
    BAIXA_DUPLICADA,
    BAIXA_EXCEDE_SALDO,
    BAIXA_JA_ESTORNADA,
    ESTORNO_EXCEDE_PAGO,
    LANCAMENTO_CANCELADO,
    conflict,
    invalid,
)
from .types import (
    EntryDirection,
    EntryStatus,
    LedgerDirection,
    LedgerOrigin,
    SettlementKind,
    values,
)

logger = logging.getLogger(__name__)


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _flip(direction: str) -> str:
    return LedgerDirection.OUT.value if direction == LedgerDirection.IN.value else LedgerDirection.IN.value


def main_ledger_direction(entry_direction: str, kind: str) -> str:
    """IN for a receivable payment / payable refund, OUT for a payable payment / receivable refund."""
    incoming = (entry_direction == EntryDirection.RECEIVABLE.value) == (kind == SettlementKind.PAYMENT.value)
    return LedgerDirection.IN.value if incoming else LedgerDirection.OUT.value


# ─── entry total ─────────────────────────────────────────────────────────────


def recompute_entry(s: Scope, entry_id: Any) -> dict:
    """Re-derive `settled_cents` + `status` from the unreversed settlements (idempotent)."""
    entry = get_entry(s, entry_id)
    live = s.rows("settlements", eq={"entry_id": str(entry_id)}, refine=lambda q: q.is_("reversed_at", "null"))
    settled = sum(
        int(r["amount_cents"]) if r["kind"] == SettlementKind.PAYMENT.value else -int(r["amount_cents"]) for r in live
    )
    patch: dict[str, Any] = {"settled_cents": settled, "updated_at": now_iso()}
    if entry["status"] != EntryStatus.CANCELLED.value:
        patch["status"] = status_for(int(entry["amount_cents"]), settled)
    s.tbl("entries").update(patch).eq("org_id", s.org_id).eq("id", str(entry_id)).execute()
    return {**entry, **patch}


# ─── ledger ──────────────────────────────────────────────────────────────────


def _ledger_row(s: Scope, *, account_id: str, on: str, direction: str, amount: int, origin: str, description: Optional[str], **extra: Any) -> dict:
    return {
        "id": new_id(),
        "org_id": s.org_id,
        "account_id": account_id,
        "occurred_on": on,
        "direction": direction,
        "amount_cents": amount,
        "origin": origin,
        "description": description,
        "created_at": now_iso(),
        **extra,
    }


def _settlement_ledger_rows(s: Scope, st: Mapping[str, Any], entry: Mapping[str, Any]) -> list[dict]:
    rows = [
        _ledger_row(
            s,
            account_id=str(st["account_id"]),
            on=iso(st["settled_on"]),
            direction=main_ledger_direction(entry["direction"], st["kind"]),
            amount=int(st["amount_cents"]),
            origin=LedgerOrigin.SETTLEMENT.value,
            description=entry.get("description"),
            settlement_id=str(st["id"]),
        )
    ]
    if int(st.get("fee_cents") or 0) > 0:
        rows.append(
            _ledger_row(
                s,
                account_id=str(st["account_id"]),
                on=iso(st["settled_on"]),
                direction=LedgerDirection.OUT.value,
                amount=int(st["fee_cents"]),
                origin=LedgerOrigin.FEE.value,
                description=f"Tarifa: {entry.get('description') or ''}".strip(),
                settlement_id=str(st["id"]),
            )
        )
    return rows


def book_settlement_ledger(s: Scope, st: Mapping[str, Any], entry: Mapping[str, Any]) -> list[dict]:
    """Insert the ledger rows a settlement is owed; rows that already exist are left alone (idempotent)."""
    have = {
        r["origin"]
        for r in s.rows("ledger", eq={"settlement_id": str(st["id"])}, refine=lambda q: q.is_("reverses_id", "null"))
    }
    wanted = [r for r in _settlement_ledger_rows(s, st, entry) if r["origin"] not in have]
    if wanted:
        s.tbl("ledger").insert(wanted).execute()
    return wanted


def list_settlement_ledger(s: Scope, settlement_id: Any) -> list[dict]:
    return s.rows("ledger", eq={"settlement_id": str(settlement_id)})


# ─── settle ──────────────────────────────────────────────────────────────────


def find_settlement_by_ref(s: Scope, kind: str, external_ref: str) -> Optional[dict]:
    resp = (
        s.tbl("settlements").select("*").eq("org_id", s.org_id).eq("kind", kind).eq("external_ref", external_ref).limit(1).execute()
    )
    return first(resp)


def _rollback(s: Scope, settlement_id: str) -> None:
    """Undo a settlement THIS call just inserted (it never became visible to a reader as complete)."""
    try:
        s.tbl("ledger").delete().eq("org_id", s.org_id).eq("settlement_id", settlement_id).execute()
        s.tbl("settlements").delete().eq("org_id", s.org_id).eq("id", settlement_id).execute()
    except Exception:
        logger.exception("finance: could not roll back half-written settlement %s", settlement_id)


def settle_entry(s: Scope, entry_id: Any, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Book a payment / refund against an entry. Returns `{settlement, entry, replayed}`."""
    entry = get_entry(s, entry_id)
    kind = _plain(data.get("kind") or SettlementKind.PAYMENT.value)
    if kind not in values(SettlementKind):
        raise invalid("kind", "Tipo de baixa inválido.")
    external_ref = (str(data["external_ref"]).strip() or None) if data.get("external_ref") else None

    if external_ref:
        prior = find_settlement_by_ref(s, kind, external_ref)
        if prior is not None:
            if str(prior["entry_id"]) != str(entry["id"]):
                raise conflict(BAIXA_DUPLICADA, "Esta referência já foi usada em outro lançamento.")
            book_settlement_ledger(s, prior, entry)
            healed = recompute_entry(s, entry["id"])
            return {"settlement": prior, "entry": healed, "replayed": True}

    if entry["status"] == EntryStatus.CANCELLED.value:
        raise conflict(LANCAMENTO_CANCELADO, "O lançamento está cancelado.")
    account = require_usable_account(s, data["account_id"])
    amount = int(data["amount_cents"])
    fee = int(data.get("fee_cents") or 0)
    if amount <= 0:
        raise invalid("amount_cents", "O valor deve ser maior que zero.")
    if fee < 0:
        raise invalid("fee_cents", "A tarifa não pode ser negativa.")
    settled = int(entry.get("settled_cents") or 0)
    if kind == SettlementKind.PAYMENT.value and amount > int(entry["amount_cents"]) - settled:
        raise invalid("amount_cents", "O valor excede o saldo em aberto do lançamento.", code=BAIXA_EXCEDE_SALDO)
    if kind == SettlementKind.REFUND.value and amount > settled:
        raise invalid("amount_cents", "O estorno excede o valor já pago.", code=ESTORNO_EXCEDE_PAGO)
    line_id = data.get("statement_line_id")
    if line_id:
        s.require_owned("statement_lines", line_id, what="Linha de extrato", field="statement_line_id")

    row = {
        "id": new_id(),
        "org_id": s.org_id,
        "entry_id": str(entry["id"]),
        "account_id": str(account["id"]),
        "kind": kind,
        "settled_on": iso(data.get("settled_on") or today()),
        "amount_cents": amount,
        "fee_cents": fee,
        "method": data.get("method") or None,
        "external_ref": external_ref,
        "statement_line_id": str(line_id) if line_id else None,
        "created_by": user_id,
        "created_at": now_iso(),
    }
    try:
        saved = first(s.tbl("settlements").insert(row).execute()) or row
    except Exception as exc:
        if external_ref and is_unique_violation(exc):
            # Lost the race to a concurrent identical delivery: that one wins; replay through it.
            return settle_entry(s, entry_id, data, user_id=user_id)
        raise
    try:
        book_settlement_ledger(s, saved, entry)
        updated = recompute_entry(s, entry["id"])
    except Exception:
        _rollback(s, str(saved["id"]))
        raise
    return {"settlement": saved, "entry": updated, "replayed": False}


# ─── reverse ─────────────────────────────────────────────────────────────────


def reverse_settlement(s: Scope, settlement_id: Any, reason: str, *, user_id: Optional[str] = None) -> dict:
    """Reverse a settlement: opposite ledger rows, `reversed_*` stamped, entry total re-derived."""
    st = s.get("settlements", settlement_id, what="Baixa")
    reason = (reason or "").strip()
    if not reason:
        raise invalid("reason", "Informe o motivo do estorno.")
    if st.get("reversed_at"):
        raise conflict(BAIXA_JA_ESTORNADA, "Esta baixa já foi estornada.")
    entry = get_entry(s, st["entry_id"])
    settled = int(entry.get("settled_cents") or 0)
    amount = int(st["amount_cents"])
    after = settled - amount if st["kind"] == SettlementKind.PAYMENT.value else settled + amount
    if after < 0:
        raise conflict("baixa_com_estorno", "Estorne primeiro os reembolsos lançados sobre este pagamento.")
    if after > int(entry["amount_cents"]):
        raise conflict("baixa_com_estorno", "O estorno deixaria o lançamento pago acima do seu valor.")

    originals = [r for r in list_settlement_ledger(s, settlement_id) if not r.get("reverses_id")]
    reversed_ids = {str(r["reverses_id"]) for r in list_settlement_ledger(s, settlement_id) if r.get("reverses_id")}
    on = today().isoformat()
    opposite = [
        _ledger_row(
            s,
            account_id=str(r["account_id"]),
            on=on,
            direction=_flip(r["direction"]),
            amount=int(r["amount_cents"]),
            origin=r["origin"],
            description=f"Estorno: {r.get('description') or ''}".strip(),
            settlement_id=str(settlement_id),
            reverses_id=str(r["id"]),
        )
        for r in originals
        if str(r["id"]) not in reversed_ids
    ]
    try:
        if opposite:
            s.tbl("ledger").insert(opposite).execute()
        patch = {"reversed_at": now_iso(), "reversed_by": user_id, "reversal_reason": reason}
        s.tbl("settlements").update(patch).eq("org_id", s.org_id).eq("id", str(settlement_id)).is_("reversed_at", "null").execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(BAIXA_JA_ESTORNADA, "Esta baixa já foi estornada.") from exc
        raise
    updated = recompute_entry(s, entry["id"])
    return {"settlement": {**st, **patch}, "entry": updated}


# ─── transfers ───────────────────────────────────────────────────────────────


def create_transfer(s: Scope, data: Mapping[str, Any]) -> dict:
    """Move money between two of the org's accounts: two ledger rows sharing `transfer_group` (never an entry)."""
    src, dst = str(data["from_account_id"]), str(data["to_account_id"])
    if src == dst:
        raise invalid("to_account_id", "As contas de origem e destino devem ser diferentes.", code="transferencia_mesma_conta")
    amount = int(data["amount_cents"])
    if amount <= 0:
        raise invalid("amount_cents", "O valor deve ser maior que zero.")
    require_usable_account(s, src, field="from_account_id")
    require_usable_account(s, dst, field="to_account_id")
    group = new_id()
    on = iso(data.get("occurred_on") or today())
    text = data.get("description") or "Transferência entre contas"
    rows = [
        _ledger_row(s, account_id=src, on=on, direction=LedgerDirection.OUT.value, amount=amount,
                    origin=LedgerOrigin.TRANSFER.value, description=text, transfer_group=group),
        _ledger_row(s, account_id=dst, on=on, direction=LedgerDirection.IN.value, amount=amount,
                    origin=LedgerOrigin.TRANSFER.value, description=text, transfer_group=group),
    ]
    s.tbl("ledger").insert(rows).execute()
    return {"transfer_group": group, "occurred_on": on, "amount_cents": amount, "from_account_id": src,
            "to_account_id": dst, "description": text}


__all__ = [
    "book_settlement_ledger",
    "create_transfer",
    "find_settlement_by_ref",
    "main_ledger_direction",
    "recompute_entry",
    "reverse_settlement",
    "settle_entry",
]
