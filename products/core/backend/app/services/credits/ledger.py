"""The credit ledger seam — every credit movement goes through `CreditLedger.apply`.

Real: `RpcCreditLedger` calls ``public.credit_apply_entry`` (migration 093) — a
SECURITY DEFINER function that, in ONE transaction under a per-org advisory
lock, dedups (ai_usage_id / payment ref), appends the entry, moves the
balance, advances the 50/80/100% alert state and stamps
``ai_usage.charged_credits``. Purchases, admin grants, adjustments, refunds
and usage debits all take this one path — a grant is distinguishable only by
``kind='grant'`` + ``source``, exactly as the owner asked (a testing ground
for the real money flow).

Fake: `FakeCreditLedger` reproduces the function's CONTRACT over table calls
on a `MockSupabaseClient`, so router/service tests read back the wallet the
way production would. It has no lock and no transaction — tests only. The
SQL itself is proven by `noctus.dev.verify_db_guards` (credit_* probes) and
`tests/test_migration_093_credit_wallets.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Protocol

APPLY_RPC = "credit_apply_entry"
KINDS = ("purchase", "grant", "adjustment", "usage_debit", "refund")


@dataclass(frozen=True)
class CreditEntryInput:
    org_id: str
    kind: str
    credits: Decimal
    source: str
    product: Optional[str] = None
    feature: Optional[str] = None
    brl_amount: Optional[Decimal] = None
    usd_amount: Optional[Decimal] = None
    provider_cost_brl: Optional[Decimal] = None
    fx_rate: Optional[Decimal] = None
    pricing_version: Optional[int] = None
    ai_usage_id: Optional[int] = None
    payment_ref: Optional[str] = None
    reason: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)
    created_by: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown credit entry kind {self.kind!r}")

    def rpc_params(self) -> dict[str, Any]:
        num = lambda v: None if v is None else str(v)  # noqa: E731 — numeric travels as text (exact)
        return {
            "p_org_id": self.org_id,
            "p_kind": self.kind,
            "p_credits": num(self.credits),
            "p_source": self.source,
            "p_product": self.product,
            "p_feature": self.feature,
            "p_brl_amount": num(self.brl_amount),
            "p_usd_amount": num(self.usd_amount),
            "p_provider_cost_brl": num(self.provider_cost_brl),
            "p_fx_rate": num(self.fx_rate),
            "p_pricing_version": self.pricing_version,
            "p_ai_usage_id": self.ai_usage_id,
            "p_payment_ref": self.payment_ref,
            "p_reason": self.reason,
            "p_detail": self.detail or {},
            "p_created_by": self.created_by,
        }


@dataclass(frozen=True)
class ApplyResult:
    status: str  # applied | duplicate | already_charged
    entry_id: Optional[int] = None
    balance_credits: Optional[Decimal] = None
    alert_threshold: Optional[Decimal] = None
    alert_base_credits: Optional[Decimal] = None
    mode: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Any) -> "ApplyResult":
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        if isinstance(payload, dict) and APPLY_RPC in payload and len(payload) == 1:
            payload = payload[APPLY_RPC]
        if not isinstance(payload, dict) or "status" not in payload:
            raise RuntimeError(f"{APPLY_RPC} returned an unexpected payload: {payload!r}")
        dec = lambda k: None if payload.get(k) is None else Decimal(str(payload[k]))  # noqa: E731
        return cls(
            status=str(payload["status"]),
            entry_id=payload.get("entry_id"),
            balance_credits=dec("balance_credits"),
            alert_threshold=dec("alert_threshold"),
            alert_base_credits=dec("alert_base_credits"),
            mode=payload.get("mode"),
        )


class CreditLedger(Protocol):
    def apply(self, entry: CreditEntryInput) -> ApplyResult: ...


class RpcCreditLedger:
    """Production: one RPC, one transaction (migration 093)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def apply(self, entry: CreditEntryInput) -> ApplyResult:
        return ApplyResult.from_payload(self._db.rpc(APPLY_RPC, entry.rpc_params()).execute().data)


