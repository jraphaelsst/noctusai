"""Pin helper: a product's rendered organ migration must equal the organ generator's output.

Generalizes `products/commerce/backend/tests/test_commerce_wiring.py`'s
`test_commerce_migration_is_the_generators_output` to every registered organ::

    from noctusai_lib.testing.organs import assert_organ_migration_current

    def test_finance_migration_current():
        assert_organ_migration_current(Path(__file__).resolve().parents[1], "finance", schema="erp")

The file is found by the organ's HEADER (never by number or name -- a renumber on integrate
must not break the test). Render/refresh it with `noctus.dev.render_organ_migration`.
"""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migrations_dir

__all__ = ["assert_organ_migration_current", "find_organ_migration"]


def find_organ_migration(product_dir: str | Path, header: str) -> list[Path]:
    return [
        p for p in sorted(migrations_dir(product_dir).glob("*.sql"))
        if p.read_text(encoding="utf-8").startswith(header)
    ]


def assert_organ_migration_current(product_dir: str | Path, organ: str, *, schema: str) -> Path:
    from noctusai_seed.organs import ORGAN_REGISTRY, organ_migration_sql

    spec = ORGAN_REGISTRY[organ]
    found = find_organ_migration(product_dir, spec.migration_header)
    assert len(found) == 1, f"expected exactly one rendered {organ} migration, found {found}"
    expected = organ_migration_sql(organ, schema)
    assert found[0].read_text(encoding="utf-8") == expected, (
        f"{found[0].name} drifted from the {organ} generator -- re-render it with "
        f"noctus.dev.render_organ_migration (never hand-edit a generated migration)"
    )
    return found[0]
