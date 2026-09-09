"""noctus.dev.migrate_product — apply a product's SQL migrations to Supabase.

WHY THIS TOOL EXISTS
--------------------
Today, applying ``products/<slug>/backend/migrations/NNN_*.sql`` to the shared
Supabase project is a hand-piped procedure: open each file, copy the SQL, paste
into the Supabase MCP ``apply_migration`` or ``db.query``, confirm, repeat.
Done ~8× in a single session during product launches.

This tool automates the whole cycle:

    1. Read ``products/<slug>/backend/migrations/*.sql`` sorted by numeric prefix.
    2. Query ``<schema>.schema_migrations`` (created on first run) to find
       which files are already applied.
    3. In **dry-run** (default, ``confirm=False``): list pending vs. applied.
    4. With ``confirm=True``: apply each un-applied file in order, recording
       ``(filename, checksum)`` in ``schema_migrations`` after each success.
       Idempotent — re-running skips already-applied files.

EXEC MECHANISM
--------------
The Supabase Management API ``POST /v1/projects/{ref}/database/query`` can
run arbitrary SQL (including DDL — ``CREATE TABLE``, ``CREATE SCHEMA``, etc.).
The ``mcp/supabase`` connector uses the same endpoint; we reuse the urllib-based
pattern from ``sso_smoke`` (stdlib only, no extra dep) rather than importing
the ``mcp/supabase`` connector's private ``api.py``.

**Credential:** the Supabase Personal Access Token (PAT), resolved DB-first via
the seed ``resolve_credential`` seam (dev=.env / prod=DB): DB
``platform_settings['supabase_access_token']`` (global scope) → env
``SUPABASE_ACCESS_TOKEN`` (Tier 3, same ``.env`` that holds ``SUPABASE_URL`` /
``SUPABASE_SERVICE_ROLE_KEY``). If none resolves, the tool returns
``status='not_configured'`` with a ``NOC-REMEDIATE`` block; the tool is fully
testable via the Fake seam.

**IO SEAM (Protocol + Fake + Real)**
We follow ``KB § PATTERNS/backend/seed-fake-real-adapter.md``:

  - ``SqlExecutor`` Protocol: ``execute(sql) -> ExecuteResult``
  - ``FakeSqlExecutor``: in-memory; used by tests.
  - ``SupabaseMgmtExecutor``: calls the Management API; used by the live tool.
  - ``make_sql_executor(access_token, project_ref)`` factory — picks Real when
    the token is present, surfaces the missing-credential shape otherwise.

TRACKING TABLE
--------------
``<schema>.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now(), checksum TEXT)``

Created automatically on first run via the executor (a pure DDL statement).

SCHEMA DERIVATION (fixed 2026-09 — was ``slug.replace("-", "_")`` always,
which silently wrote the ledger to a phantom schema for any product whose
declared schema doesn't equal the naive slug transform: ``erp-imobiliario``
declares ``schema="erp"``, ``therapy-platform`` declares ``schema="therapy"``,
and ``personal-finance`` declares the *hyphenated* ``schema="personal-finance"``
— none of which equal their slug-transform. The DDL itself always landed
correctly, because every migration's own ``SET search_path = <real-schema>``
routes it; only this tool's bookkeeping went to the wrong address, so three
products' ``schema_migrations`` ledgers under-reported for months while the
tables they claimed to track didn't exist at that address at all.)

Precedence, per ``_resolve_schema()``:
  1. explicit ``schema=`` arg (unchanged escape hatch)
  2. **derived** from the product's own ``app/main.py``: every product
     declares its schema once, as the ``schema="..."`` keyword literal on its
     ``create_product_app(...)`` call — the same declaration ``create_database_module``
     reads and every migration's ``SET search_path`` targets. AST-parsed, not
     regexed (`KB § PATTERNS/common/ast.md`), so this is a real derivation off
     the single authoritative source, never a hand-maintained slug→schema map.
  3. fallback: the historical ``slug.replace("-", "_")`` transform — used only
     when no product declares a schema (main.py missing/unparseable/no literal
     kwarg). The result payload's ``schema_source`` field says which path fired
     (``explicit_override`` / ``main_py_declaration`` / ``slug_fallback``) so a
     fallback never masquerades as a verified derivation.

Schema identifiers are always double-quoted in generated SQL (``_quote_ident``)
— required for ``personal-finance`` (a hyphen is not a valid unquoted Postgres
identifier character) and harmless for every other schema.

IDEMPOTENCY
-----------
- Tracking table creation uses ``CREATE TABLE IF NOT EXISTS``.
- Each file is applied only when its ``filename`` is absent from
  ``schema_migrations`` (primary-key guard also prevents double-insert).
- Re-running with ``confirm=True`` on a fully-applied set is a no-op.
- ``target=`` (optional) limits to one specific file by filename match.

RETURN SHAPE
------------
``{
    status: 'dry_run' | 'applied' | 'up_to_date' | 'not_configured' | 'error',
    product: str,
    schema: str,
    schema_source: 'explicit_override' | 'main_py_declaration' | 'slug_fallback',
    project_ref: str,
    applied: list[str],
    skipped_already_applied: list[str],
    pending: list[str],
    error: str | None,
}``

REPAIR MODE — ``repair_schema_migrations_ledger()``
----------------------------------------------------
Moves ``schema_migrations`` rows stranded in a phantom schema (written back
when this tool used the naive slug transform unconditionally) to the real
schema. DRY-RUN by default; ``confirm=True`` required to write. Idempotent
(``ON CONFLICT (filename) DO NOTHING`` on the copy). See its docstring for
the full contract. Registered as ``noctus.dev.repair_migration_ledger``.

KB § PATTERNS/backend/migrate-product-mcp-tool.md
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from settings import PRODUCTS_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex: numeric migration prefix — matches NNN_<rest>.sql where NNN is 1+ digits.
# ---------------------------------------------------------------------------
_NN_RE = re.compile(r"^(\d+)_.+\.sql$")

# Supabase Management API — same endpoint as mcp/supabase/tools/db.py uses.
_SUPABASE_MGMT_BASE = "https://api.supabase.com"
_UA = "noctusai-migrate-product/1.0"

# Env var that holds the PAT (readable from the noctusai MCP's own .env).
_ACCESS_TOKEN_VAR = "SUPABASE_ACCESS_TOKEN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_to_schema(product_slug: str) -> str:
    """``erp-imobiliario`` → ``erp_imobiliario`` (naive fallback transform).

    NOT the source of truth — see ``_resolve_schema``. Wrong for any product
    whose declared schema differs from its slug transform (``erp-imobiliario``
    → ``erp``, ``therapy-platform`` → ``therapy``, ``personal-finance`` →
    itself, hyphen and all). Kept as the last-resort fallback for a product
    that declares no schema at all.
    """
    return product_slug.replace("-", "_")


def _quote_ident(name: str) -> str:
    """Double-quote a Postgres identifier (schema/table name).

    Required for any schema containing a character invalid in an unquoted
    identifier — ``personal-finance``'s hyphen being the concrete case that
    forced this: ``CREATE SCHEMA IF NOT EXISTS personal-finance`` is not
    ``CREATE SCHEMA personal-finance``, it is ``CREATE SCHEMA personal`` minus
    a bareword `finance`, a syntax error. Doubling an embedded ``"`` (the
    standard Postgres escape) keeps this safe even though no current schema
    name needs it. Quoting an already-safe identifier like ``erp`` is a no-op
    behaviourally, so this is applied unconditionally rather than only to the
    schemas known (today) to need it.
    """
    return '"' + name.replace('"', '""') + '"'


def _schema_from_main_py(
    product_slug: str, products_dir: Path | None = None
) -> str | None:
    """AST-derive the product's declared schema from its own ``app/main.py``.

    Every product declares its schema exactly once, as the ``schema="..."``
    keyword literal on its ``create_product_app(...)`` call (the same call
    that wires routers, auth, and — transitively, via
    ``create_database_module`` — every RLS-scoped query). That single
    declaration is the authoritative source this function reads; nothing
    here is a hand-maintained slug→schema map (`CLAUDE.md` §1 "derive, don't
    sync by hand").

    AST-parsed per `KB § PATTERNS/common/ast.md` — not regexed, so a
    multi-line ``create_product_app(\\n    name=...,\\n    schema="erp",``
    call (every real product's shape) is found regardless of formatting.

    Returns ``None`` when ``main.py`` is missing, fails to parse, has no
    ``create_product_app`` call, or that call's ``schema`` keyword isn't a
    literal string (e.g. computed) — callers fall back to
    ``_slug_to_schema`` in that case and must say so via ``schema_source``.
    """
    base = products_dir or PRODUCTS_DIR
    main_py = base / product_slug / "backend" / "app" / "main.py"
    if not main_py.exists():
        return None
    try:
        source = main_py.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(main_py))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        logger.debug(
            "migrate_product: could not parse %s for schema derivation: %s",
            main_py,
            exc,
        )
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if func_name != "create_product_app":
            continue
        for kw in node.keywords:
            if kw.arg != "schema":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
            # schema= present but not a literal string (e.g. a variable) —
            # can't derive without executing the module; fall through to
            # the slug-transform fallback rather than guessing.
            return None
    return None


def _resolve_schema(
    product_slug: str,
    schema_override: str | None,
    products_dir: Path | None = None,
) -> tuple[str, str]:
    """Resolve the real DB schema for ``product_slug`` + say HOW it was resolved.

    Precedence: explicit override → declared in the product's own main.py →
    naive slug-transform fallback (see module docstring "SCHEMA DERIVATION").

    Returns ``(schema, schema_source)`` where ``schema_source`` is one of
    ``'explicit_override' | 'main_py_declaration' | 'slug_fallback'`` — every
    caller threads this into the result payload so a fallback is never
    silently indistinguishable from a verified derivation (no-silent-errors).
    """
    if schema_override:
        return schema_override, "explicit_override"
    declared = _schema_from_main_py(product_slug, products_dir)
    if declared:
        return declared, "main_py_declaration"
    return _slug_to_schema(product_slug), "slug_fallback"


def _migrations_dir(product_slug: str, products_dir: Path | None = None) -> Path:
    base = products_dir or PRODUCTS_DIR
    return base / product_slug / "backend" / "migrations"


def _sorted_migrations(migrations_dir: Path) -> list[Path]:
    """Return .sql files sorted by their leading numeric prefix.

    Files that don't match ``NNN_*.sql`` are silently skipped (logged at
    DEBUG) — they may be scratch files or comments.
    """
    files = []
    for f in migrations_dir.iterdir():
        if not f.is_file() or not f.suffix == ".sql":
            continue
        m = _NN_RE.match(f.name)
        if m:
            files.append((int(m.group(1)), f))
        else:
            logger.debug(
                "migrate_product: skipping non-numbered file %s",
                f.name,
            )
    files.sort(key=lambda x: x[0])
    return [f for _, f in files]


def _checksum(sql: str) -> str:
    """SHA-256 hex digest of the migration SQL content."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# SqlExecutor Protocol + Fake + Real
# ---------------------------------------------------------------------------


@runtime_checkable
class SqlExecutor(Protocol):
    """Narrow DI seam: execute a single SQL statement against the target DB.

    Returns ``{"ok": bool, "rows": list[dict] | None, "error": str | None}``.
    """

    def execute(self, sql: str) -> dict[str, Any]:
        ...  # pragma: no cover


class FakeSqlExecutor:
    """In-memory executor for unit tests.

    ``preset_rows`` maps a SQL-fragment substring to the list of row-dicts
    that the executor should return when that substring appears in the SQL.
    The first matching key wins; no match → ``[]``.

    ``executed`` accumulates every SQL string passed to ``execute``.
    ``fail_on`` is a set of SQL fragments; matching calls return
    ``{"ok": False, "error": "fake-failure"}``.
    """

    def __init__(
        self,
        *,
        preset_rows: dict[str, list[dict]] | None = None,
        fail_on: set[str] | None = None,
    ) -> None:
        self.preset_rows: dict[str, list[dict]] = preset_rows or {}
        self.fail_on: set[str] = fail_on or set()
        self.executed: list[str] = []

    def execute(self, sql: str) -> dict[str, Any]:
        self.executed.append(sql)
        for frag in self.fail_on:
            if frag in sql:
                return {"ok": False, "rows": None, "error": "fake-failure"}
        for key, rows in self.preset_rows.items():
            if key in sql:
                return {"ok": True, "rows": rows, "error": None}
        return {"ok": True, "rows": [], "error": None}


class SupabaseMgmtExecutor:
    """Real executor: calls ``POST /v1/projects/{ref}/database/query``.

    Uses stdlib urllib (no extra deps beyond what sso_smoke uses). Maps to
    the exact HTTP shape that ``mcp/supabase/tools/db.py`` uses — same
    endpoint, same auth header, same response parsing.
    """

    def __init__(self, *, access_token: str, project_ref: str) -> None:
        self._token = access_token
        self._ref = project_ref

    def execute(self, sql: str) -> dict[str, Any]:
        url = f"{_SUPABASE_MGMT_BASE}/v1/projects/{self._ref}/database/query"
        body = json.dumps({"query": sql}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                rows = json.loads(raw) if raw else []
                if not isinstance(rows, list):
                    rows = [rows] if isinstance(rows, dict) else []
                return {"ok": True, "rows": rows, "error": None}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode(errors="replace")
            except Exception:
                pass
            logger.error(
                "migrate_product: Supabase API %s — %s %s",
                exc.code,
                exc.reason,
                detail[:300],
            )
            return {
                "ok": False,
                "rows": None,
                "error": f"HTTP {exc.code} {exc.reason}: {detail[:200]}",
            }
        except Exception as exc:
            logger.error("migrate_product: network error — %s", exc)
            return {"ok": False, "rows": None, "error": str(exc)}


def _resolve_access_token(access_token: str | None = None) -> str:
    """Resolve the Supabase Management-API PAT DB-first (dev=.env / prod=DB).

    Order (via the seed ``resolve_credential`` seam): explicit arg → DB
    ``platform_settings['supabase_access_token']`` (global/platform scope) → env
    ``SUPABASE_ACCESS_TOKEN`` (Tier 3). The DB tiers require the resolver to be
    bootstrapped with the MCP's own service-role creds (already in the MCP
    ``.env`` as SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY); we do that once here.
    Any failure degrades to the plain env read so the dev path never regresses.
    """
    if access_token:
        return access_token
    try:
        from noctusai_lib.config.credentials import (
            configure_credentials,
            resolve_credential,
        )
        from settings import get_settings

        s = get_settings()
        if s.supabase_url and s.supabase_service_role_key:
            configure_credentials(
                supabase_url=s.supabase_url,
                supabase_anon_key=s.supabase_anon_key or "",
                supabase_service_role_key=s.supabase_service_role_key,
            )
        # org_id=None → skips per-org Tier 1, reads platform_settings (Tier 2),
        # then env SUPABASE_ACCESS_TOKEN (Tier 3) for free.
        token = resolve_credential("supabase_access_token")
        if token:
            return token
    except Exception as exc:  # pragma: no cover — defensive bootstrap
        logger.debug(
            "DB-first supabase_access_token resolution failed; env fallback: %s", exc
        )
    return os.environ.get(_ACCESS_TOKEN_VAR, "")


def make_sql_executor(
    *,
    access_token: str | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
) -> SqlExecutor | None:
    """Factory — returns the Real executor when credentials are present.

    The PAT is resolved DB-first via :func:`_resolve_access_token` (DB
    ``platform_settings`` → env). Returns ``None`` when no token resolves;
    callers surface the ``not_configured`` shape with a ``NOC-REMEDIATE`` message.
    """
    token = _resolve_access_token(access_token)
    if not token:
        return None
    return SupabaseMgmtExecutor(access_token=token, project_ref=project_ref)


# ---------------------------------------------------------------------------
# Tracking-table DDL
# ---------------------------------------------------------------------------


def _ensure_tracking_table_sql(schema: str) -> str:
    """DDL to create the schema_migrations tracking table (idempotent)."""
    q = _quote_ident(schema)
    return (
        f"CREATE SCHEMA IF NOT EXISTS {q};\n"
        f"CREATE TABLE IF NOT EXISTS {q}.schema_migrations (\n"
        f"    filename   TEXT        PRIMARY KEY,\n"
        f"    applied_at TIMESTAMPTZ DEFAULT now() NOT NULL,\n"
        f"    checksum   TEXT        NOT NULL\n"
        f");"
    )


def _fetch_applied_sql(schema: str) -> str:
    """SELECT to retrieve all applied migration filenames."""
    q = _quote_ident(schema)
    return (
        f"SELECT filename FROM {q}.schema_migrations ORDER BY filename;"
    )


def _record_migration_sql(schema: str, filename: str, checksum: str) -> str:
    """INSERT to record an applied migration (conflict = already applied)."""
    q = _quote_ident(schema)
    safe_filename = filename.replace("'", "''")
    safe_checksum = checksum.replace("'", "''")
    return (
        f"INSERT INTO {q}.schema_migrations (filename, checksum) "
        f"VALUES ('{safe_filename}', '{safe_checksum}') "
        f"ON CONFLICT (filename) DO NOTHING;"
    )


def _schema_migrations_exists_sql(schema: str) -> str:
    """SELECT probe: does ``<schema>.schema_migrations`` exist at all?

    Uses ``to_regclass`` (returns NULL, not an error, for a missing
    schema/table) so callers can safely check existence before SELECTing —
    a phantom schema that was never created (a product that has always used
    the correct schema, e.g. ``orbity``) must read as "nothing to repair",
    not as a query error.
    """
    # to_regclass takes the dotted name as a *string literal* — the schema
    # portion is double-quoted inside that literal (mirrors _quote_ident) so
    # a hyphenated schema like "personal-finance" resolves correctly.
    literal = (f'"{schema}".schema_migrations').replace("'", "''")
    return f"SELECT to_regclass('{literal}') IS NOT NULL AS exists_;"


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def migrate_product(
    product: str,
    *,
    confirm: bool = False,
    target: str | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    schema: str | None = None,
    executor: SqlExecutor | None = None,
    products_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply pending migrations for ``product`` to the Supabase database.

    Args:
        product:      Product slug (e.g. ``orbity``, ``erp-imobiliario``).
        confirm:      False (default) = dry-run (list pending; no DDL run).
                      True = apply all pending files in order.
        target:       Optional filename filter — apply / list only this file.
        project_ref:  Supabase project reference (default: noctusai production).
        schema:       Override the auto-derived schema. When omitted, the
                      schema is DERIVED from the product's own
                      ``create_product_app(schema="...")`` declaration (see
                      ``_resolve_schema`` / module docstring "SCHEMA
                      DERIVATION") — not the naive slug transform.
        executor:     Injection seam for tests (``FakeSqlExecutor``).
                      When None, resolved from env via ``make_sql_executor``.
        products_dir: Override ``PRODUCTS_DIR`` (injection seam for tests).

    Returns a dict with keys::

        status, product, schema, schema_source, project_ref, applied,
        skipped_already_applied, pending, error
    """
    derived_schema, schema_source = _resolve_schema(product, schema, products_dir)

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "status": status,
            "product": product,
            "schema": derived_schema,
            "schema_source": schema_source,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": None,
        }
        base.update(overrides)
        return base

    # ── Resolve executor ──────────────────────────────────────────────────────
    if executor is None:
        executor = make_sql_executor(project_ref=project_ref)
    if executor is None:
        # NOC-REMEDIATE[credentials]: no supabase_access_token resolved.
        # Store it DB-first (preferred): platform_settings['supabase_access_token']
        # (global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env.
        # Create the PAT at: https://supabase.com/dashboard/account/tokens — 2026-07-27
        return _result(
            "not_configured",
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Store it DB-first in platform_settings (key='supabase_access_token', "
                "global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env. "
                "Create the PAT at: https://supabase.com/dashboard/account/tokens"
            ),
        )

    # ── Resolve migrations directory ──────────────────────────────────────────
    mig_dir = _migrations_dir(product, products_dir)
    if not mig_dir.exists():
        return _result("error", error=f"migrations directory not found: {mig_dir}")

    all_files = _sorted_migrations(mig_dir)
    if not all_files:
        return _result("up_to_date")

    # ── Apply optional target filter ──────────────────────────────────────────
    if target is not None:
        all_files = [f for f in all_files if f.name == target]
        if not all_files:
            return _result("error", error=f"target file not found in migrations: {target!r}")

    # ── Ensure tracking table exists ──────────────────────────────────────────
    ensure_sql = _ensure_tracking_table_sql(derived_schema)
    ensure_result = executor.execute(ensure_sql)
    if not ensure_result.get("ok"):
        logger.error(
            "migrate_product: failed to ensure tracking table for %s: %s",
            product,
            ensure_result.get("error"),
        )
        return _result(
            "error",
            error=(
                f"could not create tracking table {derived_schema}.schema_migrations: "
                + (ensure_result.get("error") or "unknown error")
            ),
        )

    # ── Fetch already-applied filenames ───────────────────────────────────────
    fetch_result = executor.execute(_fetch_applied_sql(derived_schema))
    if not fetch_result.get("ok"):
        logger.error(
            "migrate_product: failed to query schema_migrations for %s: %s",
            product,
            fetch_result.get("error"),
        )
        return _result(
            "error",
            error=(
                f"could not query {derived_schema}.schema_migrations: "
                + (fetch_result.get("error") or "unknown error")
            ),
        )

    already_applied: set[str] = set()
    for row in fetch_result.get("rows") or []:
        if isinstance(row, dict):
            fn = row.get("filename")
            if fn:
                already_applied.add(fn)

    # ── Classify: pending vs. skipped ────────────────────────────────────────
    skipped: list[str] = []
    pending: list[Path] = []
    for f in all_files:
        if f.name in already_applied:
            skipped.append(f.name)
        else:
            pending.append(f)

    pending_names = [f.name for f in pending]

    if not confirm:
        return _result(
            "dry_run",
            skipped_already_applied=skipped,
            pending=pending_names,
        )

    # ── Apply pending files in order ──────────────────────────────────────────
    if not pending:
        return _result("up_to_date", skipped_already_applied=skipped)

    newly_applied: list[str] = []
    for mig_file in pending:
        sql = mig_file.read_text(encoding="utf-8")
        csum = _checksum(sql)

        logger.info("migrate_product: applying %s …", mig_file.name)
        result = executor.execute(sql)
        if not result.get("ok"):
            logger.error(
                "migrate_product: failed to apply %s: %s",
                mig_file.name,
                result.get("error"),
            )
            return _result(
                "error",
                applied=newly_applied,
                skipped_already_applied=skipped,
                pending=[f.name for f in pending if f.name not in newly_applied],
                error=f"migration {mig_file.name} failed: " + (result.get("error") or "unknown"),
            )

        # Record the applied migration
        record_sql = _record_migration_sql(derived_schema, mig_file.name, csum)
        rec_result = executor.execute(record_sql)
        if not rec_result.get("ok"):
            logger.warning(
                "migrate_product: migration %s applied but tracking INSERT failed: %s",
                mig_file.name,
                rec_result.get("error"),
            )
            # Non-fatal: the DDL ran; warn and continue.

        newly_applied.append(mig_file.name)
        logger.info("migrate_product: applied %s ✓", mig_file.name)

    return _result(
        "applied",
        applied=newly_applied,
        skipped_already_applied=skipped,
    )


# ---------------------------------------------------------------------------
# Ledger repair — move phantom-schema rows to the real schema
# ---------------------------------------------------------------------------


def _copy_ledger_rows_sql(from_schema: str, to_schema: str) -> str:
    """INSERT..SELECT to copy every ``schema_migrations`` row between schemas.

    ``ON CONFLICT (filename) DO NOTHING`` makes this idempotent AND safe: a
    filename already present in the target (e.g. correctly re-applied after
    the derivation bug was fixed) is left exactly as-is — a phantom row can
    never overwrite a real one, only fill a genuine gap.
    """
    qf = _quote_ident(from_schema)
    qt = _quote_ident(to_schema)
    return (
        f"INSERT INTO {qt}.schema_migrations (filename, applied_at, checksum) "
        f"SELECT filename, applied_at, checksum FROM {qf}.schema_migrations "
        f"ON CONFLICT (filename) DO NOTHING;"
    )


def _delete_phantom_ledger_rows_sql(from_schema: str, filenames: list[str]) -> str:
    """DELETE the just-copied rows from the phantom schema's tracking table.

    Scoped to the EXACT filenames this run moved (never a bare
    ``TRUNCATE``/``DELETE FROM``-without-``WHERE``) — a phantom row that
    failed to copy, or a filename outside this run's move-set, must never be
    silently dropped. The phantom schema itself is left in place (it may be
    empty, but dropping a schema is a bigger blast radius than this repair
    needs; an operator can drop it by hand once satisfied).
    """
    qf = _quote_ident(from_schema)
    quoted = ", ".join("'" + f.replace("'", "''") + "'" for f in filenames)
    return f"DELETE FROM {qf}.schema_migrations WHERE filename IN ({quoted});"


def _rows_to_filename_set(rows: list[dict] | None) -> set[str]:
    """Extract the ``filename`` column from a ``schema_migrations`` row-set."""
    out: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict):
            fn = row.get("filename")
            if fn:
                out.add(fn)
    return out


def repair_schema_migrations_ledger(
    product: str,
    *,
    confirm: bool = False,
    from_schema: str | None = None,
    to_schema: str | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    executor: SqlExecutor | None = None,
    products_dir: Path | None = None,
) -> dict[str, Any]:
    """Move ``schema_migrations`` rows stranded in a phantom schema to the real one.

    THE BUG THIS REPAIRS: before the ``_resolve_schema`` fix, ``migrate_product``
    always wrote its tracking rows to ``slug.replace("-", "_")`` regardless of
    what schema the product's migrations actually targeted (via their own
    ``SET search_path``). For ``erp-imobiliario`` / ``therapy-platform`` /
    ``personal-finance`` that naive transform is wrong, so their ledgers claim
    files are applied at an empty schema (``erp_imobiliario`` /
    ``therapy_platform`` / ``personal_finance``) that exists for no other
    reason — the DDL itself always landed correctly at the real schema
    (``erp`` / ``therapy`` / ``personal-finance``); only the bookkeeping was
    stranded.

    WHAT IT DOES: for ``product``, resolves ``phantom_schema`` (the naive
    slug-transform, or ``from_schema=`` override) and ``target_schema`` (the
    real schema via ``_resolve_schema``, or ``to_schema=`` override). If the
    phantom schema's ``schema_migrations`` table exists, copies every row not
    already present at the target (``ON CONFLICT DO NOTHING`` — idempotent)
    and then deletes the copied rows from the phantom table.

    SAFETY:
      - DRY-RUN by default (``confirm=False``) — reports ``rows_to_move``
        without writing anything, same posture as ``migrate_product``.
      - No-op (status ``no_op``) when ``phantom_schema == target_schema``
        (nothing phantom to repair) or when the phantom
        ``schema_migrations`` table doesn't exist at all (a product that
        never hit the bug, e.g. ``orbity``).
      - Never overwrites a target row (``ON CONFLICT DO NOTHING``) and never
        deletes anything from the phantom table that wasn't just copied.
      - Never drops the phantom schema itself — repair only, not cleanup.

    Returns a dict with keys::

        status: 'dry_run' | 'no_op' | 'up_to_date' | 'repaired' |
                'not_configured' | 'error'
        product, phantom_schema, target_schema, target_schema_source,
        rows_to_move: list[str]       # dry-run preview
        already_in_target: list[str]  # phantom rows the target already has
        moved: list[str]              # actually moved (confirm=True only)
        error: str | None
    """
    phantom_schema = from_schema or _slug_to_schema(product)
    target_schema, target_source = _resolve_schema(product, to_schema, products_dir)

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "status": status,
            "product": product,
            "phantom_schema": phantom_schema,
            "target_schema": target_schema,
            "target_schema_source": target_source,
            "rows_to_move": [],
            "already_in_target": [],
            "moved": [],
            "error": None,
        }
        base.update(overrides)
        return base

    if phantom_schema == target_schema:
        return _result("no_op")

    if executor is None:
        executor = make_sql_executor(project_ref=project_ref)
    if executor is None:
        return _result(
            "not_configured",
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Store it DB-first in platform_settings (key='supabase_access_token', "
                "global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env."
            ),
        )

    # ── Does the phantom table even exist? ──────────────────────────────────
    exists_result = executor.execute(_schema_migrations_exists_sql(phantom_schema))
    if not exists_result.get("ok"):
        return _result(
            "error",
            error=(
                f"could not probe {phantom_schema}.schema_migrations: "
                + (exists_result.get("error") or "unknown error")
            ),
        )
    exists_rows = exists_result.get("rows") or []
    phantom_exists = bool(exists_rows) and bool(
        exists_rows[0].get("exists_") if isinstance(exists_rows[0], dict) else False
    )
    if not phantom_exists:
        return _result("no_op")

    # ── Fetch phantom rows ───────────────────────────────────────────────────
    phantom_fetch = executor.execute(_fetch_applied_sql(phantom_schema))
    if not phantom_fetch.get("ok"):
        return _result(
            "error",
            error=(
                f"could not query {phantom_schema}.schema_migrations: "
                + (phantom_fetch.get("error") or "unknown error")
            ),
        )
    phantom_filenames = _rows_to_filename_set(phantom_fetch.get("rows"))
    if not phantom_filenames:
        return _result("no_op")

    # ── Fetch target rows (table may not exist yet — that's fine) ───────────
    target_filenames: set[str] = set()
    target_exists_result = executor.execute(_schema_migrations_exists_sql(target_schema))
    if not target_exists_result.get("ok"):
        return _result(
            "error",
            error=(
                f"could not probe {target_schema}.schema_migrations: "
                + (target_exists_result.get("error") or "unknown error")
            ),
        )
    target_exists_rows = target_exists_result.get("rows") or []
    target_exists = bool(target_exists_rows) and bool(
        target_exists_rows[0].get("exists_")
        if isinstance(target_exists_rows[0], dict)
        else False
    )
    if target_exists:
        target_fetch = executor.execute(_fetch_applied_sql(target_schema))
        if not target_fetch.get("ok"):
            return _result(
                "error",
                error=(
                    f"could not query {target_schema}.schema_migrations: "
                    + (target_fetch.get("error") or "unknown error")
                ),
            )
        target_filenames = _rows_to_filename_set(target_fetch.get("rows"))

    rows_to_move = sorted(phantom_filenames - target_filenames)
    already_in_target = sorted(phantom_filenames & target_filenames)

    if not confirm:
        return _result(
            "dry_run",
            rows_to_move=rows_to_move,
            already_in_target=already_in_target,
        )

    if not rows_to_move:
        return _result("up_to_date", already_in_target=already_in_target)

    # ── Write: ensure target table, copy, then clear the phantom copy ───────
    ensure_result = executor.execute(_ensure_tracking_table_sql(target_schema))
    if not ensure_result.get("ok"):
        return _result(
            "error",
            error=(
                f"could not create tracking table {target_schema}.schema_migrations: "
                + (ensure_result.get("error") or "unknown error")
            ),
        )

    copy_result = executor.execute(_copy_ledger_rows_sql(phantom_schema, target_schema))
    if not copy_result.get("ok"):
        return _result(
            "error",
            error=(
                f"could not copy rows {phantom_schema} → {target_schema}: "
                + (copy_result.get("error") or "unknown error")
            ),
        )

    clear_result = executor.execute(
        _delete_phantom_ledger_rows_sql(phantom_schema, rows_to_move)
    )
    if not clear_result.get("ok"):
        logger.warning(
            "repair_schema_migrations_ledger: %s rows copied to %s but the "
            "phantom-schema DELETE failed for %s: %s — the rows now exist in "
            "BOTH schemas; target is authoritative, phantom is stale but "
            "harmless.",
            len(rows_to_move),
            target_schema,
            phantom_schema,
            clear_result.get("error"),
        )
        # Non-fatal: the copy (the part that matters) succeeded.

    return _result(
        "repaired",
        moved=rows_to_move,
        already_in_target=already_in_target,
    )


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(server) -> None:
    @server.tool(
        name="noctus.dev.migrate_product",
        description=(
            "Apply a product's SQL migrations to the shared Supabase project. "
            "Reads products/<slug>/backend/migrations/*.sql sorted by numeric "
            "prefix, tracks applied files in <schema>.schema_migrations, and "
            "applies only the pending ones. "
            "DRY-RUN by default (confirm=False — lists pending vs applied). "
            "Pass confirm=True to actually apply. "
            "Idempotent: re-running skips already-applied files. "
            "Requires a Supabase Personal Access Token, resolved DB-first via "
            "resolve_credential (platform_settings['supabase_access_token'] → env "
            "SUPABASE_ACCESS_TOKEN; PAT from https://supabase.com/dashboard/account/tokens). "
            "The target schema is DERIVED from the product's own "
            "create_product_app(schema=\"...\") declaration in app/main.py "
            "(AST-parsed) — not a naive slug transform; pass schema= to override. "
            "Returns {status, product, schema, schema_source, project_ref, applied, "
            "skipped_already_applied, pending, error}. "
            "KB § PATTERNS/backend/migrate-product-mcp-tool.md."
        ),
    )
    def _migrate_product(
        product: str,
        confirm: bool = False,
        target: str | None = None,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
        schema: str | None = None,
    ) -> dict:
        return migrate_product(
            product=product,
            confirm=confirm,
            target=target,
            project_ref=project_ref,
            schema=schema,
        )

    @server.tool(
        name="noctus.dev.repair_migration_ledger",
        description=(
            "Repair a product's schema_migrations ledger after the pre-2026-09 "
            "schema-derivation bug: migrate_product used to write its tracking "
            "rows to a naive slug-transform schema (e.g. erp_imobiliario) "
            "regardless of the product's REAL schema (e.g. erp) — the migration "
            "DDL always landed correctly (each file's own SET search_path routes "
            "it), only the bookkeeping was stranded in a phantom schema that "
            "exists for no other reason. Copies every schema_migrations row from "
            "the phantom schema (naive slug-transform, or from_schema= override) "
            "to the real schema (derived via create_product_app's schema= "
            "declaration, or to_schema= override), then clears the copied rows "
            "from the phantom table. ON CONFLICT DO NOTHING on the copy — "
            "idempotent, never overwrites a real row. no_op when there is no "
            "phantom schema, or its schema_migrations table doesn't exist, or "
            "it's empty. DRY-RUN by default (confirm=False — reports "
            "rows_to_move). Pass confirm=True to actually write. "
            "Returns {status, product, phantom_schema, target_schema, "
            "target_schema_source, rows_to_move, already_in_target, moved, error}. "
            "KB § PATTERNS/backend/migrate-product-mcp-tool.md."
        ),
    )
    def _repair_migration_ledger(
        product: str,
        confirm: bool = False,
        from_schema: str | None = None,
        to_schema: str | None = None,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
    ) -> dict:
        return repair_schema_migrations_ledger(
            product=product,
            confirm=confirm,
            from_schema=from_schema,
            to_schema=to_schema,
            project_ref=project_ref,
        )


__all__ = [
    "migrate_product",
    "repair_schema_migrations_ledger",
    "SqlExecutor",
    "FakeSqlExecutor",
    "SupabaseMgmtExecutor",
    "make_sql_executor",
    "register",
    "_slug_to_schema",
    "_quote_ident",
    "_schema_from_main_py",
    "_resolve_schema",
    "_sorted_migrations",
    "_ensure_tracking_table_sql",
    "_fetch_applied_sql",
    "_record_migration_sql",
    "_schema_migrations_exists_sql",
    "_copy_ledger_rows_sql",
    "_delete_phantom_ledger_rows_sql",
    "_checksum",
]
