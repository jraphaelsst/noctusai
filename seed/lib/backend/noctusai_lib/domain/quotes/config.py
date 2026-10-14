"""`QuotesConfig` -- everything that differs between two quote hosts.

Same `org_id_expr` mechanism as `PartiesConfig` / `InventoryConfig`. The cross-organ FKs are opt-out:
`with_parties` emits the composite FK `(party_id, org_id) -> <parties_prefix>parties(id, org_id)` and
`with_items` emits `item_id -> <items_prefix>items(id)`, each only valid when that organ is mounted in the
SAME schema (roadmap E8). A host without one keeps the column as an opaque uuid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_NUMBER_PREFIX = re.compile(r"^[A-Za-z0-9._-]{0,12}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class QuotesConfig:
    """One quotes host's knobs.

    Attributes:
        schema: the product's Postgres schema.
        table_prefix: prefix of every organ table (`quo_` => `quo_quotes`) and RPC.
        with_parties / parties_prefix: composite FK to the parties organ's table.
        with_items / items_prefix: FK to the items organ's table (lines may name an item).
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to.
            Unset => `public.current_org_id_for('<schema>')`.
        number_prefix / number_pad: the human number, `ORC-00042` (one sequence per org; versions share it).
        currency: ISO-4217 code stored on each quote (money is always integer minor units).
        default_valid_days: validity of a quote created / revised without an explicit `valid_until`.
        link_ttl_days: lifetime of the public accept link (capped at the end of the validity day).
        utc_offset_hours: the org's civil-day offset used for "today" / validity (Brazil: -3, no DST).
        public_rate_limit / decision_rate_limit: slowapi-style limit strings for the public routes.
    """

    schema: str
    table_prefix: str = "quo_"
    with_parties: bool = True
    parties_prefix: str = "pty_"
    with_items: bool = True
    items_prefix: str = "itm_"
    org_id_expr: Optional[str] = None
    number_prefix: str = "ORC-"
    number_pad: int = 5
    currency: str = "BRL"
    default_valid_days: int = 15
    link_ttl_days: int = 30
    utc_offset_hours: int = -3
    public_rate_limit: str = "60/minute"
    decision_rate_limit: str = "10/minute"

    def __post_init__(self) -> None:
        for label, value in (
            ("schema", self.schema),
            ("table_prefix", self.table_prefix),
            ("parties_prefix", self.parties_prefix),
            ("items_prefix", self.items_prefix),
        ):
            if not _IDENT.match(value or ""):
                raise ValueError(f"QuotesConfig.{label} must be a bare lowercase identifier, got {value!r}")
        if not _NUMBER_PREFIX.match(self.number_prefix):
            raise ValueError(f"QuotesConfig.number_prefix must be <=12 chars of [A-Za-z0-9._-], got {self.number_prefix!r}")
        if not _CURRENCY.match(self.currency):
            raise ValueError(f"QuotesConfig.currency must be an ISO-4217 code, got {self.currency!r}")
        if not 1 <= self.number_pad <= 12:
            raise ValueError("QuotesConfig.number_pad must be between 1 and 12")
        if self.default_valid_days < 1 or self.link_ttl_days < 1:
            raise ValueError("QuotesConfig.default_valid_days / link_ttl_days must be >= 1")
        if not -12 <= self.utc_offset_hours <= 14:
            raise ValueError("QuotesConfig.utc_offset_hours must be a real UTC offset")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("QuotesConfig.org_id_expr must be a non-empty SQL expression (or unset)")

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`quotes` -> `quo_quotes`)."""
        return f"{self.table_prefix}{name}"

    def rpc(self, name: str) -> str:
        return f"{self.table_prefix}{name}"

    @property
    def parties_table(self) -> str:
        return f"{self.parties_prefix}parties"

    @property
    def items_table(self) -> str:
        return f"{self.items_prefix}items"

    @property
    def tz(self) -> timezone:
        return timezone(timedelta(hours=self.utc_offset_hours))

    def format_number(self, n: int) -> str:
        return f"{self.number_prefix}{int(n):0{self.number_pad}d}"


@dataclass(frozen=True)
class QuotesContext:
    """What every handler needs, resolved by the host's `resolve_context`."""

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["QuotesConfig", "QuotesContext"]
