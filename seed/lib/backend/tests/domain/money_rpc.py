"""A `MockSupabaseClient` whose `rpc()` runs the P4 money RPCs in Python, over the mock's own tables.

The mock's stock `rpc` only returns canned data. The commerce refund RPC and the finance settle / reverse RPCs
carry real logic (a row lock + a balance check), so the service tests need them to behave. This is a MIRROR
of the SQL in `domain/commerce/money_sql.py` and `domain/finance/sql.py` -- the SQL itself is proven on a real
Postgres by `test_money_sql_on_real_postgres.py` / `test_sql_on_real_postgres.py`; here a `threading.Lock`
stands in for `SELECT ... FOR UPDATE` so concurrent callers serialize the way the database makes them.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from noctusai_lib.testing.mocks import MockSupabaseClient


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Result:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def execute(self) -> Any:
        return SimpleNamespace(data=self._payload, count=None)


class RpcMockClient(MockSupabaseClient):
    """`MockSupabaseClient` + faithful money RPCs. `lock_hold` lets a test pause inside the critical section."""

    def __init__(self, *a: Any, finance_prefix: str = "fin_", **kw: Any) -> None:
        super().__init__(*a, **kw)
        self._money_lock = threading.RLock()
        self._finance_prefix = finance_prefix

    # ── helpers ──────────────────────────────────────────────────────────
    def _rows(self, table: str, **eq: Any) -> list[dict]:
        q = self.table(table).select("*")
        for k, v in eq.items():
            q = q.eq(k, v)
        return [dict(r) for r in (q.execute().data or [])]

    def _one(self, table: str, **eq: Any) -> Optional[dict]:
        rows = self._rows(table, **eq)
        return rows[0] if rows else None

    # ── dispatch ─────────────────────────────────────────────────────────
    def rpc(self, name, params=None):  # noqa: D401
        p = dict(params or {})
        if name == "commerce_create_refund":
            with self._money_lock:
                payload = self._create_refund(p)
            self.rpc_calls.append((name, p))
            return _Result(payload)
        fp = self._finance_prefix
        if name == f"{fp}settle_entry_locked":
            with self._money_lock:
                payload = self._settle(p)
            self.rpc_calls.append((name, p))
            return _Result(payload)
        if name == f"{fp}reverse_settlement_locked":
            with self._money_lock:
                payload = self._reverse(p)
            self.rpc_calls.append((name, p))
            return _Result(payload)
        return super().rpc(name, params)

    # ── commerce_create_refund ───────────────────────────────────────────
    def _create_refund(self, p: dict) -> dict:
        org, oid = str(p["p_org_id"]), str(p["p_order_id"])
        order = self._one("commerce_orders", org_id=org, id=oid)
        if order is None:
            return {"status": "refused", "code": "pedido_nao_encontrado"}
        key = p.get("p_idempotency_key")
        refunds = self._rows("commerce_refunds", order_id=oid)
        if key is not None:
            prior = next((r for r in refunds if r.get("idempotency_key") == key), None)
            if prior:
                return {"status": "replayed", "refund": prior}
        if order["status"] not in ("paid", "partially_refunded"):
            return {"status": "refused", "code": "pedido_nao_reembolsavel"}
        paid = sorted((c for c in self._rows("commerce_order_charges", order_id=oid) if c["status"] == "paid"), key=lambda c: c["attempt"])
        if not paid:
            return {"status": "refused", "code": "cobranca_nao_encontrada"}
        charge = paid[-1]
        if int(charge["installment_count"]) > 1:
            return {"status": "refused", "code": "estorno_parcelado_indisponivel"}
        if any(r["status"] == "requested" for r in refunds):
            return {"status": "refused", "code": "estorno_em_andamento"}
        remaining = int(charge["amount_cents"]) - sum(int(r["amount_cents"]) for r in refunds if r["status"] != "failed")
        amount = remaining if p.get("p_amount_cents") is None else int(p["p_amount_cents"])
        if amount <= 0 or amount > remaining:
            return {"status": "refused", "code": "valor_excede_saldo", "refundable_cents": remaining}
        row = {
            "id": str(uuid.uuid4()), "org_id": org, "order_id": oid, "charge_id": charge["id"], "amount_cents": amount,
            "reason": p.get("p_reason") or "", "status": "requested", "gateway_refund_id": None, "idempotency_key": key,
            "requested_by": p.get("p_requested_by"), "created_at": _now(), "done_at": None,
        }
        self.table("commerce_refunds").insert(row).execute()
        return {
            "status": "created", "refund": row, "refundable_cents": remaining,
            "charge": {
                "id": charge["id"], "gateway": charge["gateway"], "gateway_charge_id": charge["gateway_charge_id"],
                "amount_cents": charge["amount_cents"], "installment_count": charge["installment_count"],
            },
        }

    # ── finance ──────────────────────────────────────────────────────────
    def _fin(self, name: str) -> str:
        return f"{self._finance_prefix}{name}"

    def _settled(self, entry_id: str) -> int:
        live = [r for r in self._rows(self._fin("settlements"), entry_id=entry_id) if not r.get("reversed_at")]
        return sum(int(r["amount_cents"]) if r["kind"] == "payment" else -int(r["amount_cents"]) for r in live)

    def _settle(self, p: dict) -> dict:
        org, eid, row = str(p["p_org_id"]), str(p["p_entry_id"]), dict(p["p_row"])
        amount_raw = row.get("amount_cents")
        if amount_raw is None or int(amount_raw) <= 0:
            return {"status": "refused", "code": "valor_invalido"}
        if row.get("kind") not in ("payment", "refund"):
            return {"status": "refused", "code": "tipo_invalido"}
        entry = self._one(self._fin("entries"), org_id=org, id=eid)
        if entry is None:
            return {"status": "not_found"}
        if entry["status"] == "cancelled":
            return {"status": "refused", "code": "lancamento_cancelado"}
        settled, amount = self._settled(eid), int(row["amount_cents"])
        if row["kind"] == "payment" and amount > int(entry["amount_cents"]) - settled:
            return {"status": "refused", "code": "baixa_excede_saldo"}
        if row["kind"] == "refund" and amount > settled:
            return {"status": "refused", "code": "estorno_excede_pago"}
        row.update({"org_id": org, "entry_id": eid})
        saved = (self.table(self._fin("settlements")).insert(row).execute().data or [row])[0]
        return {"status": "ok", "settlement": dict(saved)}

    def _reverse(self, p: dict) -> dict:
        org, sid = str(p["p_org_id"]), str(p["p_settlement_id"])
        st = self._one(self._fin("settlements"), org_id=org, id=sid)
        if st is None:
            return {"status": "not_found"}
        if st.get("reversed_at"):
            return {"status": "already_reversed"}
        entry = self._one(self._fin("entries"), id=st["entry_id"])
        settled = self._settled(str(entry["id"]))
        amount = int(st["amount_cents"])
        after = settled - amount if st["kind"] == "payment" else settled + amount
        if after < 0 or after > int(entry["amount_cents"]):
            return {"status": "refused", "code": "baixa_com_estorno"}
        patch = {"reversed_at": _now(), "reversed_by": p.get("p_user"), "reversal_reason": p["p_reason"]}
        self.table(self._fin("settlements")).update(patch).eq("org_id", org).eq("id", sid).execute()
        ledger = self._rows(self._fin("ledger"), settlement_id=sid)
        reversed_ids = {str(r["reverses_id"]) for r in ledger if r.get("reverses_id")}
        opposite = [
            {
                "id": str(uuid.uuid4()), "org_id": r["org_id"], "account_id": r["account_id"], "occurred_on": p["p_on"],
                "direction": "out" if r["direction"] == "in" else "in", "amount_cents": r["amount_cents"], "origin": r["origin"],
                "description": f"Estorno: {r.get('description') or ''}".strip(), "settlement_id": sid, "reverses_id": r["id"],
                "created_at": _now(),
            }
            for r in ledger
            if not r.get("reverses_id") and str(r["id"]) not in reversed_ids
        ]
        if opposite:
            self.table(self._fin("ledger")).insert(opposite).execute()
        return {"status": "ok", "settlement": {**st, **patch}}
