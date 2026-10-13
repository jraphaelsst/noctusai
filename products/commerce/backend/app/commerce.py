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

# Org-picker rollout (core 070): every own-org RLS predicate resolves the caller's org through
# `current_org_id_for(<schema>)` (home org for everyone, the selected org while platform staff
# act) -- never the home-only `current_org_id()` the organ's default would emit.
# `tests/test_migration_007_org_picker_rollout.py` fails on any policy that doesn't.
CFG = CommerceConfig(schema=SCHEMA, org_id_expr=f"public.current_org_id_for('{SCHEMA}')")


def generate_migration() -> str:
    return commerce_migration(CFG, SCHEMA)
