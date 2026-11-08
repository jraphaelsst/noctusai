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

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from workspace import resolve_caller_root

from . import _catalog_scope_guard
from .migrate_product import _resolve_schema
from .scaffold_migration import (
    _format_number,
    _resolve_migrations_dir,
    next_migration_number,
    validate_schema_identifier,
    validate_product_slug,
)


# Child half of the cross-tree generator load. Runs under `PYTHONPATH=<tree>/seed/...`, so
# `noctusai_seed` / `noctusai_lib` resolve to THAT tree (the shared venv has the primary editable-
# installed; a PYTHONPATH entry is found first -- same recipe as `testing._worktree_pythonpath`).
# stdout's last line = one JSON object; the parent never trusts exit code or unparsable output.
_CHILD = """
import json, sys
req = json.loads(sys.argv[1])
from noctusai_seed.organs import ORGAN_REGISTRY
spec = ORGAN_REGISTRY.get(req["organ"])
out = {"registered": sorted(ORGAN_REGISTRY)}
if spec is not None:
    from noctusai_lib.testing.organs import expected_organ_migration
    import noctusai_seed.organs as _o
    out["header"] = spec.migration_header
    out["source"] = _o.__file__
    out["sql"] = {str(r): expected_organ_migration(req["organ"], req["schema"], r) for r in req["revisions"]}
print(json.dumps(out))
"""


def _tree_pythonpath(root: Path) -> str:
    return os.pathsep.join([str(root / "seed" / "framework" / "backend"), str(root / "seed" / "lib" / "backend")])


