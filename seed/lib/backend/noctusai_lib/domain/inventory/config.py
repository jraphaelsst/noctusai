"""`InventoryConfig` -- everything that differs between two inventory hosts.

Same `org_id_expr` mechanism as `FinanceConfig` / `CommerceConfig`. The one extra
knob is the cross-organ FK: `with_items` emits `item_id -> <schema>.itm_items(id)`
only when the `items` organ is mounted in the same schema (roadmap E8).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class InventoryConfig:
    """One inventory host's knobs.

    Attributes:
        schema: the product's Postgres schema.
        table_prefix: prefix of every organ table (`inv_` => `inv_stock_moves`) and RPC.
        with_items: emit the FK `item_id -> <schema>.<items_prefix>items(id)` and have the
            RPCs verify the item belongs to the caller's org. Default True; set False for a
            host that has no `items` organ (item ids are then opaque uuids).
        items_prefix: table prefix of the `items` organ (`itm_`).
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to.
            Unset => `public.current_org_id_for('<schema>')`.
    """

    schema: str
    table_prefix: str = "inv_"
    with_items: bool = True
    items_prefix: str = "itm_"
    org_id_expr: Optional[str] = None

    def __post_init__(self) -> None:
        for label, value in (("schema", self.schema), ("table_prefix", self.table_prefix), ("items_prefix", self.items_prefix)):
            if not _IDENT.match(value or ""):
                raise ValueError(f"InventoryConfig.{label} must be a bare lowercase identifier, got {value!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("InventoryConfig.org_id_expr must be a non-empty SQL expression (or unset)")

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`stock_moves` -> `inv_stock_moves`)."""
        return f"{self.table_prefix}{name}"

    def rpc(self, name: str) -> str:
        """The prefixed name of an inventory RPC (`inv_` + `receive`)."""
        return f"{self.table_prefix}{name}"

    @property
    def items_table(self) -> str:
        return f"{self.items_prefix}items"


@dataclass(frozen=True)
class InventoryContext:
    """What every handler needs, resolved by the host's `resolve_context`."""

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["InventoryConfig", "InventoryContext"]
