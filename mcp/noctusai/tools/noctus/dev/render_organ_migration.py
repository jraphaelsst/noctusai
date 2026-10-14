"""`noctus.dev.render_organ_migration` -- render a seed organ's generated migration into a product.

The organ generators (`finance_migration(FinanceConfig(schema=...), schema)`) are the single source
of the DDL; a product's `migrations/NNN_<organ>.sql` is their output VERBATIM. This tool writes it
with a collision-safe number (`next_migration_number`) and is idempotent: an existing file is found
by the organ's generated HEADER (never by number/name -- a renumber on integrate must not break
this) and left alone when current, refreshed in place when the generator moved on.

DRY-RUN by default. Refuses asleep products (catalog scope guard, same as migrate_product/deploy_image).
Pin test for the product side: `noctusai_lib.testing.organs.assert_organ_migration_current`.

KB § PATTERNS/architect/vertical-seed.md (one-call organ mount) · KB § PATTERNS/architect/mcp-first-scripts.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import _catalog_scope_guard
from .migrate_product import _resolve_schema
from .scaffold_migration import (
    _format_number,
    _resolve_migrations_dir,
    next_migration_number,
)


def render_organ_migration(
    product: str,
    organ: str,
    *,
    confirm: bool = False,
    schema: str | None = None,
    allow_inactive: bool = False,
    worktree_path: str | Path | None = None,
    products_dir: Path | None = None,
    skip_fetch: bool = False,
    live_products_fn: Callable[[], list[str]] | None = None,
) -> dict[str, Any]:
    """Returns ``{status, product, organ, schema, path, number, catalog_scope, warnings, error}``.

    status: planned | would_refresh | up_to_date | created | refreshed |
            refused_catalog_scope | error
    """
    result: dict[str, Any] = {"product": product, "organ": organ, "warnings": []}

    catalog_scope = _catalog_scope_guard.check_catalog_scope(product, live_products_fn)
    result["catalog_scope"] = catalog_scope
    result["allow_inactive"] = allow_inactive
    if not catalog_scope["in_scope"] and not allow_inactive:
        return {
            **result,
            "status": _catalog_scope_guard.REFUSED_STATUS,
            "error": _catalog_scope_guard.catalog_scope_refusal_reason(
                product, catalog_scope, action="render an organ migration into",
                escape_hatch="allow_inactive",
                untouched_clause="No migration file was written.",
            ),
        }

    try:
        from noctusai_seed.organs import ORGAN_REGISTRY, organ_migration_sql
    except ImportError as exc:  # seed framework not importable in this interpreter
        return {**result, "status": "error", "error": f"cannot import noctusai_seed.organs: {exc}"}
    spec = ORGAN_REGISTRY.get(organ)
    if spec is None:
        return {**result, "status": "error",
                "error": f"unknown organ {organ!r}; registered: {sorted(ORGAN_REGISTRY)}"}

    base, migrations_dir, err = _resolve_migrations_dir(
        product, worktree_path=worktree_path, products_dir=products_dir,
    )
    if err is not None:
        return {**result, "status": "error", "error": err["error"]}
    assert base is not None and migrations_dir is not None

    resolved_schema, schema_source = _resolve_schema(product, schema, base)
    result.update(schema=resolved_schema, schema_source=schema_source)
    sql = organ_migration_sql(organ, resolved_schema)

    existing = [
        p for p in sorted(migrations_dir.glob("*.sql"))
        if p.read_text(encoding="utf-8").startswith(spec.migration_header)
    ]
    if len(existing) > 1:
        return {**result, "status": "error",
                "error": f"expected at most one rendered {organ} migration, found {[p.name for p in existing]}"}

    if existing:
        path = existing[0]
        result["path"] = str(path)
        if path.read_text(encoding="utf-8") == sql:
            return {**result, "status": "up_to_date"}
        if not confirm:
            return {**result, "status": "would_refresh"}
        path.write_text(sql, encoding="utf-8")
        return {**result, "status": "refreshed"}

    number = next_migration_number(
        product, worktree_path=worktree_path, products_dir=products_dir, skip_fetch=skip_fetch,
    )
    if "error" in number:
        return {**result, "status": "error", "error": number["error"]}
    result["warnings"] = list(number.get("warnings", []))
    n = number["next_number"]
    path = migrations_dir / f"{_format_number(n)}_{organ}.sql"
    result.update(path=str(path), number=n)
    if path.exists():
        return {**result, "status": "error", "error": f"refusing to overwrite {path}"}
    if not confirm:
        return {**result, "status": "planned"}
    path.write_text(sql, encoding="utf-8")
    return {**result, "status": "created"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.render_organ_migration",
        description=(
            "Render a seed organ's generated migration (e.g. organ='finance' -> "
            "finance_migration(FinanceConfig(schema=<product schema>))) into "
            "products/<p>/backend/migrations/NNN_<organ>.sql with a collision-safe number "
            "(next_migration_number). DRY-RUN by default (status 'planned'/'would_refresh'); "
            "confirm=True writes. Idempotent: an existing rendered file is found by the organ's "
            "generated header and left alone when current ('up_to_date'), refreshed in place when "
            "the generator changed. Refuses asleep products (catalog scope guard -> "
            "'refused_catalog_scope'; allow_inactive=True is the supervised escape hatch). Pair the "
            "product with noctusai_lib.testing.organs.assert_organ_migration_current. "
            "KB § PATTERNS/architect/vertical-seed.md."
        ),
    )
    def _render_organ_migration(
        product: str,
        organ: str,
        confirm: bool = False,
        schema: str | None = None,
        allow_inactive: bool = False,
        worktree_path: str | None = None,
        skip_fetch: bool = False,
    ) -> dict:
        return render_organ_migration(
            product, organ, confirm=confirm, schema=schema, allow_inactive=allow_inactive,
            worktree_path=worktree_path, skip_fetch=skip_fetch,
        )
