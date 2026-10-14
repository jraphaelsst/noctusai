"""Behaviour probes for the items organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe


def item_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_itm_item_categories_name",
            kind="unique",
            requires=("itm_item_categories",),
            body=(
                f"INSERT INTO {s}.itm_item_categories (org_id, name) VALUES (v_org, 'noc probe');\n"
                f"INSERT INTO {s}.itm_item_categories (org_id, name) VALUES (v_org, 'NOC PROBE');"
            ),
            permitted="a case-variant duplicate root category name in one org",
            rationale="Category names are unique per (org, parent), case-insensitively: two 'Frios'/'frios' roots would split a catalogue branch.",
        ),
        OrganGuardProbe(
            guard_name="uq_itm_items_sku",
            kind="unique",
            requires=("itm_items",),
            body=(
                f"INSERT INTO {s}.itm_items (org_id, sku, name) VALUES (v_org, 'NOC-1', 'noc probe a');\n"
                f"INSERT INTO {s}.itm_items (org_id, sku, name) VALUES (v_org, 'noc-1', 'noc probe b');"
            ),
            permitted="a case-variant duplicate SKU in one org",
            rationale="A SKU identifies exactly one item per org (case-insensitive): stock, quotes and orders resolve items by it.",
        ),
    )
