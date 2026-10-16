"""`ContractsConfig` -- everything that differs between two contracts hosts.

Mirrors `FinanceConfig` / `PartiesConfig` (`schema`, `table_prefix`, `org_id_expr`) plus the link
switches: a host that mounts the parties / items organs turns the composite FKs on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

MAX_SIGNED_URL_TTL_SECONDS = 600


@dataclass(frozen=True)
class ContractsConfig:
    """One contracts host's knobs.

    Attributes:
        schema / table_prefix / org_id_expr: as in the sibling organs (`ctr_` => `ctr_contracts`).
        with_parties: emit the composite FK `(party_id, org_id)` -> `<parties_table>` and verify a
            party belongs to the caller's org on write. Off => `party_id` is a plain nullable UUID.
        with_items: same for `ctr_contract_lines.item_id` -> `<items_table>(org_id, id)`.
        finance_entries_table: the finance organ's entries table. When set, the migration widens its
            `source` CHECK to admit `'contracts'` (guarded: a no-op while the table does not exist).
            None => the host has no finance organ (billing then needs a custom `ContractsBilling`).
        receivable_category / service_category: finance category NAMES (`find_category_by_hint`) used
            for periodic vs one-off billing. Defaults are the DRE starter tree's (dre-structure.md §2a).
        billing_lead_days: the job books a receivable this many days BEFORE it is due.
        bucket: PRIVATE storage bucket for attachments (`<org>/contracts/<contract>/<att>.<ext>`).
        party_resolver: the named seam for a host WITHOUT the parties organ whose customers live in its own table
            (`with_parties=False`, `party_id` = that table's id): `(db, org_id, party_id) -> {"party_name", "party_doc"}`, or
            None when the id is not a customer of `org_id` (the contract is then refused `parte_invalida`). Without it a
            `party_id` stays an unverified, unsnapshotted UUID. Ignored when `with_parties` is on.
    """

    schema: str
    table_prefix: str = "ctr_"
    org_id_expr: Optional[str] = None
    with_parties: bool = False
    parties_table: str = "pty_parties"
    with_items: bool = False
    items_table: str = "itm_items"
    finance_entries_table: Optional[str] = "fin_entries"
    receivable_category: str = "Mensalidades"
    service_category: str = "Serviços"
    billing_lead_days: int = 30
    bucket: str = "contract-attachments"
    signed_url_ttl_seconds: int = MAX_SIGNED_URL_TTL_SECONDS
    party_resolver: Optional[Callable[[Any, str, str], Optional[Mapping[str, Any]]]] = None

    def __post_init__(self) -> None:
        for label, val in (("schema", self.schema), ("table_prefix", self.table_prefix),
                           ("parties_table", self.parties_table), ("items_table", self.items_table)):
            if not _IDENT.match(val or ""):
                raise ValueError(f"ContractsConfig.{label} must be a bare lowercase identifier, got {val!r}")
        if self.finance_entries_table is not None and not _IDENT.match(self.finance_entries_table):
            raise ValueError(f"ContractsConfig.finance_entries_table must be a bare identifier, got {self.finance_entries_table!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("ContractsConfig.org_id_expr must be a non-empty SQL expression (or unset)")
        if not 0 <= self.billing_lead_days <= 365:
            raise ValueError("ContractsConfig.billing_lead_days must be within 0..365")
        if not _BUCKET.match(self.bucket or ""):
            raise ValueError(f"ContractsConfig.bucket must be a bucket id, got {self.bucket!r}")
        if not 1 <= self.signed_url_ttl_seconds <= MAX_SIGNED_URL_TTL_SECONDS:
            raise ValueError(f"ContractsConfig.signed_url_ttl_seconds must be within 1..{MAX_SIGNED_URL_TTL_SECONDS}")

    def table(self, name: str) -> str:
        """The physical table name of organ table `name` (`contracts` -> `ctr_contracts`)."""
        return f"{self.table_prefix}{name}"


@dataclass(frozen=True)
class ContractsContext:
    """What every handler needs, resolved by the host's `resolve_context` (`is_admin` is server-decided)."""

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["ContractsConfig", "ContractsContext", "MAX_SIGNED_URL_TTL_SECONDS"]
