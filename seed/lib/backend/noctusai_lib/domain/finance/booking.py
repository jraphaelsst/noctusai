"""`FinanceBooking` -- the seam other organs (commerce, igig, ...) book money through.

Contract §3.5. Protocol + Fake + Real + factory (CLAUDE.md §1 seed IO rule):

- `SupabaseFinanceBooking(db, cfg)` -- the real one, over the org-scoped finance services;
- `NoopFinanceBooking` -- for products without finance (every call returns `None`);
- `FakeFinanceBooking` -- in-memory, records calls, same idempotency keys (tests of consumers);
- `make_finance_booking(kind=..., ...)` -- the factory.

All calls are IDEMPOTENT, so a retried webhook / re-run job never double-books:
`book_receivable` / `book_payable` on `(source, source_ref)`, `book_settlement` on `(kind, external_ref)`.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from ._common import Scope, iso, month_start, new_id
from .accounts import get_or_create_gateway_account, require_usable_account
from .categories import find_category_by_hint
from .config import FinanceConfig
from .entries import create_entry, find_by_source
from .errors import DOCUMENTO_INVALIDO, LANCAMENTO_DUPLICADO, FinanceError, invalid, not_found
from .settlements import find_settlement_by_ref, settle_entry
from .types import CategoryDirection, EntrySource, SettlementKind, values

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_HINT = "gateway:asaas"
#: The second settlement of a principal+interest split carries `<external_ref>:interest` (idempotent on its own).
INTEREST_REF_SUFFIX = ":interest"


@runtime_checkable
class FinanceBooking(Protocol):
    """What another organ may ask of finance. Sync, like the services behind it."""

    def book_receivable(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        description: str,
        counterparty_name: Optional[str],
        counterparty_doc: Optional[str],
        amount_cents: int,
        competence_month: date,
        due_date: date,
        category_hint: Optional[str] = None,
    ) -> Optional[str]:
        """Create (or find) the receivable for `(source, source_ref)`; returns its entry id."""
        ...

    def book_payable(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        description: str,
        counterparty_name: Optional[str],
        counterparty_doc: Optional[str],
        amount_cents: int,
        competence_month: date,
        due_date: date,
        category_hint: Optional[str] = None,
        party_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """Create (or find) the payable (AP) for `(source, source_ref)`; returns its entry id.

        `party_id` links the parties organ when the host mounts it (`FinanceConfig.with_parties`);
        `counterparty_*` stays a snapshot either way."""
        ...

    def book_settlement(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        kind: str,
        external_ref: str,
        amount_cents: int,
        fee_cents: int = 0,
        settled_on: date,
        account_hint: str = DEFAULT_ACCOUNT_HINT,
        interest_source_ref: Optional[str] = None,
    ) -> Optional[str]:
        """Settle the entry `(source, source_ref)`; idempotent on `(kind, external_ref)`; returns the settlement id.

        `interest_source_ref` (CONTRACT §10.5.3): when the order's installment interest is a SEPARATE receivable
        (`<order>:interest`), the amount is applied to the principal entry first and the overflow to the interest
        entry (a second settlement, `external_ref = <external_ref>:interest`) -- so a payment/refund of the whole
        charge never overshoots the principal. The fee rides on the first settlement written."""
        ...


class NoopFinanceBooking:
    """For products without finance: nothing is booked, nothing fails."""

    def book_receivable(self, org_id: str, **_: Any) -> Optional[str]:
        return None

    def book_payable(self, org_id: str, **_: Any) -> Optional[str]:
        return None

    def book_settlement(self, org_id: str, **_: Any) -> Optional[str]:
        return None


class FakeFinanceBooking:
    """In-memory booking with the real idempotency keys; `entries` / `settlements` expose what was booked."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str, str], dict] = {}
        self.settlements: dict[tuple[str, str, str], dict] = {}

    def book_receivable(self, org_id: str, *, source: str, source_ref: str, **fields: Any) -> Optional[str]:
        key = (str(org_id), source, source_ref)
        if key not in self.entries:
            self.entries[key] = {"id": new_id(), "org_id": str(org_id), "source": source, "source_ref": source_ref, **fields}
        return self.entries[key]["id"]

    def book_payable(self, org_id: str, *, source: str, source_ref: str, **fields: Any) -> Optional[str]:
        key = (str(org_id), source, source_ref)
        if key not in self.entries:
            self.entries[key] = {"id": new_id(), "org_id": str(org_id), "source": source, "source_ref": source_ref,
                                 "direction": "payable", **fields}
        return self.entries[key]["id"]

    def book_settlement(self, org_id: str, *, source: str, source_ref: str, kind: str, external_ref: str, **fields: Any) -> Optional[str]:
        # The real seam splits across principal + interest; the fake only records the key (its consumers assert calls).
        if (str(org_id), source, source_ref) not in self.entries:
            raise not_found("Lançamento")
        key = (str(org_id), kind, external_ref)
        if key not in self.settlements:
            self.settlements[key] = {"id": new_id(), "org_id": str(org_id), "source": source, "source_ref": source_ref,
                                     "kind": kind, "external_ref": external_ref, **fields}
        return self.settlements[key]["id"]


