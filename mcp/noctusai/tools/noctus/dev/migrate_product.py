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
Schema is derived from the product slug: ``slug.replace("-", "_")`` — the same
convention used by ``noctus.dev.scaffold_migration`` and ``create_product_app``.
Override via ``schema=`` arg when the slug-derivation doesn't match.

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
    project_ref: str,
    applied: list[str],
    skipped_already_applied: list[str],
    pending: list[str],
    error: str | None,
}``

KB § PATTERNS/backend/migrate-product-mcp-tool.md
"""
from __future__ import annotations

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
    """``erp-imobiliario`` → ``erp_imobiliario`` (scaffold_migration convention)."""
    return product_slug.replace("-", "_")


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
    return (
        f"CREATE SCHEMA IF NOT EXISTS {schema};\n"
        f"CREATE TABLE IF NOT EXISTS {schema}.schema_migrations (\n"
        f"    filename   TEXT        PRIMARY KEY,\n"
        f"    applied_at TIMESTAMPTZ DEFAULT now() NOT NULL,\n"
        f"    checksum   TEXT        NOT NULL\n"
        f");"
    )


def _fetch_applied_sql(schema: str) -> str:
    """SELECT to retrieve all applied migration filenames."""
    return (
        f"SELECT filename FROM {schema}.schema_migrations ORDER BY filename;"
    )


def _record_migration_sql(schema: str, filename: str, checksum: str) -> str:
    """INSERT to record an applied migration (conflict = already applied)."""
    safe_filename = filename.replace("'", "''")
    safe_checksum = checksum.replace("'", "''")
    return (
        f"INSERT INTO {schema}.schema_migrations (filename, checksum) "
        f"VALUES ('{safe_filename}', '{safe_checksum}') "
        f"ON CONFLICT (filename) DO NOTHING;"
    )


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
        schema:       Override the auto-derived schema (slug with ``-`` → ``_``).
        executor:     Injection seam for tests (``FakeSqlExecutor``).
                      When None, resolved from env via ``make_sql_executor``.
        products_dir: Override ``PRODUCTS_DIR`` (injection seam for tests).

    Returns a dict with keys::

        status, product, schema, project_ref, applied, skipped_already_applied,
        pending, error
    """
    derived_schema = schema or _slug_to_schema(product)

    # ── Resolve executor ──────────────────────────────────────────────────────
    if executor is None:
        executor = make_sql_executor(project_ref=project_ref)
    if executor is None:
        # NOC-REMEDIATE[credentials]: no supabase_access_token resolved.
        # Store it DB-first (preferred): platform_settings['supabase_access_token']
        # (global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env.
        # Create the PAT at: https://supabase.com/dashboard/account/tokens — 2026-07-27
        return {
            "status": "not_configured",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": (
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Store it DB-first in platform_settings (key='supabase_access_token', "
                "global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env. "
                "Create the PAT at: https://supabase.com/dashboard/account/tokens"
            ),
        }

    # ── Resolve migrations directory ──────────────────────────────────────────
    mig_dir = _migrations_dir(product, products_dir)
    if not mig_dir.exists():
        return {
            "status": "error",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": f"migrations directory not found: {mig_dir}",
        }

    all_files = _sorted_migrations(mig_dir)
    if not all_files:
        return {
            "status": "up_to_date",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": None,
        }

    # ── Apply optional target filter ──────────────────────────────────────────
    if target is not None:
        all_files = [f for f in all_files if f.name == target]
        if not all_files:
            return {
                "status": "error",
                "product": product,
                "schema": derived_schema,
                "project_ref": project_ref,
                "applied": [],
                "skipped_already_applied": [],
                "pending": [],
                "error": f"target file not found in migrations: {target!r}",
            }

    # ── Ensure tracking table exists ──────────────────────────────────────────
    ensure_sql = _ensure_tracking_table_sql(derived_schema)
    ensure_result = executor.execute(ensure_sql)
    if not ensure_result.get("ok"):
        logger.error(
            "migrate_product: failed to ensure tracking table for %s: %s",
            product,
            ensure_result.get("error"),
        )
        return {
            "status": "error",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": (
                f"could not create tracking table {derived_schema}.schema_migrations: "
                + (ensure_result.get("error") or "unknown error")
            ),
        }

    # ── Fetch already-applied filenames ───────────────────────────────────────
    fetch_result = executor.execute(_fetch_applied_sql(derived_schema))
    if not fetch_result.get("ok"):
        logger.error(
            "migrate_product: failed to query schema_migrations for %s: %s",
            product,
            fetch_result.get("error"),
        )
        return {
            "status": "error",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": (
                f"could not query {derived_schema}.schema_migrations: "
                + (fetch_result.get("error") or "unknown error")
            ),
        }

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
        return {
            "status": "dry_run",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": skipped,
            "pending": pending_names,
            "error": None,
        }

    # ── Apply pending files in order ──────────────────────────────────────────
    if not pending:
        return {
            "status": "up_to_date",
            "product": product,
            "schema": derived_schema,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": skipped,
            "pending": [],
            "error": None,
        }

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
            return {
                "status": "error",
                "product": product,
                "schema": derived_schema,
                "project_ref": project_ref,
                "applied": newly_applied,
                "skipped_already_applied": skipped,
                "pending": [f.name for f in pending if f.name not in newly_applied],
                "error": f"migration {mig_file.name} failed: " + (result.get("error") or "unknown"),
            }

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

    return {
        "status": "applied",
        "product": product,
        "schema": derived_schema,
        "project_ref": project_ref,
        "applied": newly_applied,
        "skipped_already_applied": skipped,
        "pending": [],
        "error": None,
    }


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
            "Returns {status, product, schema, project_ref, applied, "
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


__all__ = [
    "migrate_product",
    "SqlExecutor",
    "FakeSqlExecutor",
    "SupabaseMgmtExecutor",
    "make_sql_executor",
    "register",
    "_slug_to_schema",
    "_sorted_migrations",
    "_ensure_tracking_table_sql",
    "_fetch_applied_sql",
    "_record_migration_sql",
    "_checksum",
]
