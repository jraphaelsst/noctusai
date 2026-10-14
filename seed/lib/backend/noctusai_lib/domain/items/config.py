"""`ItemsConfig` -- everything that differs between two items hosts.

Mirrors `FinanceConfig` / `CommerceConfig` on purpose: one `org_id_expr` answer for
"which org does this row belong to" across organs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .types import ItemType, values

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class ItemsConfig:
    """One items host's knobs.

    Attributes:
        schema: the product's Postgres schema (and the PostgREST schema `get_db` is scoped to).
        table_prefix: prefix of every organ table (`itm_` => `itm_items`). Part of the DB contract.
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to. Unset =>
            `public.current_org_id_for('<schema>')` (home org; the SELECTED org while platform staff act
            through the org picker) -- the same default as finance / commerce.
        extra_item_types: the VERTICAL-SEED SEAM for `item_type`. The seed ships
            goods | service | raw_material | asset; a vertical (e.g. a clinic: `procedure`, a bakery:
            `recipe`) adds snake_case values here and they join the CHECK constraint and the validated set.
            Removing/renaming a SEED value is never a config matter.
    """

    schema: str
    table_prefix: str = "itm_"
    org_id_expr: Optional[str] = None
    extra_item_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _IDENT.match(self.schema or ""):
            raise ValueError(f"ItemsConfig.schema must be a bare lowercase identifier, got {self.schema!r}")
        if not _IDENT.match(self.table_prefix or ""):
            raise ValueError(f"ItemsConfig.table_prefix must be a bare lowercase identifier, got {self.table_prefix!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("ItemsConfig.org_id_expr must be a non-empty SQL expression (or unset)")
        seen = set(values(ItemType))
        for extra in self.extra_item_types:
            if not _IDENT.match(extra or ""):
                raise ValueError(f"ItemsConfig.extra_item_types entries must be snake_case identifiers, got {extra!r}")
            if extra in seen:
                raise ValueError(f"ItemsConfig.extra_item_types repeats {extra!r}")
            seen.add(extra)

    @property
    def item_types(self) -> tuple[str, ...]:
        """Every accepted `item_type`: the seed's, then the vertical's extras."""
        return values(ItemType) + tuple(self.extra_item_types)

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`items` -> `itm_items`)."""
        return f"{self.table_prefix}{name}"


@dataclass(frozen=True)
class ItemsContext:
    """What every handler needs, resolved by the host's `resolve_context`."""

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["ItemsConfig", "ItemsContext"]