def _generator_from_tree(root: Path, organ: str, schema: str, revisions: list[int]) -> dict[str, Any]:
    """Run the organ generators of ``root`` (not the server's import path) in a child interpreter.

    Mechanism: `sys.executable -c` with `PYTHONPATH` = the tree's own seed dirs. Chosen over
    `root/mcp/noctusai/cli.py` because the child needs no argparse flag (every flag on a write tool
    is one more thing `toolkit_freshness._MAPPED_PARAMS` must mirror), and over an in-process
    `sys.path` swap because `noctusai_*` are already imported by the server, so a swap would keep
    serving the cached primary modules. Returns `{registered, header?, source?, sql?}` or `{error}`.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, json.dumps({"organ": organ, "schema": schema, "revisions": revisions})],
            capture_output=True, text=True, timeout=120, cwd=str(root),
            env={**os.environ, "PYTHONPATH": _tree_pythonpath(root)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"cannot run the organ generators of {root}: {exc}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": f"organ generators of {root} failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-400:]}"}


def _generator_in_process(organ: str, schema: str, revisions: list[int]) -> dict[str, Any]:
    """The server's own import path (no `worktree_path`)."""
    try:
        from noctusai_seed.organs import ORGAN_REGISTRY
        import noctusai_seed.organs as _o
    except ImportError as exc:  # seed framework not importable in this interpreter
        return {"error": f"cannot import noctusai_seed.organs: {exc}"}
    out: dict[str, Any] = {"registered": sorted(ORGAN_REGISTRY)}
    spec = ORGAN_REGISTRY.get(organ)
    if spec is not None:
        from noctusai_lib.testing.organs import expected_organ_migration
        out.update(header=spec.migration_header, source=_o.__file__,
                   sql={str(r): expected_organ_migration(organ, schema, r) for r in revisions})
    return out


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
    generator_fn: Callable[[str, str, list[int]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The organ generator code is loaded FROM the tree ``worktree_path`` names (child interpreter with
    that tree's seed dirs on PYTHONPATH, see ``_generator_from_tree``), never from the server's import
    path, so an unmerged generator change is what gets rendered/compared. Without ``worktree_path`` the
    server's own copy is used and the result says so (``generator_source`` + a warning).
    ``generator_fn(organ, schema, revisions)`` is the test seam.

    Returns ``{status, product, organ, schema, path, number, catalog_scope, warnings, error}``.

    status: planned | would_refresh | would_new_revision | up_to_date | created | refreshed |
            new_revision | refused_catalog_scope | error
    """
    result: dict[str, Any] = {"product": product, "organ": organ, "warnings": []}
    bad = validate_product_slug(product) or (validate_schema_identifier(schema) if schema is not None else None)
    if bad:
        return {**result, "status": "error", "error": bad}

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

    gen_root: Path | None = None
    if worktree_path is not None and generator_fn is None:
        try:
            gen_root = Path(resolve_caller_root(worktree_path))
        except ValueError as exc:
            return {**result, "status": "error", "error": str(exc)}
    result["resolved_root"] = str(gen_root) if gen_root else None

    def _generate(schema_: str, revisions: list[int]) -> dict[str, Any]:
        if generator_fn is not None:
            return generator_fn(organ, schema_, revisions)
        if gen_root is not None:
            return _generator_from_tree(gen_root, organ, schema_, revisions)
        return _generator_in_process(organ, schema_, revisions)

    probe = _generate("probe_schema", [1])
    if "error" in probe:
        return {**result, "status": "error", "error": probe["error"]}
    if "header" not in probe:
        return {**result, "status": "error",
                "error": f"unknown organ {organ!r}; registered: {probe['registered']}"}
    header = probe["header"]
    result["generator_source"] = probe.get("source")
    if worktree_path is None and generator_fn is None:
        result["warnings"].append(
            f"no worktree_path: organ generators were loaded from the SERVER's tree ({probe.get('source')}). "
            "An unmerged generator change in your worktree was NOT measured -- pass worktree_path=<your worktree root>."
        )

    base, migrations_dir, err = _resolve_migrations_dir(
        product, worktree_path=worktree_path, products_dir=products_dir,
    )
    if err is not None:
        return {**result, "status": "error", "error": err["error"]}
    assert base is not None and migrations_dir is not None

    resolved_schema, schema_source = _resolve_schema(product, schema, base)
    result.update(schema=resolved_schema, schema_source=schema_source)
    if schema_source == "slug_fallback":
        return {**result, "status": "error", "error": (
            f"Could not derive the DB schema of {product!r} from its app/main.py create_product_app(schema=...) "
            f"declaration; refusing to render DDL into a guessed schema. Pass schema= explicitly."
        )}
    from noctusai_lib.testing.migrations_applied import load_applied

    existing = [
        p for p in sorted(migrations_dir.glob("*.sql"))
        if p.read_text(encoding="utf-8").startswith(header)
    ]
    gen = _generate(resolved_schema, [max(len(existing), 1), len(existing) + 1])
    if "error" in gen:
        return {**result, "status": "error", "error": gen["error"]}
    sql = gen["sql"][str(max(len(existing), 1))]
    new_revision = False
    if existing:
        path = existing[-1]
        result["path"] = str(path)
        if path.read_text(encoding="utf-8") == sql:
            return {**result, "status": "up_to_date"}
        try:
            applied = load_applied(migrations_dir)
        except ValueError as exc:
            return {**result, "status": "error", "error": str(exc)}
        if path.name not in applied:  # unapplied: refresh in place
            if not confirm:
                return {**result, "status": "would_refresh"}
            path.write_text(sql, encoding="utf-8")
            return {**result, "status": "refreshed"}
        # applied files are frozen: the generator moved on => ship the full current state as a NEW file
        new_revision = True
        revision = len(existing) + 1
        sql = gen["sql"][str(revision)]
        result["revision"] = revision

    number = next_migration_number(
        product, worktree_path=worktree_path, products_dir=products_dir, skip_fetch=skip_fetch,
    )
    if "error" in number:
        return {**result, "status": "error", "error": number["error"]}
    result["warnings"] = result["warnings"] + list(number.get("warnings", []))
    n = number["next_number"]
    suffix = f"{organ}_rev{result['revision']}" if new_revision else organ
    path = migrations_dir / f"{_format_number(n)}_{suffix}.sql"
    result.update(path=str(path), number=n)
    if path.exists():
        return {**result, "status": "error", "error": f"refusing to overwrite {path}"}
    if not confirm:
        return {**result, "status": "would_new_revision" if new_revision else "planned"}
    path.write_text(sql, encoding="utf-8")
    return {**result, "status": "new_revision" if new_revision else "created"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.render_organ_migration",
        description=(
            "Render a seed organ's generated migration (e.g. organ='finance' -> "
            "finance_migration(FinanceConfig(schema=<product schema>))) into "
            "products/<p>/backend/migrations/NNN_<organ>.sql with a collision-safe number "
            "(next_migration_number). DRY-RUN by default (status 'planned'/'would_refresh'); "
            "confirm=True writes. Idempotent: an existing rendered file is found by the organ's "
            "generated header and left alone when current ('up_to_date'); when the generator changed, an "
            "unapplied file is refreshed in place, an applied one (migrations-applied.json) yields a NEW revision file ('new_revision'). "
            " Refuses asleep products (catalog scope guard -> "
            "'refused_catalog_scope'; allow_inactive=True is the supervised escape hatch). `worktree_path` pins the tree: the "
            "file path AND the organ generator code (run in a child interpreter on that tree's seed "
            "dirs) come from it; omitted => the server's own tree, flagged in `warnings`/`generator_source`. Pair the "
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
