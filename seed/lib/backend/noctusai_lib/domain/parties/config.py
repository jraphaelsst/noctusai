"""`PartiesConfig` -- everything that differs between two parties hosts.

Mirrors `FinanceConfig` / `CommerceConfig` on purpose (one answer for "which org does this row
belong to" across organs): `schema`, `table_prefix`, `org_id_expr`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class PartiesConfig:
    """One parties host's knobs.

    Attributes:
        schema: the product's Postgres schema (and the PostgREST schema `get_db` is scoped to).
        table_prefix: prefix of every organ table (`pty_` => `pty_parties`).
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to.
            Unset => `public.current_org_id_for('<schema>')` (same default as finance/commerce).
        reference_tables: `(physical_table, party_id_column)` pairs of OTHER organs' tables that
            point at a party. A party referenced from any of them is never hard-deleted (409
            `parceiro_em_uso`; archive it instead). Empty until a linking organ is mounted --
            e.g. `(("fin_entries", "party_id"),)` once finance carries the link.
    """

    schema: str
    table_prefix: str = "pty_"
    org_id_expr: Optional[str] = None
    reference_tables: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _IDENT.match(self.schema or ""):
            raise ValueError(f"PartiesConfig.schema must be a bare lowercase identifier, got {self.schema!r}")
        if not _IDENT.match(self.table_prefix or ""):
            raise ValueError(f"PartiesConfig.table_prefix must be a bare lowercase identifier, got {self.table_prefix!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("PartiesConfig.org_id_expr must be a non-empty SQL expression (or unset)")
        for table, column in self.reference_tables:
            if not _IDENT.match(table or "") or not _IDENT.match(column or ""):
                raise ValueError(f"PartiesConfig.reference_tables entry must be bare identifiers, got {(table, column)!r}")

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`parties` -> `pty_parties`)."""
        return f"{self.table_prefix}{name}"


@dataclass(frozen=True)
class PartiesContext:
    """What every handler needs, resolved by the host's `resolve_context`.

    `is_admin` is decided SERVER-SIDE (the host's trusted org-role resolver) and only drives LGPD
    masking on reads; write authorization is the router's `admin_dependency`.
    """

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["PartiesConfig", "PartiesContext"]
