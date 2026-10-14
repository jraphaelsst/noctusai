"""Purchase orders: save (create / replace while draft), read, list and the approve -> send -> cancel lifecycle.

The RPCs are the authority (row lock on the order + every write in one transaction); Python resolves the supplier
snapshot, shapes the payload, decides WHO may approve, and maps refusals onto HTTP errors.

Approval rule (roadmap W3): approving needs `is_admin` or membership in THIS org's approver list (`pur_approvers`,
org-scoped -- never a global permission). An order whose total is ABOVE the org's `approval_threshold_cents` needs an
approver (an org admin who is not one is refused, unless the host opted in with
`PurchasingConfig.admin_approves_above_threshold`). No threshold set => no limit. `check_can_approve` is the friendly
pre-check; the AUTHORITY is `pur_transition`, which re-judges the limit (and the post-change cooldown) under the order's
row lock, so a concurrent edit that raises the total cannot slip past a stale Python read.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from . import settings as settings_svc
from ._common import Scope, first, qty_str, rpc as _rpc
from .errors import (
    APROVACAO_ACIMA_DO_LIMITE,
    FORNECEDOR_INVALIDO,
    SEM_PERMISSAO_APROVAR,
    forbidden,
    from_refusal,
    invalid,
    not_found,
)

logger = logging.getLogger(__name__)


# ─── supplier ────────────────────────────────────────────────────────────────


def get_party(s: Scope, party_id: Any) -> Optional[dict]:
    """The parties-organ row of THIS org (None when missing / foreign / the organ is not mounted)."""
    if not s.cfg.with_parties or not party_id:
        return None
    resp = s.db.table(s.cfg.parties_table).select("*").eq("org_id", s.org_id).eq("id", str(party_id)).limit(1).execute()
    return first(resp)


def _supplier(s: Scope, data: Mapping[str, Any]) -> tuple[Optional[str], str]:
    """`(party_id, supplier_name snapshot)` from the body."""
    party_id = data.get("party_id")
    if party_id and not s.cfg.with_parties:
        raise invalid("party_id", "Este módulo não está ligado ao cadastro de parceiros.", code=FORNECEDOR_INVALIDO)
    if party_id:
        party = get_party(s, party_id)
        if party is None:
            raise invalid("party_id", "Fornecedor não encontrado.", code=FORNECEDOR_INVALIDO)
        if not party.get("is_active", True):
            raise invalid("party_id", "O fornecedor está arquivado.", code=FORNECEDOR_INVALIDO)
        return str(party_id), str(party.get("trade_name") or party.get("legal_name") or "").strip()
    name = (data.get("supplier_name") or "").strip()
    if not name:
        raise invalid("supplier_name", "Informe o fornecedor.", code=FORNECEDOR_INVALIDO)
    return None, name


# ─── save / read ─────────────────────────────────────────────────────────────


def _payload(s: Scope, data: Mapping[str, Any], user_id: Optional[str]) -> dict:
    party_id, name = _supplier(s, data)
    row: dict[str, Any] = {
        "party_id": party_id,
        "supplier_name": name,
        "warehouse_id": str(data["warehouse_id"]) if data.get("warehouse_id") else None,
        "expected_date": data["expected_date"].isoformat() if data.get("expected_date") else None,
        "notes": data.get("notes"),
        "created_by": user_id,
        "lines": [
            {
                "item_id": str(line["item_id"]) if line.get("item_id") else None,
                "description": line["description"],
                "unit": line.get("unit"),
                "qty": qty_str(line["qty"]),
                "unit_cost_cents": int(line["unit_cost_cents"]),
            }
            for line in data.get("lines") or []
        ],
    }
    for key in ("installments_count", "first_due_days", "interval_days", "freight_cents", "discount_cents", "other_cents"):
        if data.get(key) is not None:
            row[key] = int(data[key])
    return row


def save_order(s: Scope, order_id: Optional[Any], data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Create (`order_id=None`) or replace a DRAFT order and its lines atomically; returns the order detail."""
    verdict = _rpc(s, "save_order", {"p_org": s.org_id, "p_order_id": str(order_id) if order_id else None, "p_row": _payload(s, data, user_id)})
    return get_order(s, verdict["order_id"])


