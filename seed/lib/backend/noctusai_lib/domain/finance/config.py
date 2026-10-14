"""`FinanceConfig` -- everything that differs between two finance hosts.

The mechanics (accounts, entries, settlements, ledger, reports) are identical
for every product; only these knobs differ. Mirrors `CommerceConfig`'s
`org_id_expr` mechanism on purpose (one answer for "which org does this row
belong to" across organs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

#: Contract §3.4: a download link lives at most 10 minutes.
MAX_SIGNED_URL_TTL_SECONDS = 600


@dataclass(frozen=True)
class FinanceConfig:
    """One finance host's knobs.

    Attributes:
        schema: the product's Postgres schema (and the PostgREST schema the
            router's `get_db` client is scoped to).
        table_prefix: prefix of every organ table (`fin_` => `fin_entries`).
            Part of the DB contract; a host overrides it only to coexist with a
            legacy `fin_*` table of its own.
        bucket: PRIVATE storage bucket for attachments; keys are
            `<org_id>/entries/<entry_id>/<attachment_id>.<ext>`.
        signed_url_ttl_seconds: attachment signed-URL lifetime (capped at 10 min).
        org_id_expr: SQL expression the authenticated own-org policies compare
            `org_id` to. Unset => `public.current_org_id_for('<schema>')` (the
            home org for everyone, the SELECTED org while platform staff act
            through the org picker) -- same default as `CommerceConfig`.
        with_parties: the `parties` organ is mounted in the same schema. Adds the nullable
            `fin_entries.party_id` (composite FK `(party_id, org_id)` -> `<parties_prefix>parties`);
            `counterparty_*` stays a SNAPSHOT of the party at booking time (roadmap E4).
        parties_prefix: table prefix of the `parties` organ (`pty_`).
    """

    schema: str
    table_prefix: str = "fin_"
    bucket: str = "finance-attachments"
    signed_url_ttl_seconds: int = MAX_SIGNED_URL_TTL_SECONDS
    org_id_expr: Optional[str] = None
    with_parties: bool = False
    parties_prefix: str = "pty_"

    def __post_init__(self) -> None:
        if not _IDENT.match(self.schema or ""):
            raise ValueError(f"FinanceConfig.schema must be a bare lowercase identifier, got {self.schema!r}")
        if not _IDENT.match(self.table_prefix or ""):
            raise ValueError(f"FinanceConfig.table_prefix must be a bare lowercase identifier, got {self.table_prefix!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("FinanceConfig.org_id_expr must be a non-empty SQL expression (or unset)")
        if not _IDENT.match(self.parties_prefix or ""):
            raise ValueError(f"FinanceConfig.parties_prefix must be a bare lowercase identifier, got {self.parties_prefix!r}")
        if not _BUCKET.match(self.bucket or ""):
            raise ValueError(f"FinanceConfig.bucket must be a bucket id, got {self.bucket!r}")
        if not 1 <= self.signed_url_ttl_seconds <= MAX_SIGNED_URL_TTL_SECONDS:
            raise ValueError(f"FinanceConfig.signed_url_ttl_seconds must be within 1..{MAX_SIGNED_URL_TTL_SECONDS}")

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`entries` -> `fin_entries`)."""
        return f"{self.table_prefix}{name}"

    @property
    def parties_table(self) -> str:
        return f"{self.parties_prefix}parties"


@dataclass(frozen=True)
class FinanceContext:
    """What every handler needs, resolved by the host's `resolve_context`.

    `is_admin` is decided SERVER-SIDE (the host's trusted org-role resolver) and
    only drives LGPD masking on reads; write authorization is the router's
    `admin_dependency`.
    """

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["FinanceConfig", "FinanceContext", "MAX_SIGNED_URL_TTL_SECONDS"]
