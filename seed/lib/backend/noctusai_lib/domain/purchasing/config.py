"""`PurchasingConfig` -- everything that differs between two purchasing hosts.

Same `org_id_expr` mechanism as `FinanceConfig` / `InventoryConfig`. The `with_*` flags decide which
cross-organ FKs the generator emits (they are only valid when that organ is mounted in the SAME schema).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Default AP category (KB PATTERNS/finance/dre-structure.md section 2a).
DEFAULT_CATEGORY_HINT = "Mercadorias / insumos para revenda"


@dataclass(frozen=True)
class PurchasingConfig:
    """One purchasing host's knobs.

    Attributes:
        schema: the product's Postgres schema.
        table_prefix: prefix of every organ table (`pur_` => `pur_orders`) and RPC.
        with_parties: emit the composite FK `(party_id, org_id) -> <parties_prefix>parties(id, org_id)` and resolve
            the supplier snapshot from the party. False => the supplier is a free-text `supplier_name`.
        with_items: emit `item_id -> <items_prefix>items(id)` and have the RPC verify the item belongs to the org.
        with_inventory: emit `warehouse_id -> <inventory_prefix>warehouses(id)`; the warehouse (and an item on every
            line) become REQUIRED because a receipt posts stock. False => no stock leg.
        admin_approves_above_threshold: when True an org admin may approve ABOVE the threshold without being in the
            org's approver list (`pur_approvers`; default False: above the threshold only an approver approves).
        default_category_hint: the finance category (by name) AP entries land on.
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to.
            Unset => `public.current_org_id_for('<schema>')`.
    """

    schema: str
    table_prefix: str = "pur_"
    with_parties: bool = True
    parties_prefix: str = "pty_"
    with_items: bool = True
    items_prefix: str = "itm_"
    with_inventory: bool = True
    inventory_prefix: str = "inv_"
    admin_approves_above_threshold: bool = False
    default_category_hint: str = DEFAULT_CATEGORY_HINT
    org_id_expr: Optional[str] = None

    def __post_init__(self) -> None:
        for label in ("schema", "table_prefix", "parties_prefix", "items_prefix", "inventory_prefix"):
            if not _IDENT.match(getattr(self, label) or ""):
                raise ValueError(f"PurchasingConfig.{label} must be a bare lowercase identifier, got {getattr(self, label)!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("PurchasingConfig.org_id_expr must be a non-empty SQL expression (or unset)")

    def table(self, name: str) -> str:
        """The physical table name of the organ table `name` (`orders` -> `pur_orders`)."""
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
    def warehouses_table(self) -> str:
        return f"{self.inventory_prefix}warehouses"


@dataclass(frozen=True)
class PurchasingContext:
    """What every handler needs, resolved by the host's `resolve_context`.

    `is_admin` is decided SERVER-SIDE (the trusted role in the SELECTED org); never from `user_metadata`. Whether the
    caller is an APPROVER is NOT host-supplied: the router reads `pur_approvers` for `(org_id, user_id)` itself, so
    approval authority can only come from this organ's own org-scoped list.
    """

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False


__all__ = ["DEFAULT_CATEGORY_HINT", "PurchasingConfig", "PurchasingContext"]