def list_lines(s: Scope, order_id: Any) -> list[dict]:
    rows = s.rows("order_lines", eq={"order_id": str(order_id)})
    rows.sort(key=lambda r: (int(r.get("line_no") or 0), str(r["id"])))
    return rows


def get_order(s: Scope, order_id: Any) -> dict:
    """The order with its lines and its receipts (each with their lines)."""
    from . import receipts as receipts_svc  # local: receipts imports this module

    order = s.get("orders", order_id, what="Pedido de compra")
    return {**order, "lines": list_lines(s, order_id), "receipts": receipts_svc.list_for_order(s, order_id)}


def list_orders(
    s: Scope,
    *,
    status: Optional[str] = None,
    party_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    term = re.sub(r"[%_\\,().*]", " ", q or "").strip()

    def refine(query):
        if status:
            query = query.eq("status", status)
        if party_id:
            query = query.eq("party_id", str(party_id))
        if term:
            query = query.eq("number", int(term)) if term.isdigit() and len(term) < 9 else query.ilike("supplier_name", f"%{term}%")
        return query

    return s.page("orders", page=page, page_size=page_size, refine=refine, order=(("number", True), ("id", False)))


# ─── lifecycle ───────────────────────────────────────────────────────────────


def check_can_approve(
    s: Scope, order: Mapping[str, Any], *, is_admin: bool, can_approve: bool, threshold: Optional[int]
) -> None:
    """Raise 403 unless this caller may approve `order` (see the module docstring)."""
    if not (is_admin or can_approve):
        raise forbidden(SEM_PERMISSAO_APROVAR, "Aprovar pedidos exige ser aprovador desta organização ou administrador.")
    above = threshold is not None and int(order["total_cents"]) > threshold
    if above and not can_approve and not (is_admin and s.cfg.admin_approves_above_threshold):
        raise forbidden(
            APROVACAO_ACIMA_DO_LIMITE,
            "Pedidos acima do limite de aprovação exigem um aprovador desta organização.",
        )


def _transition(
    s: Scope, order_id: Any, action: str, *, user_id: Optional[str], reason: Optional[str] = None, actor_can_exceed: bool = False
) -> dict:
    _rpc(
        s, "transition",
        {"p_org": s.org_id, "p_order_id": str(order_id), "p_action": action, "p_user": user_id, "p_reason": reason,
         "p_actor_can_exceed": actor_can_exceed},
    )
    return get_order(s, order_id)


def approve_order(s: Scope, order_id: Any, *, user_id: Optional[str], is_admin: bool, can_approve: bool) -> dict:
    order = s.find("orders", order_id)
    if order is None:
        raise not_found("Pedido de compra")
    check_can_approve(s, order, is_admin=is_admin, can_approve=can_approve, threshold=settings_svc.threshold_cents(s))
    # `can_exceed` is what the RPC enforces under the lock: an approver, or an admin when the host opted in.
    can_exceed = can_approve or (is_admin and s.cfg.admin_approves_above_threshold)
    return _transition(s, order_id, "approve", user_id=user_id, actor_can_exceed=can_exceed)


def send_order(s: Scope, order_id: Any, *, user_id: Optional[str] = None) -> dict:
    return _transition(s, order_id, "send", user_id=user_id)


def cancel_order(s: Scope, order_id: Any, *, user_id: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """Cancel an order that has NO receipt yet (409 `pedido_com_recebimento` otherwise)."""
    return _transition(s, order_id, "cancel", user_id=user_id, reason=reason)


__all__ = [
    "approve_order", "cancel_order", "check_can_approve", "get_order", "get_party", "list_lines", "list_orders",
    "save_order", "send_order",
]