class SupabaseFinanceBooking:
    """The real seam: books through the org-scoped finance services on a schema-scoped PostgREST client."""

    def __init__(self, db: Any, cfg: FinanceConfig) -> None:
        self._db = db
        self._cfg = cfg

    def _scope(self, org_id: str) -> Scope:
        return Scope(self._db, self._cfg, str(org_id))

    def book_receivable(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        description: str,
        counterparty_name: Optional[str],
        counterparty_doc: Optional[str],
        amount_cents: int,
        competence_month: date,
        due_date: date,
        category_hint: Optional[str] = None,
    ) -> Optional[str]:
        s = self._scope(org_id)
        if source not in values(EntrySource):
            raise invalid("source", "Origem inválida.")
        if not source_ref:
            raise invalid("source_ref", "A referência de origem é obrigatória para lançamentos automáticos.")
        existing = find_by_source(s, source, source_ref)
        if existing is not None:
            return str(existing["id"])
        data = {
            "direction": "receivable",
            "source": source,
            "source_ref": source_ref,
            "description": description,
            "counterparty_name": counterparty_name,
            "counterparty_doc": counterparty_doc,
            "amount_cents": amount_cents,
            "competence_month": month_start(competence_month),
            "due_date": due_date,
            "category_id": find_category_by_hint(s, category_hint, CategoryDirection.INCOME),
        }
        try:
            return self._create(s, data)
        except FinanceError as exc:
            if exc.code != DOCUMENTO_INVALIDO:
                raise
            # A bridge must not lose a receivable over a malformed buyer document.
            logger.warning("finance booking: invalid counterparty_doc for %s/%s; booked without it", source, source_ref)
            return self._create(s, {**data, "counterparty_doc": None})

    def book_payable(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        description: str,
        counterparty_name: Optional[str],
        counterparty_doc: Optional[str],
        amount_cents: int,
        competence_month: date,
        due_date: date,
        category_hint: Optional[str] = None,
        party_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        s = self._scope(org_id)
        if source not in values(EntrySource):
            raise invalid("source", "Origem inválida.")
        if not source_ref:
            raise invalid("source_ref", "A referência de origem é obrigatória para lançamentos automáticos.")
        existing = find_by_source(s, source, source_ref)
        if existing is not None:
            return str(existing["id"])
        data = {
            "direction": "payable",
            "source": source,
            "source_ref": source_ref,
            "description": description,
            "counterparty_name": counterparty_name,
            "counterparty_doc": counterparty_doc,
            "amount_cents": amount_cents,
            "competence_month": month_start(competence_month),
            "due_date": due_date,
            "category_id": find_category_by_hint(s, category_hint, CategoryDirection.EXPENSE),
            "party_id": party_id if self._cfg.with_parties else None,
            "notes": notes,
        }
        try:
            return self._create(s, data)
        except FinanceError as exc:
            if exc.code != DOCUMENTO_INVALIDO:
                raise
            logger.warning("finance booking: invalid counterparty_doc for %s/%s; booked without it", source, source_ref)
            return self._create(s, {**data, "counterparty_doc": None})

    @staticmethod
    def _create(s: Scope, data: dict) -> str:
        try:
            return str(create_entry(s, data)[0]["id"])
        except FinanceError as exc:
            if exc.code != LANCAMENTO_DUPLICADO:
                raise
            # A concurrent delivery created it between our lookup and insert: that one wins.
            winner = find_by_source(s, data["source"], data["source_ref"])
            if winner is None:
                raise
            return str(winner["id"])

    def _account(self, s: Scope, hint: str) -> dict:
        kind, _, value = (hint or DEFAULT_ACCOUNT_HINT).partition(":")
        if kind == "gateway" and value:
            return get_or_create_gateway_account(s, value)
        if kind == "account" and value:
            return require_usable_account(s, value, field="account_hint")
        raise invalid("account_hint", "Dica de conta inválida (use gateway:<nome> ou account:<id>).")

    def book_settlement(
        self,
        org_id: str,
        *,
        source: str,
        source_ref: str,
        kind: str,
        external_ref: str,
        amount_cents: int,
        fee_cents: int = 0,
        settled_on: date,
        account_hint: str = DEFAULT_ACCOUNT_HINT,
        interest_source_ref: Optional[str] = None,
    ) -> Optional[str]:
        s = self._scope(org_id)
        if kind not in values(SettlementKind):
            raise invalid("kind", "Tipo de baixa inválido.")
        if not external_ref:
            raise invalid("external_ref", "A referência externa é obrigatória para baixas automáticas.")
        entry = find_by_source(s, source, source_ref)
        if entry is None:
            raise not_found("Lançamento")
        account = self._account(s, account_hint)

        def settle(target: dict, ref: str, amount: int, fee: int) -> str:
            result = settle_entry(
                s,
                target["id"],
                {
                    "account_id": account["id"],
                    "kind": kind,
                    "settled_on": iso(settled_on),
                    "amount_cents": amount,
                    "fee_cents": fee,
                    "external_ref": ref,
                    "method": account_hint,
                },
            )
            return str(result["settlement"]["id"])

        interest_entry = find_by_source(s, source, interest_source_ref) if interest_source_ref else None
        if interest_entry is None:
            return settle(entry, external_ref, amount_cents, fee_cents)

        interest_ref = f"{external_ref}{INTEREST_REF_SUFFIX}"
        done_main = find_settlement_by_ref(s, kind, external_ref)
        done_interest = find_settlement_by_ref(s, kind, interest_ref)
        if done_main is not None:  # a replay (or a half-finished first run): the split is already decided
            main_part = int(done_main["amount_cents"])
        elif done_interest is not None:
            main_part = amount_cents - int(done_interest["amount_cents"])
        elif kind == SettlementKind.PAYMENT.value:
            main_part = min(amount_cents, max(int(entry["amount_cents"]) - int(entry.get("settled_cents") or 0), 0))
        else:  # a refund returns principal first, then interest
            main_part = min(amount_cents, int(entry.get("settled_cents") or 0))
        interest_part = amount_cents - main_part
        main_id = interest_id = None
        if main_part > 0:
            main_id = settle(entry, external_ref, main_part, fee_cents)
        if interest_part > 0:
            interest_id = settle(interest_entry, interest_ref, interest_part, fee_cents if main_part == 0 else 0)
        return main_id or interest_id


def make_finance_booking(
    kind: Literal["noop", "fake", "supabase"] = "noop",
    *,
    db: Any = None,
    cfg: Optional[FinanceConfig] = None,
) -> FinanceBooking:
    """Build a `FinanceBooking`. `supabase` needs `db` (schema-scoped PostgREST client) and `cfg`."""
    if kind == "noop":
        return NoopFinanceBooking()
    if kind == "fake":
        return FakeFinanceBooking()
    if kind == "supabase":
        if db is None or cfg is None:
            raise ValueError("make_finance_booking(kind='supabase') requires db= and cfg=")
        return SupabaseFinanceBooking(db, cfg)
    raise ValueError(f"unknown finance booking kind {kind!r}")


__all__ = [
    "DEFAULT_ACCOUNT_HINT",
    "INTEREST_REF_SUFFIX",
    "FakeFinanceBooking",
    "FinanceBooking",
    "NoopFinanceBooking",
    "SupabaseFinanceBooking",
    "make_finance_booking",
]
