"""Accounts -- bank / cash / gateway wallets and their ledger balance."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_foreign_key_violation, is_unique_violation

from ._common import Scope, first, iso, new_id, now_iso, to_date, today
from .errors import CONTA_COM_MOVIMENTO, CONTA_EM_USO, CONTA_GATEWAY_DUPLICADA, CONTA_INATIVA, conflict, invalid
from .types import AccountKind, LedgerDirection

logger = logging.getLogger(__name__)

_FIELDS = ("name", "bank_code", "agency", "number", "opening_balance_cents", "opening_date", "gateway", "active", "accounting_code")
_LEDGER = "ledger"


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _clean(data: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: _plain(v) for k, v in data.items() if k in _FIELDS or k == "kind"}
    if "opening_date" in out:
        out["opening_date"] = iso(out["opening_date"])
    if "accounting_code" in out:
        out["accounting_code"] = str(out["accounting_code"]).strip() or None if out["accounting_code"] is not None else None
    if "gateway" in out and out["gateway"]:
        out["gateway"] = str(out["gateway"]).strip().lower()
    return out


def list_accounts(s: Scope, *, active: Optional[bool] = None) -> list[dict]:
    eq = {"active": active} if active is not None else None
    rows = s.rows("accounts", eq=eq)
    rows.sort(key=lambda r: (str(r.get("name", "")).lower(), str(r["id"])))
    return rows


def get_account(s: Scope, account_id: Any) -> dict:
    return s.get("accounts", account_id, what="Conta")


def require_usable_account(s: Scope, account_id: Any, *, field: str = "account_id") -> dict:
    """An account of THIS org that can take new money movements (active)."""
    row = s.require_owned("accounts", account_id, what="Conta", field=field)
    if not row.get("active", True):
        raise invalid(field, "A conta está inativa.", code=CONTA_INATIVA)
    return row


def _gateway_exists(s: Scope, gateway: str, *, except_id: Any = None) -> bool:
    for row in s.rows("accounts", eq={"kind": AccountKind.GATEWAY.value, "gateway": gateway}):
        if except_id is None or str(row["id"]) != str(except_id):
            return True
    return False


def create_account(s: Scope, data: Mapping[str, Any]) -> dict:
    row = _clean(data)
    kind = row.get("kind")
    if kind == AccountKind.GATEWAY.value:
        if not row.get("gateway"):
            raise invalid("gateway", "Informe o gateway da conta.")
        if _gateway_exists(s, row["gateway"]):
            raise conflict(CONTA_GATEWAY_DUPLICADA, "Já existe uma conta para este gateway.")
    else:
        row["gateway"] = None
    if row.get("accounting_code") is None:
        row.pop("accounting_code", None)  # E21 additive column: sent only when set
    now = now_iso()
    row.setdefault("opening_balance_cents", 0)
    row.setdefault("active", True)
    row.update(id=new_id(), org_id=s.org_id, created_at=now, updated_at=now)
    try:
        return first(s.tbl("accounts").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CONTA_GATEWAY_DUPLICADA, "Já existe uma conta para este gateway.") from exc
        raise


def get_or_create_gateway_account(s: Scope, gateway: str, *, name: Optional[str] = None) -> dict:
    """The org's account for `gateway` (idempotent -- the commerce bridge's destination)."""
    gateway = gateway.strip().lower()
    for row in s.rows("accounts", eq={"kind": AccountKind.GATEWAY.value, "gateway": gateway}):
        return row
    try:
        return create_account(
            s, {"kind": AccountKind.GATEWAY.value, "gateway": gateway, "name": name or gateway.capitalize()}
        )
    except Exception as exc:  # lost the create race: read the winner
        again = s.rows("accounts", eq={"kind": AccountKind.GATEWAY.value, "gateway": gateway})
        if again:
            return again[0]
        raise exc


def _has_ledger(s: Scope, account_id: Any) -> bool:
    resp = s.tbl(_LEDGER).select("id").eq("org_id", s.org_id).eq("account_id", str(account_id)).limit(1).execute()
    return bool(resp.data)


def update_account(s: Scope, account_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_account(s, account_id)
    patch = {k: v for k, v in _clean(data).items() if k != "kind"}
    if "name" in patch and not patch["name"]:
        raise invalid("name", "Informe o nome da conta.")
    if patch.get("active") is None:
        patch.pop("active", None)
    if "gateway" in patch and current["kind"] != AccountKind.GATEWAY.value:
        patch.pop("gateway")
    if "gateway" in patch:
        if not patch["gateway"]:
            raise invalid("gateway", "Informe o gateway da conta.")
        if _gateway_exists(s, patch["gateway"], except_id=account_id):
            raise conflict(CONTA_GATEWAY_DUPLICADA, "Já existe uma conta para este gateway.")
    for key in ("opening_balance_cents", "opening_date"):
        if key in patch and patch[key] != current.get(key) and _has_ledger(s, account_id):
            raise conflict(CONTA_COM_MOVIMENTO, "A conta já tem movimentações; o saldo inicial não pode mudar.")
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    try:
        s.tbl("accounts").update(patch).eq("org_id", s.org_id).eq("id", str(account_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CONTA_GATEWAY_DUPLICADA, "Já existe uma conta para este gateway.") from exc
        raise
    return {**current, **patch}


#: (table, column) pairs that reference an account (all FK ON DELETE RESTRICT).
_ACCOUNT_REFS = (
    ("entries", "expected_account_id"),
    ("settlements", "account_id"),
    ("ledger", "account_id"),
    ("statement_imports", "account_id"),
    ("statement_lines", "account_id"),
)


def _account_in_use(s: Scope, account_id: str) -> bool:
    for table, col in _ACCOUNT_REFS:
        resp = s.tbl(table).select("id").eq("org_id", s.org_id).eq(col, account_id).limit(1).execute()
        if resp.data:
            return True
    # recurrence templates carry the account inside JSON (no FK): a delete would leave the generator booking to a ghost
    return any(str((rec.get("template") or {}).get("expected_account_id") or "") == account_id for rec in s.rows("recurrences"))


def delete_account(s: Scope, account_id: Any) -> None:
    """Hard-delete an account nothing references (entries, settlements, transfers/ledger, statements, recurrences)."""
    get_account(s, account_id)
    msg = "A conta tem movimentações; desative-a."
    if _account_in_use(s, str(account_id)):
        raise conflict(CONTA_EM_USO, msg)
    try:
        s.tbl("accounts").delete().eq("org_id", s.org_id).eq("id", str(account_id)).execute()
    except Exception as exc:
        if is_foreign_key_violation(exc):
            raise conflict(CONTA_EM_USO, msg) from exc
        raise


def signed_ledger_cents(rows: list[dict]) -> int:
    return sum(
        int(r["amount_cents"]) if r["direction"] == LedgerDirection.IN.value else -int(r["amount_cents"])
        for r in rows
    )


def account_balance(s: Scope, account_id: Any, on: Optional[date] = None) -> dict:
    """Balance of the account on day `on` (default today): opening + the ledger up to and including `on`."""
    account = get_account(s, account_id)
    on = on or today()
    day = on.isoformat()
    rows = s.rows(_LEDGER, eq={"account_id": str(account_id)}, refine=lambda q: q.lte("occurred_on", day))
    opening_date = to_date(account.get("opening_date"))
    opening = int(account.get("opening_balance_cents") or 0) if opening_date is None or opening_date <= on else 0
    movement = signed_ledger_cents(rows)
    return {
        "account_id": str(account["id"]),
        "on": day,
        "opening_balance_cents": opening,
        "movement_cents": movement,
        "balance_cents": opening + movement,
    }


__all__ = [
    "account_balance",
    "create_account",
    "delete_account",
    "get_account",
    "get_or_create_gateway_account",
    "list_accounts",
    "require_usable_account",
    "signed_ledger_cents",
    "update_account",
]
