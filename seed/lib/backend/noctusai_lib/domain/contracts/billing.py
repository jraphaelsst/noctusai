"""`ContractsBilling` -- the seam contracts book receivables through (Protocol + Fake + Real + factory).

- `SupabaseContractsBilling(db, finance_cfg)` -- the real one, over the org-scoped finance services
  (`FinanceBooking.book_receivable` for the idempotent book; finance `cancel_entry` for the cancel);
- `FakeContractsBilling` -- in-memory with the SAME idempotency key `(org, source_ref)` (tests of consumers);
- `NoopContractsBilling` -- a host without finance: nothing is booked (the contract still tracks the schedule);
- `make_contracts_billing(kind=...)` -- the factory.

Every receivable carries `source='contracts'` and `source_ref = <contract_id>:<period_key>[:<kind>]`,
so a re-run job / retried request never double-books.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from noctusai_lib.domain.finance._common import Scope as FinanceScope
from noctusai_lib.domain.finance.booking import SupabaseFinanceBooking
from noctusai_lib.domain.finance.config import FinanceConfig
from noctusai_lib.domain.finance.entries import cancel_entry, find_by_source
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.types import EntrySource

from ._common import new_id

logger = logging.getLogger(__name__)

SOURCE = EntrySource.CONTRACTS.value

#: `cancel_receivable` outcomes.
CANCELLED = "cancelled"
KEPT_SETTLED = "kept_settled"
MISSING = "missing"


@runtime_checkable
class ContractsBilling(Protocol):
    def book_receivable(
        self, org_id: str, *, source_ref: str, description: str, counterparty_name: Optional[str],
        counterparty_doc: Optional[str], amount_cents: int, competence_month: date, due_date: date,
        category_hint: Optional[str] = None,
    ) -> Optional[str]:
        """Create (or find) the receivable `(contracts, source_ref)`; returns its entry id (None: no finance)."""
        ...

    def cancel_receivable(self, org_id: str, *, source_ref: str) -> str:
        """Cancel the receivable if it has no settlements: `cancelled` | `kept_settled` | `missing`."""
        ...


class NoopContractsBilling:
    def book_receivable(self, org_id: str, **_: Any) -> Optional[str]:
        return None

    def cancel_receivable(self, org_id: str, **_: Any) -> str:
        return MISSING


class FakeContractsBilling:
    """In-memory; `entries` is keyed `(org, source_ref)` and a `settled` set simulates a paid entry."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], dict] = {}
        self.settled: set[tuple[str, str]] = set()

    def book_receivable(self, org_id: str, *, source_ref: str, **fields: Any) -> Optional[str]:
        key = (str(org_id), source_ref)
        if key not in self.entries:
            self.entries[key] = {"id": new_id(), "org_id": str(org_id), "source": SOURCE, "source_ref": source_ref,
                                 "status": "open", **fields}
        return self.entries[key]["id"]

    def cancel_receivable(self, org_id: str, *, source_ref: str) -> str:
        key = (str(org_id), source_ref)
        if key not in self.entries:
            return MISSING
        if key in self.settled:
            return KEPT_SETTLED
        self.entries[key]["status"] = "cancelled"
        return CANCELLED


class SupabaseContractsBilling:
    def __init__(self, db: Any, finance_cfg: FinanceConfig) -> None:
        self._db = db
        self._cfg = finance_cfg
        self._booking = SupabaseFinanceBooking(db, finance_cfg)

    def book_receivable(self, org_id: str, *, source_ref: str, description: str, counterparty_name: Optional[str],
                        counterparty_doc: Optional[str], amount_cents: int, competence_month: date, due_date: date,
                        category_hint: Optional[str] = None) -> Optional[str]:
        return self._booking.book_receivable(
            org_id, source=SOURCE, source_ref=source_ref, description=description, counterparty_name=counterparty_name,
            counterparty_doc=counterparty_doc, amount_cents=amount_cents, competence_month=competence_month,
            due_date=due_date, category_hint=category_hint,
        )

    def cancel_receivable(self, org_id: str, *, source_ref: str) -> str:
        s = FinanceScope(self._db, self._cfg, str(org_id))
        entry = find_by_source(s, SOURCE, source_ref)
        if entry is None:
            return MISSING
        try:
            cancel_entry(s, entry["id"])
        except FinanceError as exc:
            logger.info("contracts billing: %s kept (%s)", source_ref, exc.code)
            return KEPT_SETTLED
        return CANCELLED


def make_contracts_billing(kind: Literal["noop", "fake", "supabase"] = "noop", *, db: Any = None,
                           finance_cfg: Optional[FinanceConfig] = None) -> ContractsBilling:
    """Build a `ContractsBilling`. `supabase` needs `db` (schema-scoped client) and `finance_cfg`."""
    if kind == "noop":
        return NoopContractsBilling()
    if kind == "fake":
        return FakeContractsBilling()
    if kind == "supabase":
        if db is None or finance_cfg is None:
            raise ValueError("make_contracts_billing('supabase') needs db= and finance_cfg=")
        return SupabaseContractsBilling(db, finance_cfg)
    raise ValueError(f"unknown contracts billing kind {kind!r}")


__all__ = ["CANCELLED", "KEPT_SETTLED", "MISSING", "SOURCE", "ContractsBilling", "FakeContractsBilling",
           "NoopContractsBilling", "SupabaseContractsBilling", "make_contracts_billing"]