class FakeCreditLedger:
    """Tests only — the `credit_apply_entry` contract over table calls (no lock)."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self.applied: list[CreditEntryInput] = []

    def _one(self, table: str, **eq: Any) -> Optional[dict[str, Any]]:
        q = self._db.table(table).select("*")
        for k, v in eq.items():
            q = q.eq(k, v)
        rows = q.limit(1).execute().data or []
        return rows[0] if rows else None

    def apply(self, entry: CreditEntryInput) -> ApplyResult:
        if entry.ai_usage_id is not None:
            usage = self._one("ai_usage", id=entry.ai_usage_id)
            if usage is None:
                raise RuntimeError(f"credit_apply_entry: ai_usage {entry.ai_usage_id} not found")
            if str(usage.get("org_id")) != str(entry.org_id):
                raise RuntimeError(f"credit_apply_entry: ai_usage {entry.ai_usage_id} belongs to another org")
            dup = self._one("credit_entries", ai_usage_id=entry.ai_usage_id)
            if dup:
                return ApplyResult("duplicate", dup["id"], Decimal(str(dup["balance_after"])))
            if usage.get("charged_credits") is not None:
                return ApplyResult("already_charged")
        if entry.payment_ref is not None:
            dup = self._one("credit_entries", kind=entry.kind, payment_ref=entry.payment_ref)
            if dup:
                return ApplyResult("duplicate", dup["id"], Decimal(str(dup["balance_after"])))
        credits = Decimal(str(entry.credits))
        sign_ok = {
            "purchase": credits > 0, "grant": credits > 0, "usage_debit": credits <= 0,
            "refund": credits < 0, "adjustment": credits != 0,
        }[entry.kind]
        if not sign_ok:
            raise RuntimeError('new row violates check constraint "credit_entries_sign"')

        defaults = {
            "org_id": entry.org_id, "mode": "prepaid", "balance_credits": 0,
            "overdraft_limit_credits": 0, "alert_thresholds": [0.5, 0.8, 1.0],
            "alert_base_credits": 0, "last_alert_threshold": 0,
            "charge_from": datetime.now(timezone.utc).isoformat(),
        }
        found = self._one("credit_wallets", org_id=entry.org_id)
        if found is None:
            wallet = defaults
            self._db.table("credit_wallets").insert(wallet).execute()
        else:  # a mock row carries no column DEFAULTs; Postgres would
            wallet = {**defaults, **{k: v for k, v in found.items() if v is not None}}
        balance = Decimal(str(wallet["balance_credits"])) + credits
        base = Decimal(str(wallet.get("alert_base_credits") or 0))
        last = Decimal(str(wallet.get("last_alert_threshold") or 0))
        threshold: Optional[Decimal] = None
        if entry.kind in ("purchase", "grant"):
            base, last = max(balance, Decimal(0)), Decimal(0)
        elif credits < 0 and base > 0:
            consumed = (base - balance) / base
            for t in (Decimal(str(x)) for x in wallet.get("alert_thresholds") or []):
                if consumed >= t and t > last:
                    threshold = max(threshold or Decimal(0), t)
            if threshold is not None:
                last = threshold

        existing = self._db.table("credit_entries").select("id").execute().data or []
        entry_id = max((int(r["id"]) for r in existing), default=0) + 1
        row = {
            "id": entry_id, "org_id": entry.org_id, "product": entry.product, "feature": entry.feature,
            "kind": entry.kind, "source": entry.source, "credits": float(credits),
            "balance_after": float(balance),
            "brl_amount": None if entry.brl_amount is None else float(entry.brl_amount),
            "usd_amount": None if entry.usd_amount is None else float(entry.usd_amount),
            "provider_cost_brl": None if entry.provider_cost_brl is None else float(entry.provider_cost_brl),
            "fx_rate": None if entry.fx_rate is None else float(entry.fx_rate),
            "pricing_version": entry.pricing_version, "ai_usage_id": entry.ai_usage_id,
            "payment_ref": entry.payment_ref, "reason": entry.reason, "detail": entry.detail or {},
            "created_by": entry.created_by, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._db.table("credit_entries").insert(row).execute()
        self._db.table("credit_wallets").update({
            "balance_credits": float(balance), "alert_base_credits": float(base),
            "last_alert_threshold": float(last),
        }).eq("org_id", entry.org_id).execute()
        if entry.ai_usage_id is not None:
            self._db.table("ai_usage").update({"charged_credits": float(-credits)}).eq(
                "id", entry.ai_usage_id).execute()
        self.applied.append(entry)
        return ApplyResult("applied", entry_id, balance, threshold, base, wallet.get("mode"))


__all__ = [
    "APPLY_RPC",
    "ApplyResult",
    "CreditEntryInput",
    "CreditLedger",
    "FakeCreditLedger",
    "RpcCreditLedger",
]
