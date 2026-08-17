"""Migration scaffolder — emits the next-numbered SQL file for a product.

WHY this tool exists
--------------------
Two slips this catches at authoring-time:

1. **Migration-numbering slip.** Every product holds an ordered, prefix-numbered
   migration log (``001_seed.sql`` → ``002_status_pagina.sql`` → …). Hand-rolled
   numbering drifts: agents skip ahead, repeat a number, or invent the next slot
   wrong. This tool walks the directory and computes ``max(NN) + 1`` from the
   actual filesystem, so the consumer never has to count.

2. **Canonical-SQL drift.** New migrations must use the helpers from
   ``noctusai_lib.domain.sql_templates`` (``set_search_path`` /
   ``updated_at_function`` / ``updated_at_trigger`` / ``rls_subquery_policy``)
   so the platform-wide DDL conventions don't fork per-product. The emitted
   skeleton wires these in by default and points at the helpers in a comment
   block — no consumer re-reading the SQL conventions doc.

WHEN to use
-----------
Every fresh product migration. Authoring scratch SQL by hand still works (the
file is plain SQL once written), but reach for the scaffolder first — it pairs
with ``noctus.dev.scaffold_product`` (which emits ``001_seed.sql`` for new
products) for migrations 002+.

Mirrors ``mcp/noctusai/tools/noctus/dev/scaffold.py`` end-to-end: same
workspace-aware path resolution via ``settings.REPO_ROOT`` / ``PRODUCTS_DIR``,
same ``register(server)`` per-file MCP registration shape.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

# Per `feedback_mcp_path_constants_from_settings.md` — every MCP tool module
# imports REPO_ROOT/PRODUCTS_DIR from settings, never computes via parents[N].
from settings import PRODUCTS_DIR
from workspace import resolve_caller_root

# Seed-lib lookup is a separate concern from REPO_ROOT — settings doesn't
# expose it because the seed-lib path is not a tool-resolution constant. We
# reach `noctusai_lib.domain.sql_templates` via the seed-lib `sys.path` shim
# the test harness installs; in the running MCP server, `noctusai_lib` is
# already importable because the server's venv has it installed.
from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    set_search_path,
    updated_at_function,
    updated_at_trigger,
)

# Authoring-ergonomic wrappers — `prelude` bundles the schema-lock with a
# why-block; `noctusai_lib.sql.updated_at_trigger` emits function + trigger
# in one call. Used for the top-of-file prelude and the multi-table
# `with_updated_at=[...]` shortcut. Single-table `with_table=` keeps the
# existing canonical-helper composition for backward compatibility.
from noctusai_lib.sql import (
    prelude as sql_prelude,
    updated_at_trigger as sql_updated_at_trigger,
)

logger = logging.getLogger(__name__)

# Numeric prefix matcher — matches `NNN_<rest>.sql` where NNN is 1+ digits.
# Width is *whatever the existing files use* (3 digits today, future-proof).
_NN_RE = re.compile(r"^(\d+)_.+\.sql$")


def _slug_to_default_schema(product_slug: str) -> str:
    """`youtube-crawler` → `youtube_crawler` (matches scaffold_product convention)."""
    return product_slug.replace("-", "_")


def _migrations_dir(product_slug: str, products_dir: Path) -> Path:
    return products_dir / product_slug / "backend" / "migrations"


def _format_number(n: int) -> str:
    """Three-digit zero-padded prefix to match the platform convention."""
    return f"{n:03d}"


def _resolve_migrations_dir(
    product_slug: str,
    *,
    worktree_path: str | Path | None,
    products_dir: Path | None,
) -> tuple[Path | None, Path | None, dict | None]:
    """Resolve ``(base_products_dir, migrations_dir, error)``.

    Shared by ``scaffold_migration`` and ``next_migration_number`` — both need
    the identical "does this product / its migrations dir exist" gate with
    the identical error text. A caller seeing two DIFFERENT error strings for
    the same failure from two different tools is its own kind of drift.
    """
    if products_dir is not None:
        base_products_dir = products_dir
    elif worktree_path is not None:
        base_products_dir = resolve_caller_root(worktree_path) / "products"
    else:
        base_products_dir = PRODUCTS_DIR

    product_dir = base_products_dir / product_slug
    if not product_dir.is_dir():
        return None, None, {
            "error": (
                f"Product '{product_slug}' not found at {product_dir}. "
                f"Scaffold the product first via noctus.dev.scaffold_product."
            )
        }

    migrations_dir = _migrations_dir(product_slug, base_products_dir)
    if not migrations_dir.is_dir():
        return None, None, {
            "error": (
                f"Product '{product_slug}' has no backend/migrations/ directory "
                f"(expected at {migrations_dir}). Scaffold the product first via "
                f"noctus.dev.scaffold_product — it ships 001_seed.sql."
            )
        }
    return base_products_dir, migrations_dir, None


def _origin_dev_migration_files(
    repo_root: Path,
    migrations_rel: str,
    *,
    dev_ref: str,
    skip_fetch: bool,
) -> tuple[list[str] | None, str | None]:
    """Filenames present under ``migrations_rel`` on ``dev_ref`` RIGHT NOW.

    This is the leg the 2026-08-13 incident needed and neither the on-disk
    scan nor the local-branch scan (`_migration_branch_claims`) provides: a
    migration MERGED (and deployed) by a parallel worktree is invisible to
    ``ls migrations/`` in a worktree that has not rebased, and invisible to
    `git diff origin/dev...<branch>` too — that diff is relative to the
    merge-base, so it only shows what a LOCAL branch added, never what
    `origin/dev` itself gained after the branch forked. Reading `dev_ref`'s
    tree directly, after a fresh fetch, is the only source that answers
    "what is actually merged, right now" independent of this worktree's own
    rebase state.

    Best-effort: a fetch failure (offline) degrades to whatever `dev_ref`
    already resolves to locally (or to "no signal" if it doesn't resolve at
    all) — this function NEVER raises and NEVER silently pretends nothing is
    wrong; a degradation always returns a warning string as the second
    element.
    """
    import subprocess

    if not skip_fetch:
        try:
            subprocess.run(
                ["git", "fetch", "origin", "--quiet"],
                cwd=repo_root, capture_output=True, timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            # Non-fatal — fall through and try ls-tree against whatever
            # `dev_ref` already resolves to locally.
            pass
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", dev_ref, "--", migrations_rel],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return None, f"git unavailable — could not read {dev_ref}"
    if result.returncode != 0:
        return None, (
            f"{dev_ref} did not resolve (no git repo, no such ref, or fetch "
            f"failed and no cached copy exists) — this source was skipped"
        )
    names = [line.rsplit("/", 1)[-1] for line in result.stdout.splitlines() if line.strip()]
    return names, None


def next_migration_number(
    product_slug: str,
    *,
    worktree_path: str | Path | None = None,
    products_dir: Path | None = None,
    dev_ref: str = "origin/dev",
    skip_fetch: bool = False,
) -> dict:
    """Compute the next SAFE migration number for a product.

    NOT the naive ``max(NN) + 1`` a plain ``ls migrations/`` gives you — that
    naive computation is exactly what produced two files both numbered `049`
    on 2026-08-13 (a parallel worktree's migration had already merged and
    deployed; this worktree's own directory listing didn't know). Three
    sources are unioned, none of which is sufficient alone:

    1. **This worktree's own ``migrations/`` directory** — the naive signal.
       Catches nothing outside this checkout.
    2. **``origin/dev``, freshly fetched** — the AUTHORITATIVE merged state,
       independent of whether this worktree has rebased. Catches the exact
       2026-08-13 incident (see ``_origin_dev_migration_files``).
    3. **Every LOCAL branch** (git refs are shared across every worktree of
       this one clone — a sibling worktree's branch is a local ref here too)
       diffed against ``origin/dev``. Catches a sibling worktree's
       committed-but-UNPUSHED migration — the 2026-08-03 incident
       ``check_migration_number_collision``'s docstring cites, and the exact
       gap plain ``ls migrations/`` + ``git log origin/dev`` both miss.

    Returns (on success)::

        {
            "product": "<slug>",
            "migrations_dir": "<path>",
            "next_number": 50,
            "claims": [{"number": "049", "file": "049_x.sql", "source": "disk"}, ...],
            "sources_checked": ["disk", "origin/dev", "local-branches"],
            "warnings": [...],   # non-fatal source degradation, e.g. no network
        }

    or ``{"error": str}`` when the product / its migrations dir doesn't
    exist, or when the UNION of all three sources is empty (mirrors
    ``scaffold_migration``'s "empty migrations/ dir" guard — do NOT silently
    propose `1` for a product that should be getting `001_seed.sql` from
    ``noctus.dev.scaffold_product`` instead).

    ``skip_fetch=True`` skips the network round-trip (source 2 falls back to
    whatever ``origin/dev`` already resolves to locally) — for a fast,
    offline-safe answer, or for tests. NEVER raises.
    """
    if not product_slug:
        return {"error": "product_slug must be a non-empty string"}

    base_products_dir, migrations_dir, err = _resolve_migrations_dir(
        product_slug, worktree_path=worktree_path, products_dir=products_dir,
    )
    if err is not None:
        return err
    assert base_products_dir is not None and migrations_dir is not None  # narrows for mypy/readers

    repo_root = (
        resolve_caller_root(worktree_path) if worktree_path is not None
        else base_products_dir.parent
    )

    claims: list[dict] = []
    warnings: list[str] = []

    # ── Source 1: this worktree's own directory ──
    for f in sorted(migrations_dir.glob("*.sql")):
        m = _NN_RE.match(f.name)
        if m:
            claims.append({"number": m.group(1), "file": f.name, "source": "disk"})

    # ── Source 2: origin/dev, freshly fetched ──
    migrations_rel = f"products/{product_slug}/backend/migrations"
    dev_files, dev_warning = _origin_dev_migration_files(
        repo_root, migrations_rel, dev_ref=dev_ref, skip_fetch=skip_fetch,
    )
    if dev_warning:
        warnings.append(dev_warning)
    for name in dev_files or []:
        m = _NN_RE.match(name)
        if m:
            claims.append({"number": m.group(1), "file": name, "source": dev_ref})

    # ── Source 3: every local branch (sibling worktrees share this .git) ──
    try:
        from .compliance import _migration_branch_claims
        branch_claims = _migration_branch_claims(repo_root, _NN_RE, dev_ref=dev_ref)
    except Exception as exc:  # pragma: no cover - defensive; see _migration_branch_claims contract
        branch_claims = {}
        warnings.append(f"local-branch scan unavailable: {exc}")
    for (directory, number), by_name in branch_claims.items():
        if directory != migrations_rel:
            continue
        for name, branches in by_name.items():
            claims.append({
                "number": number,
                "file": name,
                "source": f"branch:{','.join(sorted(branches))}",
            })

    if not claims:
        return {
            "error": (
                f"Product '{product_slug}' has an empty migrations/ directory "
                f"and no migrations found on {dev_ref} or any local branch. "
                f"Scaffold the product first via noctus.dev.scaffold_product — "
                f"it ships 001_seed.sql, after which subsequent migrations land "
                f"via this tool."
            )
        }

    next_n = max(int(c["number"]) for c in claims) + 1

    return {
        "product": product_slug,
        "migrations_dir": str(migrations_dir),
        "next_number": next_n,
        "claims": sorted(claims, key=lambda c: (c["number"], c["file"], c["source"])),
        "sources_checked": ["disk", dev_ref, "local-branches"],
        "warnings": warnings,
    }


def _build_with_table_block(schema: str, table: str) -> str:
    """Emit a CREATE TABLE skeleton + updated_at_function + trigger + RLS policy hook.

    Idempotency: ``updated_at_function(schema)`` uses ``CREATE OR REPLACE``
    inside the helper, so emitting it again is safe (per-schema, the function
    converges to the same body). The trigger uses ``CREATE OR REPLACE TRIGGER``
    for the same reason.
    """
    table_ddl = (
        f"CREATE TABLE IF NOT EXISTS {schema}.{table} (\n"
        f"    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        f"    -- TODO: add columns here\n"
        f"    created_at timestamptz NOT NULL DEFAULT now(),\n"
        f"    updated_at timestamptz NOT NULL DEFAULT now()\n"
        f");"
    )

    rls_enable = (
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;"
    )

    rls_policy_stub = rls_subquery_policy(
        schema,
        table,
        f"{table}_select_own",
        "SELECT",
        using="(SELECT auth.uid()) IS NOT NULL  -- TODO: tighten to ownership predicate",
    )

    return "\n\n".join(
        [
            f"-- ----- Table: {schema}.{table} -----",
            table_ddl,
            "-- updated_at trigger wiring (idempotent — function uses CREATE OR REPLACE)",
            updated_at_function(schema),
            updated_at_trigger(schema, table),
            "-- Row-Level Security",
            rls_enable,
            rls_policy_stub,
        ]
    )


def _build_updated_at_block(schema: str, tables: list[str]) -> str:
    """Emit one function declaration + N trigger blocks for ``tables``.

    The function lives once per migration (CREATE OR REPLACE — idempotent),
    and each table gets its own ``CREATE OR REPLACE TRIGGER`` block via
    :func:`noctusai_lib.sql.updated_at_trigger` with
    ``include_function=False`` so the function is declared exactly once.
    """
    sections: list[str] = [
        "-- ----- updated_at auto-touch (function + per-table triggers) -----",
        # First trigger emission carries the function declaration.
        sql_updated_at_trigger(tables[0], schema=schema),
    ]
    # Subsequent triggers reuse the function declared above.
    for table in tables[1:]:
        sections.append(
            sql_updated_at_trigger(table, schema=schema, include_function=False)
        )
    return "\n\n".join(sections)


def _build_sql(
    *,
    migration_name: str,
    schema: str,
    with_table: str | None,
    with_updated_at: list[str] | None,
    today_str: str,
) -> str:
    """Build the full SQL body for the new migration file."""
    header = (
        f"-- Migration: {migration_name}\n"
        f"-- Generated by noctus.dev.scaffold_migration on {today_str}\n"
        f"-- Schema: {schema}\n"
    )
    # `noctusai_lib.sql.prelude` bundles the schema-lock with a why-block
    # (RLS isolation, cross-product safety) and a trailing newline. Strip
    # the trailing newline here because we re-join with `\n\n` below.
    prelude = sql_prelude(schema).rstrip("\n")
    helpers_comment = (
        "-- =======================================================\n"
        "-- TODO: Add your DDL here. Patterns available:\n"
        "--   updated_at_function(schema)     -- emit once per schema\n"
        "--   updated_at_trigger(schema, table) -- per table that has updated_at\n"
        "--   rls_subquery_policy(table, ...)  -- per RLS-enabled table\n"
        "-- See seed/lib/backend/noctusai_lib/domain/sql_templates.py\n"
        "-- ======================================================="
    )

    parts = [header, prelude, helpers_comment]
    if with_table:
        parts.append(_build_with_table_block(schema, with_table))
    if with_updated_at:
        parts.append(_build_updated_at_block(schema, with_updated_at))
    return "\n\n".join(parts) + "\n"


def scaffold_migration(
    product_slug: str,
    migration_name: str,
    *,
    schema: str | None = None,
    with_table: str | None = None,
    with_updated_at: list[str] | None = None,
    worktree_path: str | Path | None = None,
    products_dir: Path | None = None,
    skip_fetch: bool = False,
) -> dict:
    """Emit the next-numbered migration SQL file for ``<product_slug>``.

    Args:
        product_slug: Product directory name under ``products/`` (e.g.
            ``youtube-crawler``, ``personal-finance``).
        migration_name: Snake-case-ish suffix for the file (e.g.
            ``oauth_credentials``). Used in the filename + header comment.
        schema: Schema name to bind ``set_search_path`` and emit table DDL
            against. Defaults to ``product_slug.replace("-", "_")``.
        with_table: Optional table name. When set, the emitted SQL includes
            a ``CREATE TABLE IF NOT EXISTS`` skeleton + idempotent
            ``updated_at_function`` + ``updated_at_trigger`` + a
            ``rls_subquery_policy`` stub. Convenient for the common case
            "add a new table".
        with_updated_at: Optional list of table names. When set, appends
            an ``updated_at`` function + per-table BEFORE-UPDATE trigger
            block via :func:`noctusai_lib.sql.updated_at_trigger`. The
            function is declared exactly once (CREATE OR REPLACE — idempotent),
            triggers attach to each named table. Convenient when adding
            ``updated_at`` auto-touch to several existing tables in one
            migration.
        worktree_path: **Caller-aware path resolution.** When set, the
            migration is emitted under the given worktree's
            ``products/<slug>/backend/migrations/`` instead of the MCP
            server's startup workspace. Engineers in a git worktree pass
            their worktree root; architects on main noc omit. See
            ``resolve_caller_root`` + ``KB § PATTERNS/mcp-tool-conventions.md``.
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to ``<worktree_path or server-startup>/products``.
            Tests pass tmp_path-based dirs; the MCP tool registration leaves
            it as None so the worktree-aware default wins.
        skip_fetch: Skip the ``git fetch origin`` round-trip inside the
            number computation (see ``next_migration_number``). Off by
            default — correctness (seeing a sibling worktree's already-merged
            migration) outweighs the network round-trip cost for an
            authoring-time call. Set True for a fast offline-safe scaffold.

    Returns ``{"created": True, "path": str, "number": int, "schema": str,
    "warnings": list[str]}`` on success, or ``{"error": str}`` on failure.
    ``warnings`` is normally empty; it carries a note when the number
    computation degraded (e.g. no network for the ``origin/dev`` fetch) — the
    file still gets the best available number, but with reduced confidence
    from that one source. NEVER raises — the caller (MCP server) is meant to
    surface the error string verbatim.
    """
    if not product_slug:
        return {"error": "product_slug must be a non-empty string"}
    if not migration_name:
        return {"error": "migration_name must be a non-empty string"}
    if with_updated_at is not None:
        if not isinstance(with_updated_at, list):
            return {
                "error": (
                    "with_updated_at must be a list of table names, "
                    f"got {type(with_updated_at).__name__}"
                )
            }
        if any(not isinstance(t, str) or not t.strip() for t in with_updated_at):
            return {
                "error": "with_updated_at entries must be non-empty strings"
            }

    base_products_dir, migrations_dir, err = _resolve_migrations_dir(
        product_slug, worktree_path=worktree_path, products_dir=products_dir,
    )
    if err is not None:
        return err
    assert base_products_dir is not None and migrations_dir is not None

    # Correct-by-construction numbering: `scaffold_migration` is the
    # canonical authoring entrypoint, so it must not carry its own naive
    # max(NN)+1 — that WAS the bug (an engineer who never separately ran
    # `noctus.dev.next_migration_number` or the pre-commit keeper got a wrong
    # number from the moment they scaffolded, undetected until the tech-lead's
    # eventual commit). Delegating here means using the standard tool is
    # sufficient; no extra step to remember.
    number_result = next_migration_number(
        product_slug,
        worktree_path=worktree_path,
        products_dir=products_dir,
        skip_fetch=skip_fetch,
    )
    if "error" in number_result:
        return number_result
    next_n = number_result["next_number"]
    warnings = number_result["warnings"]

    resolved_schema = schema if schema is not None else _slug_to_default_schema(product_slug)
    if not resolved_schema:
        return {"error": "Resolved schema is empty (slug derived to '')"}

    filename = f"{_format_number(next_n)}_{migration_name}.sql"
    target = migrations_dir / filename
    if target.exists():
        # Defensive — next_migration_number already advances past every
        # claimed NN across disk/origin-dev/local-branches, so this should be
        # unreachable unless something raced us in the instant between the
        # computation and this write. Surface it explicitly rather than
        # silently overwriting (no-silent-errors rule).
        return {"error": f"Refusing to overwrite existing file at {target}"}

    sql_body = _build_sql(
        migration_name=migration_name,
        schema=resolved_schema,
        with_table=with_table,
        with_updated_at=with_updated_at,
        today_str=date.today().isoformat(),
    )

    try:
        target.write_text(sql_body)
    except OSError as exc:
        logger.warning("scaffold_migration: cannot write %s (%s)", target, exc)
        return {"error": f"Failed to write {target}: {exc}"}

    logger.info(
        "scaffold_migration: created %s (schema=%s, with_table=%s)",
        target,
        resolved_schema,
        with_table,
    )
    return {
        "created": True,
        "path": str(target),
        "number": next_n,
        "schema": resolved_schema,
        "warnings": warnings,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_migration",
        description=(
            "Emit the next-numbered migration SQL file for a product, "
            "pre-wired with set_search_path / updated_at / RLS helpers from "
            "noctusai_lib.domain.sql_templates. The number is computed "
            "correct-by-construction via noctus.dev.next_migration_number "
            "(disk + freshly-fetched origin/dev + every local branch — not "
            "the naive max(NN)+1 that collided twice, 2026-08-03 and "
            "2026-08-13). Pass `worktree_path` when calling from inside a "
            "git worktree so the migration lands in the worktree, not the "
            "MCP server's startup workspace. `skip_fetch=True` for a fast "
            "offline-safe scaffold (skips the origin/dev fetch)."
        ),
    )
    def _scaffold_migration(
        product_slug: str,
        migration_name: str,
        schema: str | None = None,
        with_table: str | None = None,
        with_updated_at: list[str] | None = None,
        worktree_path: str | None = None,
        skip_fetch: bool = False,
    ) -> dict:
        return scaffold_migration(
            product_slug,
            migration_name,
            schema=schema,
            with_table=with_table,
            with_updated_at=with_updated_at,
            worktree_path=worktree_path,
            skip_fetch=skip_fetch,
        )

    @server.tool(
        name="noctus.dev.next_migration_number",
        description=(
            "Compute the next SAFE migration number for a product — not the "
            "naive max(NN)+1 that `ls migrations/` gives you. Cross-"
            "references THIS worktree's migrations/ directory, `origin/dev` "
            "(freshly fetched — the authoritative merged state, catches a "
            "migration a PARALLEL worktree already merged that this worktree "
            "hasn't rebased onto — the 2026-08-13 incident), AND every LOCAL "
            "branch (git refs are shared across every worktree of this one "
            "clone, so a sibling worktree's committed-but-unpushed migration "
            "is visible — the 2026-08-03 incident). Read-only: the only "
            "network call is `git fetch`; nothing is written or reserved. "
            "`noctus.dev.scaffold_migration` calls this internally, so a "
            "scaffolded migration is correct by construction — call this "
            "directly only to PREVIEW the number before scaffolding, or to "
            "sanity-check a hand-picked one. Pass `worktree_path` when "
            "calling from inside a git worktree. `skip_fetch=True` for a "
            "fast offline-safe answer (falls back to whatever origin/dev "
            "already resolves to locally)."
        ),
    )
    def _next_migration_number(
        product_slug: str,
        worktree_path: str | None = None,
        skip_fetch: bool = False,
    ) -> dict:
        return next_migration_number(
            product_slug,
            worktree_path=worktree_path,
            skip_fetch=skip_fetch,
        )
