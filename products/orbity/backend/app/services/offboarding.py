"""Client inactivation with kept charges -- ONE admin-only server operation.

What the operator decides: for each of the client's OPEN charges (pending + overdue) -- cancel it (default) or keep it.
What the server guarantees, in this order:

1. ATOMIC (``orbity.offboard_client`` RPC, one transaction): every open charge is cancelled or flagged preserved, and the
   client row goes inactive (``inactivated_at`` stamped). All or nothing -- an undecided / foreign / partially-paid charge
   rolls the whole thing back and the client stays active.
2. The client's live contracts are TERMINATED through the seed contracts organ (``terminate_contract``: version history,
   unsettled future receivables cancelled). A charge the operator KEPT survives that: ``OrbityContractsBilling`` answers
   "kept" for a preserved receivable, so the organ never cancels it.
3. A cancelled charge that already exists at the gateway is cancelled THERE too (the upstream gap: the receivable was
   cancelled and the boleto/PIX stayed payable). A failed gateway cancel is recorded on the charge and retried by the
   worker -- never swallowed.

Steps 2-3 run after step 1 committed. If one fails the client IS inactive and the response says exactly which contract /
charge is left: re-running the same call finishes the job (step 1 finds nothing left to decide, steps 2-3 are idempotent).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from noctusai_lib.domain.contracts import ContractsScope
from noctusai_lib.domain.contracts import contracts as contracts_svc

from app.billing import CONTRACTS_CFG
from app.services.billing_charges import (
    CONTRACTS, BillingError, ChargeStore, OrbityContractsBilling, cancel_pending_at_gateway,
)
from app.services.financial_service import FinancialService

logger = logging.getLogger(__name__)

CANCEL, KEEP = "cancel", "keep"
TERMINATION_REASON = "Cliente inativado"

_RPC_REFUSALS = {
    "unresolved_charges": (409, "cobrancas_em_aberto", "Decida o destino de todas as cobranças em aberto do cliente."),
    "charge_not_open_for_client": (422, "cobranca_invalida", "Uma das cobranças informadas não está em aberto para este cliente."),
    "charge_in_both_lists": (422, "cobranca_duplicada", "Uma cobrança não pode ser cancelada e mantida ao mesmo tempo."),
    "charge_has_settlements": (409, "cobranca_parcialmente_paga", "Uma cobrança com pagamento parcial não pode ser cancelada: mantenha-a."),
    "client_not_found": (404, "cliente_nao_encontrado", "Cliente não encontrado."),
}


def preview(db: Any, org_id: str, client_id: str) -> dict:
    """What inactivating the client touches: its open charges (still to decide) and its live contracts."""
    store = ChargeStore(db)
    client = store.client(org_id, client_id)
    if client is None:
        raise BillingError(404, "cliente_nao_encontrado", "Cliente não encontrado.")
    charges = [c for c in FinancialService(db, org_id).open_charges_of_client(client_id) if not c["preserved_after_deactivation"]]
    contracts = (
        db.table(CONTRACTS).select("id,title,status").eq("org_id", str(org_id)).eq("party_id", str(client_id))
        .in_("status", ["active", "suspended"]).execute().data or []
    )
    return {
        "client": {"id": str(client["id"]), "name": client.get("legal_name") or client.get("name"), "active": bool(client.get("active"))},
        "charges": charges,
        "contracts": [{"id": str(c["id"]), "title": c["title"], "status": c["status"]} for c in contracts],
    }


def deletion_blockers(db: Any, org_id: str, client_id: str) -> dict:
    """What stops a client from being deleted: a live contract (active/suspended) or an open charge.

    Reuses ``preview`` (the same two questions inactivation asks). ``{"contracts": [...], "charges": [...]}``
    -- both empty means the client can be deleted. Raises ``BillingError(404)`` for an unknown client.
    """
    state = preview(db, org_id, client_id)
    return {"contracts": state["contracts"], "charges": state["charges"]}


def _rpc_refusal(exc: Exception) -> Optional[BillingError]:
    text = str(exc)
    for marker, (status, code, message) in _RPC_REFUSALS.items():
        if marker in text:
            return BillingError(status, code, message)
    return None


def offboard(db: Any, gateway: Any, org_id: str, client_id: str, decisions: dict[str, str], *, user_id: Optional[str] = None,
             on: Optional[date] = None) -> dict:
    """Inactivate ``client_id``. ``decisions`` = ``{entry_id: 'cancel' | 'keep'}`` for every open charge."""
    state = preview(db, org_id, client_id)
    by_id = {c["entry_id"]: c for c in state["charges"]}
    unknown = sorted(set(decisions) - set(by_id))
    if unknown:
        raise BillingError(422, "cobranca_invalida", "Uma das cobranças informadas não está em aberto para este cliente.")
    bad = sorted({a for a in decisions.values() if a not in (CANCEL, KEEP)})
    if bad:
        raise BillingError(422, "acao_invalida", "A ação de cada cobrança deve ser 'cancel' ou 'keep'.")
    undecided = sorted(set(by_id) - set(decisions))
    if undecided:
        raise BillingError(409, "cobrancas_em_aberto", "Decida o destino de todas as cobranças em aberto do cliente.")
    cancel = [e for e, a in decisions.items() if a == CANCEL]
    keep = [e for e, a in decisions.items() if a == KEEP]
    if any(by_id[e]["entry_status"] == "partial" for e in cancel):
        raise BillingError(409, "cobranca_parcialmente_paga", "Uma cobrança com pagamento parcial não pode ser cancelada: mantenha-a.")

    try:
        result = db.rpc("offboard_client", {
            "p_org_id": str(org_id), "p_client_id": str(client_id),
            "p_cancel_entry_ids": cancel, "p_preserve_entry_ids": keep,
        }).execute().data
    except Exception as exc:  # noqa: BLE001 -- a known refusal becomes its HTTP error; anything else propagates loudly
        refusal = _rpc_refusal(exc)
        if refusal is not None:
            raise refusal from exc
        raise
    if isinstance(result, list):  # PostgREST returns a scalar jsonb as-is; be liberal with a one-row wrapper
        result = result[0] if result else {}
    result = result or {}

    summary: dict[str, Any] = {
        "client_id": str(client_id), "cancelled": int(result.get("cancelled", len(cancel))),
        "preserved": int(result.get("preserved", len(keep))), "contracts_terminated": [], "contracts_failed": [],
        "gateway_cancelled": 0, "gateway_pending": 0,
    }

    billing = OrbityContractsBilling(db, gateway=gateway)
    scope = ContractsScope(db, CONTRACTS_CFG, str(org_id))
    for contract in state["contracts"]:
        try:
            contracts_svc.terminate_contract(
                scope, contract["id"],
                {"reason": TERMINATION_REASON, "effective_on": None, "waive_notice": True, "waive_penalty": True},
                billing=billing, user_id=user_id, on=on,
            )
            summary["contracts_terminated"].append(contract["id"])
        except Exception as exc:  # noqa: BLE001 -- recorded and reported; the client is already inactive, a re-run finishes
            logger.exception("offboarding: terminating contract %s failed org=%s", contract["id"], org_id)
            summary["contracts_failed"].append({"id": contract["id"], "title": contract["title"], "error": str(exc)})

    # Every pending cancel of THIS org: the ones the RPC queued and the ones the contract termination queued.
    gw = cancel_pending_at_gateway(db, gateway, org_id=str(org_id))
    summary["gateway_cancelled"], summary["gateway_pending"] = gw["done"], gw["pending"] + gw["failed"]
    return summary


__all__ = ["CANCEL", "KEEP", "deletion_blockers", "offboard", "preview"]
