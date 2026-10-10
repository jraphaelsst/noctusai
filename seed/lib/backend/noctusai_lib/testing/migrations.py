"""Locate a product migration by NAME, never by number.

WHY. Migration numbers are assigned at scaffold time and re-assigned when a
branch integrates onto a busier ``dev`` (``task_branch integrate`` renumbers a
colliding ``NNN_x.sql`` -> ``MMM_x.sql``). A test that hardcodes
``"217_x.sql"`` therefore breaks on a rebase that changed nothing else.
Resolve by the stable name suffix instead::

    from noctusai_lib.testing.migrations import migration_path, migration_sql

    sql = migration_sql(Path(__file__).resolve().parents[2], "cs_research_extraction")

Exactly ONE ``<digits>_<name_suffix>.sql`` must match: zero or several raise
:class:`MigrationLookupError` naming the candidates (never a silent guess).

Keeper: ``check_migration_number_refs_in_tests``.
KB: ``KB § PATTERNS/compliance/testing.md`` (migration references).
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["MigrationLookupError", "migration_path", "migration_sql", "migrations_dir"]


class MigrationLookupError(LookupError):
    """Zero or more than one migration matched the requested suffix."""


def migrations_dir(root: str | Path) -> Path:
    """Accept a migrations dir, ``<product>/backend`` or ``<product>`` root."""
    base = Path(root)
    for candidate in (base, base / "migrations", base / "backend" / "migrations"):
        if candidate.name == "migrations" and candidate.is_dir():
            return candidate
    raise MigrationLookupError(f"no migrations directory under {base}")


def migration_path(migrations_dir_or_product_root: str | Path, name_suffix: str) -> Path:
    """The single ``<digits>_<name_suffix>.sql`` under the given migrations dir.

    ``name_suffix`` may omit or include the ``.sql`` extension.
    """
    suffix = name_suffix[:-4] if name_suffix.endswith(".sql") else name_suffix
    directory = migrations_dir(migrations_dir_or_product_root)
    pattern = re.compile(rf"^\d+_{re.escape(suffix)}\.sql$")
    matches = sorted(p for p in directory.iterdir() if pattern.match(p.name))
    if len(matches) != 1:
        found = [p.name for p in matches] or "none"
        raise MigrationLookupError(
            f"expected exactly one migration matching '<digits>_{suffix}.sql' in {directory}; found: {found}"
        )
    return matches[0]


def migration_sql(migrations_dir_or_product_root: str | Path, name_suffix: str) -> str:
    """Text of :func:`migration_path`'s result."""
    return migration_path(migrations_dir_or_product_root, name_suffix).read_text(encoding="utf-8")
