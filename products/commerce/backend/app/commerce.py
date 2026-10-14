"""This product's `CommerceConfig` and its generated migration.

Everything that differs between two commerce products is a knob on the config;
the mechanics are `noctusai_lib.domain.commerce`. `migrations/012_commerce.sql`
is the generator's output VERBATIM -- never hand-edit it; regenerate:

    python -c "from app.commerce import generate_migration as g; \\
               open('migrations/012_commerce.sql','w').write(g())"

(run from products/commerce/backend). `tests/test_commerce_wiring.py` fails if the
file drifts from `commerce_migration(CFG, "commerce")`.
"""
from __future__ import annotations

from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration
from noctusai_lib.domain.contracts import ContractsConfig
from noctusai_lib.domain.finance import FinanceConfig
from noctusai_lib.domain.inventory import InventoryConfig
from noctusai_lib.domain.purchasing import PurchasingConfig
from noctusai_lib.domain.quotes import QuotesConfig

SCHEMA = "commerce"

# Org-picker rollout (core 070): the organ's default `org_id_expr` is already
# `current_org_id_for('<schema>')` (home org for everyone, the selected org while platform
# staff act), so no override here. `tests/test_commerce_wiring.py` pins it.
CFG = CommerceConfig(schema=SCHEMA)

# The finance organ lives in the SAME schema (tables `fin_*`); its migration, like the P4 commerce
# money / fiscal deltas, the jobs queue and the items organ, is rendered by
# `noctus.dev.render_organ_migration` and pinned by `tests/test_commerce_wiring.py`
# (`assert_organ_migration_current`). `012_commerce.sql` is APPLIED in prod and never rewritten.
FINANCE_CFG = FinanceConfig(schema=SCHEMA)

# The ERP organs that share the schema (migrations rendered by `noctus.dev.render_organ_migration`, order pinned by
# `assert_organ_migration_order` in `tests/test_commerce_erp_wiring.py`). Every cross-organ FK is on: commerce
# mounts parties, items, inventory and finance in the same schema.
INVENTORY_CFG = InventoryConfig(schema=SCHEMA)
PURCHASING_CFG = PurchasingConfig(schema=SCHEMA)
QUOTES_CFG = QuotesConfig(schema=SCHEMA)
CONTRACTS_CFG = ContractsConfig(schema=SCHEMA, with_parties=True, with_items=True)


def generate_migration() -> str:
    return commerce_migration(CFG, SCHEMA)
