"""Behaviour probes for the inventory organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_item uuid; v_wh uuid;"


def _item_and_warehouse(s: str) -> str:
    return (
        f"INSERT INTO {s}.itm_items (org_id, sku, name) VALUES (v_org, 'NOC-INV', 'noc probe item') RETURNING id INTO v_item;\n"
        f"INSERT INTO {s}.inv_warehouses (org_id, name, code) VALUES (v_org, 'noc probe', 'NOC') RETURNING id INTO v_wh;\n"
    )


def _move(s: str, kind: str = "in") -> str:
    return (
        f"INSERT INTO {s}.inv_stock_moves (org_id, item_id, warehouse_id, kind, qty, source, source_ref, "
        f"on_hand_after, reserved_after, avg_cost_after_cents) "
        f"VALUES (v_org, v_item, v_wh, '{kind}', 1, 'noc_probe', 'ref-1', 1, 0, 0)"
    )


def inventory_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    needs_stock = ("itm_items", "inv_warehouses", "inv_stock_balances")
    return (
        OrganGuardProbe(
            guard_name="uq_inv_warehouses_code",
            kind="unique",
            requires=("inv_warehouses",),
            body=(
                f"INSERT INTO {s}.inv_warehouses (org_id, name, code) VALUES (v_org, 'noc a', 'noc-w');\n"
                f"INSERT INTO {s}.inv_warehouses (org_id, name, code) VALUES (v_org, 'noc b', 'NOC-W');"
            ),
            permitted="a case-variant duplicate warehouse code in one org",
            rationale="A warehouse code identifies one warehouse per org (case-insensitive); stock lookups by code must be unambiguous.",
        ),
        OrganGuardProbe(
            guard_name="uq_inv_warehouses_default",
            kind="unique",
            requires=("inv_warehouses",),
            body=(
                f"INSERT INTO {s}.inv_warehouses (org_id, name, code, is_default) VALUES (v_org, 'noc a', 'noc-a', true);\n"
                f"INSERT INTO {s}.inv_warehouses (org_id, name, code, is_default) VALUES (v_org, 'noc b', 'noc-b', true);"
            ),
            permitted="a second default warehouse in one org",
            rationale="Exactly one default warehouse per org: a stock move with no explicit warehouse must land in one place.",
        ),
        OrganGuardProbe(
            guard_name="inv_stock_balances_reserved_nonneg",
            kind="check",
            requires=needs_stock,
            declare=_DECLARE,
            body=(
                _item_and_warehouse(s)
                + f"INSERT INTO {s}.inv_stock_balances (org_id, item_id, warehouse_id, on_hand, reserved) VALUES (v_org, v_item, v_wh, 0, -1);"
            ),
            permitted="a negative reserved quantity",
            rationale="Reserved stock can never go below zero: a release larger than the reservation would mint stock.",
        ),
        OrganGuardProbe(
            guard_name="inv_stock_balances_available_nonneg",
            kind="check",
            requires=needs_stock,
            declare=_DECLARE,
            body=(
                _item_and_warehouse(s)
                + f"INSERT INTO {s}.inv_stock_balances (org_id, item_id, warehouse_id, on_hand, reserved) VALUES (v_org, v_item, v_wh, 1, 2);"
            ),
            permitted="reserving more than is on hand",
            rationale="Available stock (on hand minus reserved) can never go negative: overselling is refused at the table, not only in the service.",
        ),
        OrganGuardProbe(
            guard_name="uq_inv_stock_moves_idem",
            kind="unique",
            requires=("itm_items", "inv_warehouses", "inv_stock_moves"),
            declare=_DECLARE,
            body=_item_and_warehouse(s) + _move(s) + ";\n" + _move(s) + ";",
            permitted="a replayed stock move with the same source reference",
            rationale="A retried posting (same source, source_ref, kind, item, warehouse) is a replay, never a second kardex row.",
        ),
        OrganGuardProbe(
            guard_name="inv_stock_moves_append_only",
            kind="trigger",
            requires=("itm_items", "inv_warehouses", "inv_stock_moves"),
            declare=_DECLARE,
            fragment="inv_stock_moves is append-only",
            body=_item_and_warehouse(s) + _move(s) + f";\nUPDATE {s}.inv_stock_moves SET note = 'noc probe' WHERE org_id = v_org;",
            permitted="an UPDATE of a kardex row",
            rationale="The stock kardex is history: a correction is a new `adjust` move, never an edit of an old row.",
        ),
    )
