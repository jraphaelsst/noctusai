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


def _active_slugs(root: Path) -> list[str]:
    """Slugs of `deploy/fleet/active-scope.txt` (the set every gate checks; asleep products are out)."""
    f = root / "deploy" / "fleet" / "active-scope.txt"
    if not f.is_file():
        return []
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


_BASELINE_REL = Path("deploy") / "fleet" / "organ-render-baseline.json"


def _load_baseline(root: Path, baseline: list[dict[str, Any]] | None) -> dict[tuple[str, str], dict[str, Any]]:
    """Accepted known-lag drift: ``{(product, organ): entry}``. Each entry needs a destination and a date
    (a baseline row without them is a silent deferral, so it is refused)."""
    if baseline is None:
        f = root / _BASELINE_REL
        baseline = json.loads(f.read_text(encoding="utf-8")).get("accepted", []) if f.is_file() else []
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for e in baseline:
        missing = [k for k in ("product", "organ", "destination", "date") if not e.get(k)]
        if missing:
            raise ValueError(f"{_BASELINE_REL}: entry {e!r} lacks {missing} -- an accepted drift needs a destination and a date")
        out[(e["product"], e["organ"])] = e
    return out


def _frozen_violations(migrations_dir: Path) -> list[str]:
    """Applied files (migrations-applied.json) whose bytes no longer match the recorded sha256.

    An applied migration is frozen -- it ran in prod under the schema it names (e.g. `monica` before the
    nosnolimiar cutover). A render must only ever ADD a new revision, never rewrite one of these.
    """
    from noctusai_lib.testing.migrations_applied import load_applied, sha256_text

    bad: list[str] = []
    for name, recorded in sorted(load_applied(migrations_dir).items()):
        f = migrations_dir / name
        if f.is_file() and sha256_text(f.read_text(encoding="utf-8")) != recorded:
            bad.append(name)
    return bad


