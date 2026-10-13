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

SCHEMA = "commerce"

# Org-picker rollout (core 070): the organ's default `org_id_expr` is already
# `current_org_id_for('<schema>')` (home org for everyone, the selected org while platform
# staff act), so no override here. `tests/test_commerce_wiring.py` pins it.
CFG = CommerceConfig(schema=SCHEMA)


def generate_migration() -> str:
    return commerce_migration(CFG, SCHEMA)
