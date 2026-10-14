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
from noctusai_lib.testing.migrations_applied import load_applied, sha256_text

__all__ = ["assert_organ_migration_current", "expected_organ_migration", "find_organ_migration"]


def find_organ_migration(product_dir: str | Path, header: str) -> list[Path]:
    return [
        p for p in sorted(migrations_dir(product_dir).glob("*.sql"))
        if p.read_text(encoding="utf-8").startswith(header)
    ]


def expected_organ_migration(organ: str, schema: str, revision: int) -> str:
    """The generator's output for revision ``revision`` (1-based). Revision 1 is the bare output;
    a later revision is the same full-state script plus a trailing ``-- organ-revision: N`` marker."""
    from noctusai_seed.organs import organ_migration_sql

    sql = organ_migration_sql(organ, schema)
    return sql if revision <= 1 else f"{sql.rstrip(chr(10))}\n-- organ-revision: {revision}\n"


def assert_organ_migration_current(product_dir: str | Path, organ: str, *, schema: str) -> Path:
    """Pin the LATEST rendered file of ``organ`` to the generator; earlier files are FROZEN.

    A generator change after a file was applied ships as a NEW file (``render_organ_migration``
    -> ``new_revision``), so >=1 files may exist. Every file but the latest must be recorded as
    applied (``migrations-applied.json``) and byte-identical to the recorded sha256 -- never
    compared to the generator. Returns the latest file.
    """
    from noctusai_seed.organs import ORGAN_REGISTRY

    spec = ORGAN_REGISTRY[organ]
    found = find_organ_migration(product_dir, spec.migration_header)
    assert found, f"no rendered {organ} migration found -- render one with noctus.dev.render_organ_migration"
    applied = load_applied(migrations_dir(product_dir))
    for old in found[:-1]:
        recorded = applied.get(old.name)
        assert recorded is not None, (
            f"{old.name} is superseded by {found[-1].name} but is not recorded as applied in "
            f"migrations-applied.json -- an unapplied revision must be refreshed in place, not stacked"
        )
        assert sha256_text(old.read_text(encoding="utf-8")) == recorded, (
            f"{old.name} is applied and frozen but its bytes changed -- restore it; ship changes as a "
            f"new revision via noctus.dev.render_organ_migration"
        )
    latest = found[-1]
    expected = expected_organ_migration(organ, schema, len(found))
    assert latest.read_text(encoding="utf-8") == expected, (
        f"{latest.name} drifted from the {organ} generator -- re-render with "
        f"noctus.dev.render_organ_migration (unapplied: refreshed in place; applied: a new revision file)"
    )
    return latest