def render_all_consumers(
    *,
    baseline: list[dict[str, Any]] | None = None,
    write: bool = False,
    worktree_path: str | Path | None = None,
    generator_fn: Callable[[str, str, list[int]], dict[str, Any]] | None = None,
    products_dir: Path | None = None,
    slugs: list[str] | None = None,
) -> dict[str, Any]:
    """Every active product's committed organ render vs the organ generator output of the tree.

    A product is a consumer of an organ when one of its `backend/migrations/*.sql` starts with the
    organ's generated header. `write=False` (check) lists the consumers whose render drifted;
    `write=True` re-renders them (render_organ_migration semantics: unapplied file refreshed in
    place, applied one => a new revision file). Cheap: generator output is memoised per
    (organ, schema, revisions), so each organ costs one child interpreter plus one per distinct schema.

    Drift listed in the committed baseline (``deploy/fleet/organ-render-baseline.json``, each entry with a
    destination + date) is reported as ``accepted`` and never fails the check or gets written; only NEW
    drift fails.

    Returns ``{status, ok, checked, drifted, accepted, rendered, errors}``;
    status: clean | accepted | drift | rendered | error.
    """
    root = Path(resolve_caller_root(worktree_path)) if worktree_path is not None else Path(__file__).resolve().parents[5]
    pdir = products_dir or root / "products"
    cache: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    inner = generator_fn

    def gen(organ: str, schema: str, revisions: list[int]) -> dict[str, Any]:
        key = (organ, schema, tuple(revisions))
        if key not in cache:
            if inner is not None:
                cache[key] = inner(organ, schema, revisions)
            elif worktree_path is not None:
                cache[key] = _generator_from_tree(root, organ, schema, revisions)
            else:
                cache[key] = _generator_in_process(organ, schema, revisions)
        return cache[key]

    registered = gen("", "probe_schema", [1])
    if "error" in registered:
        return {"status": "error", "ok": False, "checked": 0, "drifted": [], "rendered": [], "errors": [registered["error"]]}
    headers: dict[str, str] = {}
    for organ in registered["registered"]:
        probe = gen(organ, "probe_schema", [1])
        if "header" in probe:
            headers[organ] = probe["header"]

    active = slugs if slugs is not None else _active_slugs(root)
    live = lambda: list(active)  # noqa: E731 - offline roster, never the network catalog
    try:
        accepted_map = _load_baseline(root, baseline)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"status": "error", "ok": False, "checked": 0, "drifted": [], "accepted": [], "rendered": [], "errors": [str(exc)]}
    checked, drifted, accepted, rendered, errors = 0, [], [], [], []
    for slug in active:
        mig = pdir / slug / "backend" / "migrations"
        if not mig.is_dir():
            continue
        texts = [p.read_text(encoding="utf-8") for p in sorted(mig.glob("*.sql"))]
        for organ, header in headers.items():
            if not any(t.startswith(header) for t in texts):
                continue
            checked += 1
            try:
                frozen_bad = _frozen_violations(mig)
            except ValueError as exc:
                frozen_bad = [f"unreadable migrations-applied.json: {exc}"]
            if frozen_bad:
                errors.append({"product": slug, "organ": organ, "status": "frozen_file_modified",
                               "error": f"applied (frozen) migration(s) differ from the recorded sha256: {frozen_bad}. "
                                        "Restore them; ship changes as a NEW revision file, never by rewriting an applied one."})
                continue

            def _run(confirm: bool, slug: str = slug, organ: str = organ) -> dict[str, Any]:
                return render_organ_migration(
                    slug, organ, confirm=confirm, worktree_path=None,
                    products_dir=pdir, skip_fetch=True, live_products_fn=live, generator_fn=gen,
                )

            r = _run(False)
            st = r["status"]
            if st in ("would_refresh", "would_new_revision") and (slug, organ) in accepted_map:
                e = accepted_map[(slug, organ)]
                accepted.append({"product": slug, "organ": organ, "status": st, "path": r.get("path"),
                                 "destination": e["destination"], "date": e["date"]})
                continue
            if write and st in ("would_refresh", "would_new_revision"):
                r = _run(True)
                st = r["status"]
                after = _frozen_violations(mig)
                if after:  # defence in depth: a write must never have touched an applied file
                    errors.append({"product": slug, "organ": organ, "status": "frozen_file_modified",
                                   "error": f"the render modified applied (frozen) file(s) {after}"})
                    continue
            if st == "up_to_date":
                continue
            row = {"product": slug, "organ": organ, "status": st, "path": r.get("path")}
            if st in ("would_refresh", "would_new_revision"):
                drifted.append(row)
            elif st in ("refreshed", "new_revision"):
                rendered.append(row)
            else:
                errors.append({**row, "error": r.get("error")})
    status = ("error" if errors else "rendered" if rendered else "drift" if drifted
              else "accepted" if accepted else "clean")
    return {"status": status, "ok": status in ("clean", "accepted", "rendered"), "checked": checked,
            "drifted": drifted, "accepted": accepted, "rendered": rendered, "errors": errors}


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
            "all_consumers=True (product/organ ignored): check EVERY active consumer's committed render against the "
            "generator (confirm=False lists drift, confirm=True re-renders) -- the derived-artifact check for a seed organ generator change. "
            "KB § PATTERNS/architect/vertical-seed.md."
        ),
    )
    def _render_organ_migration(
        product: str = "",
        organ: str = "",
        confirm: bool = False,
        schema: str | None = None,
        allow_inactive: bool = False,
        worktree_path: str | None = None,
        skip_fetch: bool = False,
        all_consumers: bool = False,
    ) -> dict:
        if all_consumers:
            return render_all_consumers(write=confirm, worktree_path=worktree_path)
        if not product or not organ:
            return {"status": "error", "error": "product and organ are required unless all_consumers=True"}
        return render_organ_migration(
            product, organ, confirm=confirm, schema=schema, allow_inactive=allow_inactive,
            worktree_path=worktree_path, skip_fetch=skip_fetch,
        )
