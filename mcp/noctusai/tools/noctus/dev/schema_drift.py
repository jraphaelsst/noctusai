"""noctus.dev.schema_drift — does the live schema actually contain what the
code reads and writes?

THE GAP THIS CLOSES (three real bugs, all found 2026-09-17, all the same
shape):

  1. ``erp.assinaturas.external_id`` — ``assinatura_service.preparar_envio``
     inserted this key for months. No migration ever created the column
     (fixed in ``047_assinaturas_external_id.sql``). Every insert failed.
  2. ``erp.tool_call_audits`` — ``ai_service.py`` + ``audit_hook.py`` write
     rows via the seed ``make_audit_writer``. Migration 030 was authored but
     never *applied* (erp's ``schema_migrations`` ledger was empty — the
     pre-2026-09 phantom-schema bug — so "which migrations ran" was
     unanswerable). Table absent.
  3. ``erp.llm_preferences`` — a live routed page (``App.tsx:283`` →
     ``useLLMPreferences()``) called an endpoint backed by a table whose
     migration (017) referenced ``public.org_members``, a table that has
     NEVER existed in this database, so it could never apply. Table absent
     in every schema. A live dead page.

All three survived because (a) "which migrations are applied" was
unanswerable (now closed — the ledgers are reconciled and
``noctus.dev.migrate_product`` refuses a stale tree), and (b) the products'
test suites run ``MockSupabaseClient(validate_schema=False)``, so a missing
table/column is invisible to tests (``check_mock_schema_validation`` gates
that opt-out — see ``KB § PATTERNS/compliance/testing.md``). This tool
closes the REMAINING question: given a migration set that both parses AND
is fully applied, does the live schema still match?

WHAT "WHAT THE CODE EXPECTS" MEANS HERE
----------------------------------------
Two sources, in order of trust:

  1. **The product's own migration files** (primary, always used) —
     ``products/<slug>/backend/migrations/*.sql``, parsed by
     ``noctusai_lib.testing.migration_parser.parse_files`` — the EXACT same
     parser ``MockSupabaseClient(validate_schema=True)`` uses to validate
     code-under-test against (``noctusai_lib.testing._schema_cache``). Reusing
     it means "what MockSupabaseClient thinks exists" and "what this tool
     compares against the live DB" can never silently diverge into two
     different answers to the same question. A migration is the code's
     OWN declared contract for the DB — a service that writes a column no
     migration ever created (bug #1) is *not* caught by this leg; it is
     caught downstream by ``check_mock_schema_validation`` gating
     ``validate_schema=False`` (see that keeper below) because the mock
     schema cache is built from the SAME parse.

  2. **SQLAlchemy ORM models**, where a product declares them
     (``app/models/*.py`` — currently only the seed ``ToolCallAudit``
     pattern absorbed by erp/core/therapy/daily-life/personal-finance).
     AST-extracted (``__tablename__`` + ``Column(...)`` class attributes),
     NOT executed — the ORM docstrings are explicit that the migration is
     the source of truth and the ORM is a mirror ("never run
     ``Base.metadata.create_all(...)`` against the live DB"). Because it is
     only a mirror, ORM-declared columns that the migration set does NOT
     also declare are their OWN drift class (``orm_migration_drift``) —
     the mirror going stale independent of whether the DB agrees with
     either side.

Both sources are then checked against the LIVE schema via
``information_schema.columns``, using the exact ``SqlExecutor``
Protocol+Fake+Real DI seam ``noctus.dev.migrate_product`` already ships
(``make_sql_executor`` — Supabase Management API, PAT resolved DB-first).

WHAT THIS CHECK CAN SEE
------------------------
  - A table a product's migrations (or ORM) declare that the live schema
    does not have at all (``missing_table``) — this is exactly bugs #2/#3.
  - A column a product's migrations (or ORM) declare on a table that DOES
    exist live, but the live table lacks (``missing_column``).
  - An ORM model declaring a table/column the product's OWN migration set
    does not (``orm_migration_drift``) — the ORM mirror is stale, whether
    or not the live DB happens to agree with it. Runs even with no live-DB
    executor (pure code-vs-code).
  - A product with NEITHER a migrations dir NOR ORM models present — FAIL
    CLOSED: this is an ``undeterminable`` finding, not a silent pass. A
    check that returns "0 findings" because it had nothing to compare is
    indistinguishable from "everything matches" to a caller reading only
    ``status``, and that indistinguishability is precisely the shape that
    let bug #1-3 hide for months.

WHAT THIS CHECK CANNOT SEE (blind spots — always in the ``blind_spots`` key)
------------------------------------------------------------------------------
  - **Bug #1's own shape** (code writes a column no migration ever
    declared) — the migration set agrees with itself, so a migrations-vs-
    live diff sees nothing wrong. That gap is closed by
    ``check_mock_schema_validation`` (a NEW test file is refused if it
    opts a product out of validation without a rationale marker) forcing
    the product's OWN test suite to exercise the real column set against
    every code call site — a different leg of the same slice, not this
    tool.
  - Extra/orphaned tables or columns present in the live schema but not
    declared by any known source — not reported (a manually-added debug
    column is not this class of bug, and reporting it would train
    engineers to ignore the noise).
  - A non-literal ``__table_args__`` schema override (e.g. computed at
    import time rather than a string/dict literal) — the ORM extractor
    falls back to the product's own resolved schema in that case; logged
    as a blind spot, not silently assumed correct.
  - A migration whose DDL shape the regex parser cannot recognize (rare;
    ``migration_parser`` itself warns + omits the table — the SAME
    graceful-degradation ``MockSupabaseClient`` lives with).
  - RLS policies, indexes, constraints, defaults, and types — table/column
    NAME existence only, matching what PostgREST 400s on.

Returns ``{ok, status, product, schema, schema_source, sources_used,
checked_tables, findings, blind_spots, error}``. ``status`` ∈
``'in_sync' | 'drift_detected' | 'not_configured' | 'undeterminable' |
'error'``. Per the ``schema_exposure`` leg's precedent
(``noctus.dev.ensure_schema_exposure``): ``not_configured`` (no PAT
resolves) is surfaced distinctly, and ``noctus.dev.predeploy_check``'s
``schema_drift`` leg treats it as a FAILURE, never a silent skip — "we
couldn't check" must never read as "it's fine" for a gate built specifically
because three things WERE fine-looking and weren't.

KB § PATTERNS/backend/database-rls.md · KB § PATTERNS/compliance/testing.md.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from . import migrate_product as _mp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source 1 — migration-declared schema (reuses noctusai_lib's own parser)
# ---------------------------------------------------------------------------


def _migration_declared_schema(
    product_slug: str, products_dir: Path | None = None
) -> tuple[dict[str, set[str]], bool]:
    """``{qualified_table: {columns}}`` derived from THIS product's own
    ``backend/migrations/*.sql`` — scoped to one product (never the whole
    fleet; ``get_schema_map()``'s cache walks every product, which is right
    for ``MockSupabaseClient`` but wrong for a per-product drift compare).

    Returns ``(schema_map, migrations_dir_found)`` — the second element lets
    the caller distinguish "found the dir, it parsed to zero tables" (real,
    if unusual) from "no migrations dir at all" (an undeterminable finding).
    """
    migrations_dir = _mp._migrations_dir(product_slug, products_dir)
    if not migrations_dir.is_dir():
        return {}, False
    from noctusai_lib.testing.migration_parser import parse_files

    files = sorted(migrations_dir.glob("*.sql"))
    return parse_files(files), True


# ---------------------------------------------------------------------------
# Source 2 — SQLAlchemy ORM models (AST-extracted, never executed)
# ---------------------------------------------------------------------------


def _orm_declared_schema(
    product_slug: str, default_schema: str, products_dir: Path | None = None
) -> tuple[dict[str, set[str]], list[str]]:
    """AST-walk ``app/models/*.py`` for SQLAlchemy declarative models:
    a class with a ``__tablename__ = "..."`` string literal and one or more
    ``<attr> = Column(...)`` assignments in its body. ``__table_args__ =
    {"schema": ...}`` supplies the schema when it is a literal string;
    otherwise (e.g. an imported ``SCHEMA`` name, the seed pattern) falls
    back to ``default_schema`` (the product's own resolved schema — right
    for the seed ``ToolCallAudit`` shape, which always binds to the
    product's own schema) and records a blind spot.

    Returns ``(schema_map, blind_spots)``. Absence of ``app/models/`` is NOT
    a blind spot (most products have no ORM layer at all — the mock-schema
    parser and every routing convention here is deliberately Supabase-
    client-first); an unparseable *present* file is.
    """
    base = products_dir or _PRODUCTS_DIR()
    models_dir = base / product_slug / "backend" / "app" / "models"
    if not models_dir.is_dir():
        return {}, []

    schema_map: dict[str, set[str]] = {}
    blind_spots: list[str] = []
    for path in sorted(models_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError) as exc:
            blind_spots.append(f"{path}: could not parse ({exc}) — ORM tables in this file unknown")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            table = None
            schema = None
            schema_resolved = True
            columns: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    target_names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                    if "__tablename__" in target_names and isinstance(stmt.value, ast.Constant):
                        if isinstance(stmt.value.value, str):
                            table = stmt.value.value
                        continue
                    if "__table_args__" in target_names:
                        schema, schema_resolved = _extract_table_args_schema(stmt.value)
                        continue
                    # <attr> = Column(...) / mapped_column(...)
                    if len(target_names) == 1 and isinstance(stmt.value, ast.Call):
                        callee = stmt.value.func
                        callee_name = (
                            callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
                        )
                        if callee_name in ("Column", "mapped_column"):
                            columns.add(target_names[0])
            if table is None or not columns:
                continue  # not an ORM table declaration (or nothing to compare)
            if not schema_resolved:
                blind_spots.append(
                    f"{path}: {node.name}.__table_args__ schema is not a string literal — "
                    f"assumed product default schema {default_schema!r}"
                )
            qualified = f"{schema or default_schema}.{table}"
            schema_map.setdefault(qualified, set()).update(columns)
    return schema_map, blind_spots


def _extract_table_args_schema(value: ast.expr) -> tuple[str | None, bool]:
    """``__table_args__`` is either a dict literal (``{"schema": "x"}``) or a
    tuple whose last element is that dict (``(Index(...), {"schema": "x"})``).
    Returns ``(schema_or_None, resolved)`` — ``resolved=False`` means a
    schema key was present but its value wasn't a string literal (e.g. an
    imported name), so the caller should fall back + record a blind spot."""
    dict_node: ast.expr | None = None
    if isinstance(value, ast.Dict):
        dict_node = value
    elif isinstance(value, ast.Tuple) and value.elts and isinstance(value.elts[-1], ast.Dict):
        dict_node = value.elts[-1]
    if dict_node is None:
        return None, True
    for key, val in zip(dict_node.keys, dict_node.values):
        if isinstance(key, ast.Constant) and key.value == "schema":
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                return val.value, True
            return None, False
    return None, True


def _PRODUCTS_DIR() -> Path:
    from settings import PRODUCTS_DIR

    return PRODUCTS_DIR


# ---------------------------------------------------------------------------
# Live schema (information_schema.columns via the shared SqlExecutor seam)
# ---------------------------------------------------------------------------


def _live_columns_sql(schema: str) -> str:
    safe = schema.replace("'", "''")
    return (
        "SELECT table_name, column_name FROM information_schema.columns "
        f"WHERE table_schema = '{safe}' ORDER BY table_name, column_name;"
    )


def _rows_to_live_schema(schema: str, rows: list[dict] | None) -> dict[str, set[str]]:
    live: dict[str, set[str]] = {}
    for row in rows or []:
        table = row.get("table_name")
        column = row.get("column_name")
        if not table or not column:
            continue
        live.setdefault(f"{schema}.{table}", set()).add(column)
    return live


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _compare(
    declared: dict[str, set[str]],
    live: dict[str, set[str]],
    *,
    source: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for table, columns in sorted(declared.items()):
        if table not in live:
            findings.append({
                "kind": "missing_table",
                "table": table,
                "column": None,
                "source": source,
                "severity": "high",
                "detail": f"{source} declares {table} but it does not exist in the live schema.",
            })
            continue
        missing_cols = sorted(columns - live[table])
        for col in missing_cols:
            findings.append({
                "kind": "missing_column",
                "table": table,
                "column": col,
                "source": source,
                "severity": "high",
                "detail": f"{source} declares {table}.{col} but the live table lacks that column.",
            })
    return findings


def _compare_orm_vs_migrations(
    orm: dict[str, set[str]], migrations: dict[str, set[str]]
) -> list[dict[str, Any]]:
    """ORM-declared table/column that the migration set does not also
    declare — the ORM mirror drifting from its own stated source of truth.
    Offline (no live DB needed); runs unconditionally."""
    findings: list[dict[str, Any]] = []
    for table, columns in sorted(orm.items()):
        mig_columns = migrations.get(table)
        if mig_columns is None:
            findings.append({
                "kind": "orm_migration_drift",
                "table": table,
                "column": None,
                "source": "orm",
                "severity": "warning",
                "detail": (
                    f"ORM model declares {table} but no migration in this product "
                    "declares that table — the ORM mirror is out of date."
                ),
            })
            continue
        for col in sorted(columns - mig_columns):
            findings.append({
                "kind": "orm_migration_drift",
                "table": table,
                "column": col,
                "source": "orm",
                "severity": "warning",
                "detail": (
                    f"ORM model declares {table}.{col} but no migration in this "
                    "product declares that column — the ORM mirror is out of date."
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def check_schema_drift(
    product: str,
    *,
    executor: "_mp.SqlExecutor | None" = None,
    products_dir: Path | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
) -> dict[str, Any]:
    """Compare `product`'s declared schema (migrations + ORM, where present)
    against the live DB schema. See module docstring for the full CAN/CANNOT
    matrix. Never raises — every failure mode is a typed ``status``.
    """

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ok": status in ("in_sync",),
            "status": status,
            "product": product,
            "schema": None,
            "schema_source": None,
            "sources_used": {"migrations": False, "orm": False},
            "checked_tables": 0,
            "findings": [],
            "blind_spots": [],
            "error": None,
        }
        base.update(overrides)
        return base

    if not product or not product.strip():
        return _result("error", error="product is required")

    schema, schema_source = _mp._resolve_schema(product, None, products_dir)

    migrations_map, migrations_found = _migration_declared_schema(product, products_dir)
    orm_map, orm_blind_spots = _orm_declared_schema(product, schema, products_dir)

    blind_spots = list(orm_blind_spots)
    sources_used = {"migrations": migrations_found, "orm": bool(orm_map)}

    if not migrations_found and not orm_map:
        return _result(
            "undeterminable",
            schema=schema,
            schema_source=schema_source,
            sources_used=sources_used,
            blind_spots=blind_spots,
            findings=[{
                "kind": "undeterminable",
                "table": None,
                "column": None,
                "source": None,
                "severity": "high",
                "detail": (
                    f"{product} has neither a backend/migrations/ directory nor "
                    "app/models/ ORM declarations — this tool cannot determine "
                    "what the live schema should contain. Fail-closed: this is a "
                    "finding, not a pass."
                ),
            }],
            error=f"no schema-expectation source found for {product}",
        )

    declared: dict[str, set[str]] = {t: set(c) for t, c in migrations_map.items()}
    for table, cols in orm_map.items():
        declared.setdefault(table, set()).update(cols)

    # Offline leg — always runs, needs no executor.
    findings: list[dict[str, Any]] = list(_compare_orm_vs_migrations(orm_map, migrations_map))

    # Live-DB leg — needs a working SqlExecutor.
    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)
    if executor is None:
        return _result(
            "not_configured",
            schema=schema,
            schema_source=schema_source,
            sources_used=sources_used,
            checked_tables=len(declared),
            blind_spots=blind_spots,
            findings=findings,
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved — "
                "cannot query information_schema to verify the live schema. Same "
                "resolution path as noctus.dev.migrate_product."
            ),
        )

    fetch = executor.execute(_live_columns_sql(schema))
    if not fetch.get("ok"):
        return _result(
            "error",
            schema=schema,
            schema_source=schema_source,
            sources_used=sources_used,
            checked_tables=len(declared),
            blind_spots=blind_spots,
            findings=findings,
            error="could not read information_schema.columns: " + (fetch.get("error") or "unknown error"),
        )

    live = _rows_to_live_schema(schema, fetch.get("rows"))
    findings += _compare(declared, live, source="migrations+orm" if orm_map else "migrations")

    status = "drift_detected" if findings else "in_sync"
    return _result(
        status,
        schema=schema,
        schema_source=schema_source,
        sources_used=sources_used,
        checked_tables=len(declared),
        blind_spots=blind_spots,
        findings=findings,
    )


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(server) -> None:
    @server.tool(
        name="noctus.dev.schema_drift",
        description=(
            "Does the live DB schema actually contain what the product's code "
            "reads and writes? Compares the product's own migration files "
            "(parsed via the SAME noctusai_lib.testing.migration_parser "
            "MockSupabaseClient(validate_schema=True) uses) plus any SQLAlchemy "
            "ORM models under app/models/ against the live schema via "
            "information_schema.columns (reuses noctus.dev.migrate_product's "
            "SqlExecutor DI seam — Supabase Management API, PAT resolved "
            "DB-first). Reports missing_table / missing_column (live-vs-declared) "
            "and orm_migration_drift (ORM mirror vs migrations, offline, no PAT "
            "needed). A product with neither a migrations/ dir nor ORM models is "
            "'undeterminable' — a finding, never a silent pass. Closes the class "
            "of bug behind erp.assinaturas.external_id / erp.tool_call_audits / "
            "erp.llm_preferences (2026-09-17) — three tables/columns the code "
            "depended on that were never actually in the live DB. Returns {ok, "
            "status, product, schema, schema_source, sources_used, "
            "checked_tables, findings, blind_spots, error}. See module docstring "
            "for the full CAN/CANNOT-see matrix. "
            "KB § PATTERNS/backend/database-rls.md · KB § PATTERNS/compliance/testing.md."
        ),
    )
    def _schema_drift(
        product: str,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
    ) -> dict:
        return check_schema_drift(product, project_ref=project_ref)


__all__ = [
    "check_schema_drift",
    "_migration_declared_schema",
    "_orm_declared_schema",
    "_live_columns_sql",
    "_rows_to_live_schema",
    "_compare",
    "_compare_orm_vs_migrations",
    "register",
]
