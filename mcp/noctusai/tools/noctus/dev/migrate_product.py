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

STALE-TREE REFUSAL (added 2026-09-17 — the incident)
------------------------------------------------------
``migrate_product`` reads migration files from a filesystem tree
(``products/<slug>/backend/migrations/``), not from git history — so a
tree that is BEHIND its upstream silently omits any migration added
upstream, and the dry-run this tool prints has no way to know it is
missing anything. On 2026-09-17, during a real prod deploy, the primary
checkout was 26 commits behind ``origin/dev`` and did not contain
``134_contrato_assinatura.sql`` at all. The dry-run confidently listed a
pending set that OMITTED the migration actually being deployed — a
reassuring, green-looking output computed against the wrong tree. That is
a silent error in the CLAUDE.md §1 sense: the dangerous behaviour (trust
whatever tree happens to be checked out) was the *default*.

``migrate_product`` now REFUSES — status ``'refused_stale_tree'``,
``exit_code=1`` — before reading a single migration file, whenever the
tree it is about to read from is not verifiably trustworthy:

  1. It is BEHIND its upstream tracking ref (``HEAD..<upstream>`` is
     non-empty).
  2. It has uncommitted changes (staged, unstaged, or untracked) under
     ``products/*/backend/migrations/`` anywhere in the tree.
  3. Any git query the check depends on fails, or the tree is not a git
     work tree at all — this is fail-closed by construction: an
     unanswerable question is treated as untrustworthy, NEVER silently as
     clean (that is exactly the bug being fixed).

The refusal names the inspected tree (absolute path), its branch, its
upstream, ``commits_behind``, and the exact remedy
(``git merge --ff-only <upstream>``, or pass ``worktree_path=``/
``repo_root=`` to pin a different tree) in ``error``. The full staleness
verdict also always rides along as the ``stale_tree`` key on every
returned result (dry_run/applied/up_to_date/error/refused_stale_tree
alike) — never only on the refusal path — so a caller that deliberately
bypasses the gate (see below) can still see what was found.

``worktree_path=`` pins BOTH which tree the staleness check inspects and
where migrations are read from (mirrors ``predeploy_check``'s parameter
of the same name and semantics exactly) — the MCP server is one
long-running stdio process fixed at whatever directory it booted in, so a
caller working inside a worktree MUST say so explicitly; there is no way
to auto-detect a caller's cwd. Omitting it checks/reads the primary.

``allow_stale_tree: bool = False`` is the documented escape hatch (same
shape as ``deploy_image``'s ``skip_ancestry_check``) for the rare
deliberate case — e.g. a human has already visually diffed the pending
set and knows it is complete. Using it is almost always wrong: it exists
so a genuinely-informed override doesn't have to fork the tool, not so a
caller can silence the gate out of impatience. When set, the staleness
check still runs and its (now non-fatal) verdict still rides on
``stale_tree`` in the result — the bypass is visible, never silent.

CATALOG-SCOPE REFUSAL (added 2026-09-17 — the same incident)
--------------------------------------------------------------
The same 2026-09-17 incident this tool's stale-tree gate above closes also
included ``migrate_product`` applying migrations to ``erp`` for
``erp-imobiliario`` — ``ativo=false, deploy_scope='dev'`` in the product
catalog. CLAUDE.md §1: "The product catalog IS the working guide —
ativo+live ⇒ work in prod, ativo+dev ⇒ dev only, inativo ⇒ don't touch"
(``KB § PATTERNS/architect/product-working-scope.md``). Nothing in this
tool asked that question before writing to Supabase.

``migrate_product`` now REFUSES — status ``'refused_catalog_scope'``,
``exit_code=1`` — before touching any credential or migration file,
whenever ``product`` is not ``ativo=true AND deploy_scope='live'`` in the
catalog (or ``core``). Same status-key convention as
``'refused_stale_tree'`` above; same "verdict rides on every return" rule
— the resolved ``catalog_scope`` dict is present on ``dry_run`` /
``applied`` / ``up_to_date`` / ``error`` / ``not_configured`` /
``refused_stale_tree`` / ``refused_catalog_scope`` alike, never only on
the refusal path.

This check REUSES ``deploy_verify._resolve_live_products`` (via the
shared ``_catalog_scope_guard`` module — also consumed by
``noctus.dev.deploy_image``) rather than a second hand-rolled catalog
query (§1: grep for the existing mechanism before designing one).
Fail-closed: a catalog read that cannot be answered at all (neither the
live catalog nor the checked-in ``build-scope.txt`` fallback resolves) is
treated as NOT in scope — "cannot tell" is never "allowed".

``allow_inactive: bool = False`` is the documented escape hatch — same
shape and same warning as ``allow_stale_tree`` above: legitimate ONLY for
a deliberate, supervised reactivation of a dormant product (e.g. a human
has confirmed the catalog row is about to be flipped to ``ativo=true``
and wants the schema ready first), almost always wrong otherwise. The
bypass is never silent — ``catalog_scope``/``allow_inactive`` still ride
on the result.

KB § PATTERNS/backend/migrate-product-mcp-tool.md ·
KB § PATTERNS/architect/product-working-scope.md
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from settings import PRODUCTS_DIR, REPO_ROOT
from workspace import resolve_caller_root

from . import _catalog_scope_guard
from . import toolkit_freshness as _toolkit_freshness

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


def _parse_schema_from_source(source: str, label: str) -> str | None:
    """AST-derive the ``schema="..."`` keyword literal off a
    ``create_product_app(...)`` call — the pure parser shared by BOTH the
    working-tree (``_schema_from_main_py``) and the sha-pinned
    (``_schema_from_main_py_at_sha``) resolution paths, so "how we read the
    schema" is never duplicated across the two (F8, compliance review
    2026-09-24 — this is what closes the sha-mode schema-derivation gap
    filed against migrate_product).

    AST-parsed per `KB § PATTERNS/common/ast.md` — not regexed, so a
    multi-line ``create_product_app(\\n    name=...,\\n    schema="erp",``
    call (every real product's shape) is found regardless of formatting.
    ``label`` is only used in the debug log line on a parse failure.

    Returns ``None`` when the source fails to parse, has no
    ``create_product_app`` call, or that call's ``schema`` keyword isn't a
    literal string (e.g. computed) — callers fall back to
    ``_slug_to_schema`` in that case and must say so via ``schema_source``.
    """
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        logger.debug(
            "migrate_product: could not parse %s for schema derivation: %s", label, exc,
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


def _schema_from_main_py(
    product_slug: str, products_dir: Path | None = None
) -> str | None:
    """AST-derive the product's declared schema from its own WORKING-TREE
    ``app/main.py``.

    Every product declares its schema exactly once, as the ``schema="..."``
    keyword literal on its ``create_product_app(...)`` call (the same call
    that wires routers, auth, and — transitively, via
    ``create_database_module`` — every RLS-scoped query). That single
    declaration is the authoritative source this function reads; nothing
    here is a hand-maintained slug→schema map (`CLAUDE.md` §1 "derive, don't
    sync by hand").

    Returns ``None`` when ``main.py`` is missing, fails to read/parse, or
    the AST parse (``_parse_schema_from_source``) can't find a literal
    ``schema=`` — callers fall back to ``_slug_to_schema`` in that case."""
    base = products_dir or PRODUCTS_DIR
    main_py = base / product_slug / "backend" / "app" / "main.py"
    if not main_py.exists():
        return None
    try:
        source = main_py.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug(
            "migrate_product: could not read %s for schema derivation: %s", main_py, exc,
        )
        return None
    return _parse_schema_from_source(source, str(main_py))


def _schema_from_main_py_at_sha(
    root: Path, sha: str, product_slug: str, git_runner: "GitRunner",
) -> str | None:
    """F8 (compliance review, 2026-09-24): AST-derive the schema from
    ``app/main.py`` AS IT EXISTED AT ``sha`` (via ``git show``), never the
    working tree — closes the sha-mode schema-derivation gap filed
    against migrate_product: a
    schema-declaration change between ``sha`` and the working tree could
    otherwise apply ``sha``'s migrations against the WRONG schema, silently.
    Returns ``None`` when the file doesn't exist at that sha (``git show``
    fails) or the AST parse finds no literal ``schema=`` — same fallback
    contract as ``_schema_from_main_py``."""
    rel = f"products/{product_slug}/backend/app/main.py"
    try:
        source = git_runner.run(root, ["show", f"{sha}:{rel}"])
    except GitQueryError as exc:
        logger.debug(
            "migrate_product: could not read %s:%s for schema derivation: %s",
            sha, rel, exc,
        )
        return None
    return _parse_schema_from_source(source, f"{sha}:{rel}")


def _resolve_schema(
    product_slug: str,
    schema_override: str | None,
    products_dir: Path | None = None,
    *,
    sha: str | None = None,
    git_root: Path | None = None,
    git_runner: "GitRunner | None" = None,
) -> tuple[str, str]:
    """Resolve the real DB schema for ``product_slug`` + say HOW it was resolved.

    Precedence: explicit override → declared in the product's own main.py
    (AT ``sha`` when given — F8, never the working tree in sha= mode) →
    naive slug-transform fallback (see module docstring "SCHEMA DERIVATION").

    Returns ``(schema, schema_source)`` where ``schema_source`` is one of
    ``'explicit_override' | 'main_py_declaration' | 'main_py_declaration_at_sha'
    | 'slug_fallback'`` — every caller threads this into the result payload
    so a fallback is never silently indistinguishable from a verified
    derivation (no-silent-errors).
    """
    if schema_override:
        return schema_override, "explicit_override"
    if sha:
        declared_at_sha = _schema_from_main_py_at_sha(
            git_root or PRODUCTS_DIR.parent, sha, product_slug,
            git_runner or _DEFAULT_GIT_RUNNER,
        )
        if declared_at_sha:
            return declared_at_sha, "main_py_declaration_at_sha"
        return _slug_to_schema(product_slug), "slug_fallback"
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
# R3 (2026-09-24, part of the release-no-freeze fix): read migrations from a
# BLESSED SHA via `git show`, never the working tree.
#
# `noctus.dev.release` R1 now blesses the newest QUALIFYING-green commit,
# which is not necessarily the exact dev tip (and — with `deploy_pull`'s
# usual §2a FF flow — `main`'s working tree is only updated by a later `git
# merge --ff-only`). Deploying migrations off "whatever the working tree
# currently holds" always risked a race against the blessed state; passing
# `sha=` makes that pin EXACT: the applied migration set is the migrations
# directory as it existed AT that commit, full stop, independent of
# whatever the checkout happens to hold right now.
# ---------------------------------------------------------------------------
class _GitBlobFile:
    """Duck-types the tiny surface the apply loop needs from a migration
    file (`.name` + `.read_text()`), but resolves its CONTENT from
    `git show <sha>:<path>` instead of the filesystem. Content is fetched
    lazily and cached — a dry-run that never applies anything never pays a
    `git show` cost for files it only needs to list."""

    def __init__(self, name: str, git_path: str, sha: str, root: Path, git_runner: "GitRunner") -> None:
        self.name = name
        self._git_path = git_path
        self._sha = sha
        self._root = root
        self._git_runner = git_runner
        self._content: str | None = None

    def read_text(self, encoding: str = "utf-8") -> str:  # noqa: ARG002 — Path.read_text() parity
        if self._content is None:
            # F8 (compliance review, 2026-09-24): `run_raw`, NEVER `run` —
            # `run` rstrips, which would silently drop this file's trailing
            # newline/whitespace and make `_checksum` hash something other
            # than the byte-identical working-tree read would. See the
            # `GitRunner.run_raw` Protocol docstring for the full reasoning.
            self._content = self._git_runner.run_raw(
                self._root, ["show", f"{self._sha}:{self._git_path}"]
            )
        return self._content


def _sorted_migrations_at_sha(
    root: Path, sha: str, product_slug: str, git_runner: "GitRunner"
) -> list[_GitBlobFile]:
    """Same ordering contract as ``_sorted_migrations`` (leading ``NNN_``
    numeric prefix, ``.sql`` only), but the file LIST comes from
    ``git ls-tree`` and the CONTENT from ``git show`` — never the working
    tree. Raises :class:`GitQueryError` on any git failure (fail-closed,
    same posture as ``_check_tree_staleness`` — an unanswerable "what files
    exist at this sha" is never silently treated as "no files").

    F8(a) (compliance review, 2026-09-24): ALSO raises ``GitQueryError``
    when ``git ls-tree`` returns completely EMPTY output — git has no
    concept of an empty directory, so zero tree entries at ``rel_dir``
    means the path does not exist at this sha at all (wrong product slug,
    or the product didn't exist yet at this historical commit), never a
    legitimate "migrations dir exists but is empty". The caller (`migrate_
    product`) must surface this as ``status='error'``, never a misleadingly
    clean ``'up_to_date'``."""
    rel_dir = f"products/{product_slug}/backend/migrations"
    listing = git_runner.run(root, ["ls-tree", "--name-only", "-r", sha, "--", rel_dir])
    if not listing.strip():
        raise GitQueryError(
            f"migrations directory {rel_dir!r} does not exist at {sha} — git "
            "has no concept of an empty directory, so an empty `ls-tree` "
            "means the path itself is missing at this commit (wrong product "
            "slug, or the product did not exist yet at this sha)."
        )
    numbered: list[tuple[int, str, str]] = []
    for line in listing.splitlines():
        line = line.strip()
        if not line or not line.endswith(".sql"):
            continue
        name = line.rsplit("/", 1)[-1]
        m = _NN_RE.match(name)
        if m:
            numbered.append((int(m.group(1)), name, line))
        else:
            logger.debug("migrate_product: skipping non-numbered file %s @ %s", name, sha)
    numbered.sort(key=lambda x: x[0])
    return [
        _GitBlobFile(name=name, git_path=git_path, sha=sha, root=root, git_runner=git_runner)
        for _, name, git_path in numbered
    ]


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
# Stale-tree refusal — GitRunner Protocol + Fake + Real (see module
# docstring "STALE-TREE REFUSAL")
# ---------------------------------------------------------------------------


class GitQueryError(Exception):
    """A git query the staleness gate depends on could not be answered.

    Deliberately its own exception (not a bare ``RuntimeError``) so
    ``_check_tree_staleness`` can catch precisely this and nothing else —
    fail-closed by construction: every code path that cannot determine an
    answer raises this and is treated as untrustworthy, never as clean.
    """


@runtime_checkable
class GitRunner(Protocol):
    """Narrow DI seam: run one read-only git query in ``root``.

    Returns stdout, stripped. Raises :class:`GitQueryError` on ANY failure
    (non-zero exit, git missing, not a work tree, timeout) — a runner must
    never return a placeholder/empty value to signal failure, because an
    empty value is indistinguishable from a genuine (if unlikely) empty
    answer. Mirrors the ``SqlExecutor`` Protocol+Fake+Real+factory shape
    used above for the Supabase side of this same tool.
    """

    def run(self, root: Path, args: list[str]) -> str:
        ...  # pragma: no cover

    def run_raw(self, root: Path, args: list[str]) -> str:
        """F8 (compliance review, 2026-09-24): like ``run``, but returns
        stdout byte-for-byte UNSTRIPPED. ``run`` deliberately ``.rstrip()``s
        (see ``SubprocessGitRunner.run``'s comment) — correct for the
        porcelain/plumbing queries every OTHER caller in this module makes,
        WRONG for fetching a migration FILE's content: rstripping a `git
        show <sha>:<path>` blob silently drops the file's trailing
        newline/whitespace, so ``_checksum`` would hash something OTHER
        than what the working-tree path (``Path.read_text()``, never
        stripped) hashes for the byte-identical file — a checksum that
        differs depending on which CODE PATH read it defeats the whole
        point of a content-integrity checksum. Used ONLY by
        ``_GitBlobFile.read_text`` for exactly this reason."""
        ...  # pragma: no cover


class FakeGitRunner:
    """In-memory git runner for unit tests — spawns zero real git processes.

    ``responses`` maps an exact args-tuple (e.g.
    ``("rev-parse", "--abbrev-ref", "HEAD")``) to the canned stdout string.
    ``fail_on`` is a set of args-tuples that raise :class:`GitQueryError`
    instead (simulates "not a git repo" / any git failure). An args-tuple
    with neither a response nor a fail_on entry returns ``""`` — tests
    should configure every call the staleness check will actually make.
    ``calls`` accumulates every args-tuple passed to ``run``/``run_raw``
    (assertions on call order/count). ``run_raw`` delegates to the SAME
    ``responses``/``fail_on`` — the Fake never strips anything in the first
    place, so there is no separate "raw" behavior to fake."""

    def __init__(
        self,
        *,
        responses: dict[tuple[str, ...], str] | None = None,
        fail_on: set[tuple[str, ...]] | None = None,
    ) -> None:
        self.responses: dict[tuple[str, ...], str] = responses or {}
        self.fail_on: set[tuple[str, ...]] = fail_on or set()
        self.calls: list[tuple[str, ...]] = []

    def run(self, root: Path, args: list[str]) -> str:
        key = tuple(args)
        self.calls.append(key)
        if key in self.fail_on:
            raise GitQueryError(f"fake failure for: git {' '.join(args)}")
        return self.responses.get(key, "")

    def run_raw(self, root: Path, args: list[str]) -> str:
        return self.run(root, args)


class SubprocessGitRunner:
    """Real runner: shells out to the system ``git`` binary.

    A bounded timeout (15s) keeps a hung git process (e.g. a credential
    prompt on a misconfigured remote) from blocking a dry-run forever —
    a timeout is a query failure like any other (``GitQueryError``), never
    silently treated as clean.
    """

    _TIMEOUT_S = 15

    def _run_proc(self, root: Path, args: list[str]) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=self._TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitQueryError(
                f"git {' '.join(args)} failed to run in {root}: {exc}"
            ) from exc
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "no output"
            raise GitQueryError(
                f"git {' '.join(args)} exited {proc.returncode} in {root}: {detail}"
            )
        return proc

    def run(self, root: Path, args: list[str]) -> str:
        proc = self._run_proc(root, args)
        # `.rstrip()`, NEVER `.strip()` — a multi-line porcelain output's
        # FIRST line can legitimately start with a leading space (the git
        # status-code column, e.g. ` M path` for "modified, not staged").
        # `.strip()` trims that leading space off the WHOLE blob (not
        # per-line), shifting every char of that first line's `line[3:]`
        # status-code slice by one and silently eating the path's first
        # character (`KNOWLEDGE-BASE/...` -> `NOWLEDGE-BASE/...`). Found
        # 2026-09-17 building `noctus.dev.gate_sweep`'s real (non-Fake)
        # `git status --porcelain` path — a corner `FakeGitRunner`-only
        # tests can never exercise, since the Fake returns exact strings.
        return proc.stdout.rstrip()

    def run_raw(self, root: Path, args: list[str]) -> str:
        # F8: byte-for-byte, no `.rstrip()` — see the Protocol docstring.
        return self._run_proc(root, args).stdout


_DEFAULT_GIT_RUNNER = SubprocessGitRunner()

# Matches a path under products/<slug>/backend/migrations/ inside
# `git status --porcelain` output (rule 2 of the stale-tree refusal).
_MIGRATION_PATH_RE = re.compile(r"^products/[^/]+/backend/migrations/")


def _dirty_migration_paths(porcelain_output: str) -> list[str]:
    """Extract every path under ``products/*/backend/migrations/`` touched
    by an uncommitted change, from ``git status --porcelain`` output.

    Handles porcelain v1's ``XY <path>`` shape and the rename shape
    ``XY <old> -> <new>`` (the new path is the one that matters). Staged,
    unstaged, AND untracked changes all count — a migration file added
    locally but not yet committed is exactly the kind of unreviewed state
    this gate exists to catch, same as an edited one.
    """
    paths: list[str] = []
    for line in porcelain_output.splitlines():
        if len(line) <= 3:
            continue
        path_part = line[3:]
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        path_part = path_part.strip().strip('"')
        if _MIGRATION_PATH_RE.match(path_part):
            paths.append(path_part)
    return sorted(set(paths))


def _check_tree_staleness(root: Path, *, git_runner: GitRunner) -> dict[str, Any]:
    """Determine whether ``root``'s git tree is trustworthy to read
    migrations from. See module docstring "STALE-TREE REFUSAL".

    Fail-closed: any query this needs that cannot be answered is reported
    as untrustworthy (``check="query_failed"``) — never silently as clean.

    Returns::

        {
            "stale": bool,
            "check": "behind" | "dirty_migrations" | "query_failed" | None,
            "branch": str | None,
            "upstream": str | None,
            "commits_behind": int | None,
            "dirty_migration_files": list[str],
            "detail": str,  # concrete, human-readable — no tree/remedy text
                             # (the caller composes the full refusal message,
                             # which always names the tree + remedy too).
        }
    """
    base: dict[str, Any] = {
        "stale": False,
        "check": None,
        "branch": None,
        "upstream": None,
        "commits_behind": None,
        "dirty_migration_files": [],
        "detail": "clean",
    }

    try:
        branch = git_runner.run(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    except GitQueryError as exc:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "detail": f"could not determine the current branch: {exc}",
        }
    if not branch:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "detail": "could not determine the current branch (empty git output)",
        }

    try:
        upstream = git_runner.run(
            root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
        )
    except GitQueryError as exc:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "branch": branch,
            "detail": (
                f"branch {branch!r} has no resolvable upstream tracking ref, "
                f"so freshness cannot be verified: {exc}"
            ),
        }
    if not upstream:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "branch": branch,
            "detail": f"branch {branch!r} has no upstream tracking ref configured",
        }

    try:
        behind_raw = git_runner.run(root, ["rev-list", "--count", f"HEAD..{upstream}"])
        commits_behind = int(behind_raw)
    except (GitQueryError, ValueError) as exc:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "branch": branch,
            "upstream": upstream,
            "detail": f"could not compute commits behind {upstream}: {exc}",
        }

    if commits_behind > 0:
        return {
            "stale": True,
            "check": "behind",
            "branch": branch,
            "upstream": upstream,
            "commits_behind": commits_behind,
            "dirty_migration_files": [],
            "detail": (
                f"{commits_behind} commit(s) behind {upstream} — a migration "
                f"file added upstream would be silently invisible to this run"
            ),
        }

    try:
        status_raw = git_runner.run(root, ["status", "--porcelain"])
    except GitQueryError as exc:
        return {
            **base,
            "stale": True,
            "check": "query_failed",
            "branch": branch,
            "upstream": upstream,
            "commits_behind": commits_behind,
            "detail": f"could not query git status: {exc}",
        }

    dirty = _dirty_migration_paths(status_raw)
    if dirty:
        return {
            "stale": True,
            "check": "dirty_migrations",
            "branch": branch,
            "upstream": upstream,
            "commits_behind": commits_behind,
            "dirty_migration_files": dirty,
            "detail": (
                "uncommitted changes under products/*/backend/migrations/: "
                + ", ".join(dirty)
            ),
        }

    return {
        "stale": False,
        "check": None,
        "branch": branch,
        "upstream": upstream,
        "commits_behind": commits_behind,
        "dirty_migration_files": [],
        "detail": "clean",
    }


# ---------------------------------------------------------------------------
# Tracking-table DDL
# ---------------------------------------------------------------------------


def _ensure_tracking_table_sql(schema: str) -> str:
    """DDL to create the schema_migrations tracking table (idempotent) —
    LOCKED DOWN against PostgREST.

    Product schemas are exposed via PostgREST (``authenticator``'s
    ``pgrst.db_schemas``) with default grants to ``anon``/``authenticated``,
    so a bare ``schema_migrations`` table is readable AND writable over the
    REST API by anyone — including inserting a fake filename so a future
    ``migrate_product`` run silently skips a real migration. Verified live
    on Supabase project ``nyplttplcoyiiqjrvtiw`` 2026-09-16: before the fix,
    an anon REST call could read the ledger; after ``ENABLE ROW LEVEL
    SECURITY`` + revoking the PostgREST roles, the same call returns
    ``42501`` while the Management-API executor (the table owner, which
    RLS never restricts) still reads/writes it fine.

    Both statements are idempotent: re-enabling RLS on an already-RLS'd
    table is a no-op (no error), and ``REVOKE`` on a role that already
    lacks the privilege is also a no-op — so re-running this on an
    already-hardened schema is safe.

    KB § PATTERNS/backend/database-rls.md § schema_migrations ledger
    hardening (2026-09-16); codified fleet-wide in
    ``products/core/backend/migrations/048_lock_schema_migrations_ledgers.sql``.
    """
    q = _quote_ident(schema)
    return (
        f"CREATE SCHEMA IF NOT EXISTS {q};\n"
        f"CREATE TABLE IF NOT EXISTS {q}.schema_migrations (\n"
        f"    filename   TEXT        PRIMARY KEY,\n"
        f"    applied_at TIMESTAMPTZ DEFAULT now() NOT NULL,\n"
        f"    checksum   TEXT        NOT NULL\n"
        f");\n"
        f"ALTER TABLE {q}.schema_migrations ENABLE ROW LEVEL SECURITY;\n"
        f"REVOKE ALL ON {q}.schema_migrations FROM anon, authenticated;"
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


_ERROR_STATUSES = frozenset({
    "error", "not_configured", "refused_stale_tree", _catalog_scope_guard.REFUSED_STATUS,
})


@_toolkit_freshness.refuse_gate("migrate_product")
def migrate_product(
    product: str,
    *,
    confirm: bool = False,
    target: str | None = None,
    sha: str | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    schema: str | None = None,
    executor: SqlExecutor | None = None,
    products_dir: Path | None = None,
    worktree_path: str | None = None,
    allow_stale_tree: bool = False,
    allow_inactive: bool = False,
    repo_root: str | Path | None = None,
    git_runner: GitRunner | None = None,
    live_products_fn: Callable[[], list[str]] | None = None,
) -> dict[str, Any]:
    """Apply pending migrations for ``product`` to the Supabase database.

    Args:
        product:      Product slug (e.g. ``orbity``, ``erp-imobiliario``).
        confirm:      False (default) = dry-run (list pending; no DDL run).
                      True = apply all pending files in order.
        target:       Optional filename filter — apply / list only this file.
        sha:          R3 (release-no-freeze): when given, migration files —
                      AND the schema they're applied to (F8, closes NOC-
                      REMEDIATE[migrate-product-sha-schema]) — are read via
                      ``git show <sha>:<path>``, the EXACT state that existed
                      at that commit, never the working tree; the stale-tree
                      refusal below is skipped entirely (there is nothing
                      "stale" about a pinned historical commit). Typical
                      caller: ``noctus.dev.release``'s ``blessed_sha`` right
                      after a bless, so what gets APPLIED is provably what
                      got BLESSED, independent of whatever the checkout
                      currently holds. Raises no exception on an unreadable
                      sha —
                      surfaces as ``status='error'``.
        project_ref:  Supabase project reference (default: noctusai production).
        schema:       Override the auto-derived schema. When omitted, the
                      schema is DERIVED from the product's own
                      ``create_product_app(schema="...")`` declaration (see
                      ``_resolve_schema`` / module docstring "SCHEMA
                      DERIVATION") — not the naive slug transform.
        executor:     Injection seam for tests (``FakeSqlExecutor``).
                      When None, resolved from env via ``make_sql_executor``.
        products_dir: Override the migrations-source directory (injection
                      seam for tests). When omitted, derived from
                      ``worktree_path`` if given, else ``PRODUCTS_DIR``.
        worktree_path: Pins BOTH which tree the stale-tree check inspects
                      AND where migrations are read from — same parameter
                      name and semantics as ``predeploy_check``. The MCP
                      server is one long-running process fixed at whatever
                      directory it booted in; a caller working inside a
                      git worktree MUST pass this explicitly. Omit to
                      target the primary checkout.
        allow_stale_tree: Escape hatch for the stale-tree refusal (see
                      module docstring "STALE-TREE REFUSAL"). Default
                      False. Setting this True is almost always wrong —
                      it exists for the rare case a human has already
                      manually verified the tree is safe to read from
                      (e.g. visually diffed the pending set against what
                      is actually merged upstream), not as a way to
                      silence the gate out of impatience. The staleness
                      verdict still computes and still rides on the
                      ``stale_tree`` key even when bypassed — never silent.
        repo_root:    Explicit override for the tree the stale-tree check
                      inspects (test seam — wins over ``worktree_path``,
                      same precedence convention as ``check_merge_debt`` /
                      ``predeploy_check``).
        git_runner:   Injection seam for tests (``FakeGitRunner``). When
                      None, resolved to the real ``SubprocessGitRunner``.
        allow_inactive: Escape hatch for the catalog-scope refusal (see
                      module docstring "CATALOG-SCOPE REFUSAL"). Default
                      False. Setting this True is almost always wrong —
                      it exists for a deliberate, supervised reactivation
                      of a dormant product, not as a way to silence the
                      gate out of impatience. The resolved ``catalog_scope``
                      verdict still rides on the result even when bypassed
                      — never silent.
        live_products_fn: Injection seam for tests — same parameter name
                      and semantics as ``deploy_verify``'s own seam of the
                      same name (threaded through ``_catalog_scope_guard``).
                      When None, resolved against the live catalog with a
                      ``build-scope.txt`` fallback.

    Returns a dict with keys::

        status ('dry_run' | 'applied' | 'up_to_date' | 'not_configured' |
                'error' | 'refused_stale_tree' | 'refused_catalog_scope'),
        exit_code (0 on every non-error status, 1 otherwise),
        product, schema, schema_source, project_ref, applied,
        skipped_already_applied, pending, error, stale_tree,
        allow_stale_tree, catalog_scope, allow_inactive, sha
    """
    resolved_products_dir: Path
    if products_dir is not None:
        resolved_products_dir = products_dir
    elif worktree_path:
        resolved_products_dir = Path(resolve_caller_root(worktree_path)) / "products"
    else:
        resolved_products_dir = PRODUCTS_DIR

    git_root: Path
    if repo_root is not None:
        git_root = Path(repo_root)
    elif worktree_path:
        git_root = Path(resolve_caller_root(worktree_path))
    else:
        git_root = Path(REPO_ROOT)

    # F8(b) (compliance review, 2026-09-24): resolve `sha` to a FULL,
    # VERIFIED commit sha exactly ONCE, before it is used anywhere —
    # schema derivation, migration listing, and the result payload all then
    # see the SAME pinned value. `--verify ...^{commit}` both confirms the
    # ref actually names a commit (not a tree/blob/tag mismatch) up front,
    # with one clear error, instead of a confusing failure from whichever
    # of the several later `git` calls happens to hit it first.
    if sha:
        resolver = git_runner or _DEFAULT_GIT_RUNNER
        try:
            sha = resolver.run(git_root, ["rev-parse", "--verify", f"{sha}^{{commit}}"])
        except GitQueryError as exc:
            return {
                "status": "error",
                "exit_code": 1,
                "product": product,
                "schema": None,
                "schema_source": None,
                "project_ref": project_ref,
                "applied": [],
                "skipped_already_applied": [],
                "pending": [],
                "sha": sha,
                "error": (
                    f"migrate_product: sha={sha!r} does not resolve to a real "
                    f"commit in {git_root}: {exc}. It must be reachable from "
                    "this tree's object database (e.g. already fetched)."
                ),
            }

    derived_schema, schema_source = _resolve_schema(
        product, schema, resolved_products_dir,
        sha=sha, git_root=git_root, git_runner=git_runner,
    )

    # R3: a `sha=` pin reads migrations from that COMMIT via git, never the
    # working tree — the stale-tree question ("is the CHECKOUT trustworthy")
    # is moot for a pinned historical commit, so the check still computes
    # (informational — it rides on every result either way) but never
    # refuses when `sha` is given.
    stale_tree = _check_tree_staleness(
        git_root, git_runner=git_runner or _DEFAULT_GIT_RUNNER
    )

    catalog_scope = _catalog_scope_guard.check_catalog_scope(product, live_products_fn)

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "status": status,
            "exit_code": 1 if status in _ERROR_STATUSES else 0,
            "product": product,
            "schema": derived_schema,
            "schema_source": schema_source,
            "project_ref": project_ref,
            "applied": [],
            "skipped_already_applied": [],
            "pending": [],
            "error": None,
            "stale_tree": stale_tree,
            "allow_stale_tree": allow_stale_tree,
            "catalog_scope": catalog_scope,
            "allow_inactive": allow_inactive,
            "sha": sha,
        }
        base.update(overrides)
        return base

    # ── Refuse a product the catalog doesn't say is live BEFORE anything else ──
    # (KB § PATTERNS/backend/migrate-product-mcp-tool.md "CATALOG-SCOPE REFUSAL":
    # the same 2026-09-17 incident — migrate_product wrote to `erp` for
    # erp-imobiliario, ativo=false/deploy_scope='dev'. Fail-closed: this check
    # runs — and can refuse — before any Supabase credential is touched.)
    if not catalog_scope["in_scope"] and not allow_inactive:
        return _result(
            _catalog_scope_guard.REFUSED_STATUS,
            error=_catalog_scope_guard.catalog_scope_refusal_reason(
                product, catalog_scope,
                action="migrate", escape_hatch="allow_inactive",
                untouched_clause="No migration file was read and no SQL was run.",
            ),
        )

    # ── Refuse a stale/dirty/unverifiable tree BEFORE reading migrations ──────
    # (KB § PATTERNS/backend/migrate-product-mcp-tool.md "STALE-TREE REFUSAL":
    # the 2026-09-17 incident — a dry-run computed a confident pending list
    # against a tree 26 commits behind origin/dev that didn't even contain
    # the migration being deployed. Fail-closed by construction: this check
    # runs — and can refuse — before any Supabase credential is touched.)
    if stale_tree["stale"] and not allow_stale_tree and not sha:
        remedy = (
            f"git merge --ff-only {stale_tree['upstream']}"
            if stale_tree["upstream"]
            else "fetch and set an upstream tracking ref for this branch"
        )
        return _result(
            "refused_stale_tree",
            error=(
                f"migrate_product refused to read migrations from an "
                f"untrustworthy tree at {git_root} (branch "
                f"{stale_tree['branch']!r}, commits_behind="
                f"{stale_tree['commits_behind']}): {stale_tree['detail']} "
                f"Remedy: `{remedy}` in that tree, or pass worktree_path= "
                f"(or repo_root= in tests) to pin a different, up-to-date "
                f"tree. If you have manually verified this tree is safe, "
                f"pass allow_stale_tree=True (see docstring — almost "
                f"always wrong)."
            ),
        )

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

    # ── Resolve migration files — from `sha` via git, or the working tree ─────
    if sha:
        resolved_git_runner = git_runner or _DEFAULT_GIT_RUNNER
        try:
            all_files: list[Any] = _sorted_migrations_at_sha(
                git_root, sha, product, resolved_git_runner
            )
        except GitQueryError as exc:
            return _result(
                "error",
                error=(
                    f"migrate_product: cannot read migrations for {product!r} "
                    f"at sha {sha!r} from {git_root}: {exc}. The sha must be "
                    f"reachable from this tree's object database (e.g. "
                    f"already fetched) — `git fetch {git_root}` first if it "
                    "was just pushed elsewhere."
                ),
            )
        # `derived_schema` above is ALSO resolved from `app/main.py` AT
        # THIS SHA (F8(e)), not the working tree — see `_resolve_schema`'s
        # `sha=` branch, which calls `_schema_from_main_py_at_sha`.
    else:
        mig_dir = _migrations_dir(product, resolved_products_dir)
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

    # F8(c) (compliance review, 2026-09-24): read EVERY pending file's
    # content BEFORE running any DDL. In sha= mode each read is its own
    # `git show` call — if a LATER file's read failed mid-loop (a transient
    # git/network hiccup, or the sha becoming unreachable), the OLDER
    # migrations would already have been applied with no way to know
    # whether the remaining ones were even valid, leaving the DB in a
    # partially-applied state for no good reason. Fail BEFORE touching the
    # database if any pending file can't be read.
    try:
        pending_sql: list[tuple[Any, str, str]] = [
            (f, (content := f.read_text(encoding="utf-8")), _checksum(content))
            for f in pending
        ]
    except (OSError, GitQueryError) as exc:
        return _result(
            "error",
            skipped_already_applied=skipped,
            pending=pending_names,
            error=(
                f"migrate_product: could not read a pending migration's content "
                f"before applying any DDL — refusing to apply a partial set: {exc}"
            ),
        )

    newly_applied: list[str] = []
    for mig_file, sql, csum in pending_sql:
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
            "REFUSES (status='refused_stale_tree', exit_code=1 — never a silent "
            "green) before reading any migration file when the tree it would "
            "read from is untrustworthy: behind its upstream, has uncommitted "
            "changes under products/*/backend/migrations/, or any needed git "
            "query fails (fail-closed — never assumed clean). The 2026-09-17 "
            "incident this closes: a prod dry-run silently omitted a migration "
            "because the primary checkout was 26 commits behind origin/dev. "
            "Pass worktree_path when called from inside a git worktree — pins "
            "BOTH which tree is checked and which tree migrations are read "
            "from, same parameter name+semantics as predeploy_check. "
            "allow_stale_tree=True is the documented escape hatch (almost "
            "always wrong — see the tool's docstring) for a human-verified "
            "deliberate override; the staleness verdict still rides on the "
            "stale_tree key even when bypassed. "
            "R3 (2026-09-24, release-no-freeze): pass sha= to read migration "
            "FILES via `git show <sha>:<path>` — the EXACT set that existed at "
            "that commit — never the working tree; the stale-tree refusal is "
            "skipped entirely in this mode (nothing is 'stale' about a pinned "
            "historical commit). Typical caller: the sha noctus.dev.release "
            "just blessed, so what gets APPLIED is provably what got BLESSED. "
            "An unreadable sha (not fetched into this tree's object database) "
            "surfaces as status='error', never a silent fall-back to the "
            "working tree. "
            "CATALOG-SCOPE GUARD (2026-09-17, same incident): REFUSES "
            "(status='refused_catalog_scope', exit_code=1) before touching any "
            "credential or migration file unless the product is ativo=true AND "
            "deploy_scope='live' in the product catalog (or core) — reuses "
            "deploy_verify's catalog resolution, never a second hand-rolled "
            "read. Closes the incident: this tool once wrote to `erp` for "
            "erp-imobiliario (ativo=false, deploy_scope='dev'). "
            "allow_inactive=True is the escape hatch (almost always wrong — see "
            "the tool's docstring) for a deliberate, supervised reactivation; "
            "the catalog_scope verdict still rides on the result when bypassed. "
            "TOOLKIT-STALENESS GUARD (2026-09-18; R4 fresh-subprocess fallback "
            "2026-09-24): a confirm=True call on a STALE MCP server re-runs "
            "itself as a brand-new `python mcp/noctusai/cli.py "
            "--migrate-product ...` subprocess against the current on-disk "
            "code (status carries executed_via='fresh_subprocess') instead "
            "of refusing outright — acting on stale logic against production "
            "is the case that actually hurts, but the fix for that is fresh "
            "code, not a manual reconnect. It only REFUSES (status="
            "'refused_stale_toolkit', exit_code=1) when that fallback itself "
            "is impossible. A confirm=False (dry-run) call is never refused "
            "or subprocessed, only warned (toolkit_stale + a warnings "
            "entry), since it never touches the database. "
            "allow_stale_toolkit=True is the escape hatch (almost always "
            "wrong) that stays fully in-process. See "
            "noctus.dev.toolkit_freshness. "
            "Returns {status, exit_code, product, schema, schema_source, "
            "project_ref, applied, skipped_already_applied, pending, error, "
            "stale_tree, allow_stale_tree, catalog_scope, allow_inactive, sha, "
            "toolkit_stale}. "
            "KB § PATTERNS/backend/migrate-product-mcp-tool.md · "
            "KB § PATTERNS/architect/product-working-scope.md."
        ),
    )
    def _migrate_product(
        product: str,
        confirm: bool = False,
        target: str | None = None,
        sha: str | None = None,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
        schema: str | None = None,
        worktree_path: str | None = None,
        allow_stale_tree: bool = False,
        allow_inactive: bool = False,
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return migrate_product(
            product=product,
            confirm=confirm,
            target=target,
            sha=sha,
            project_ref=project_ref,
            schema=schema,
            worktree_path=worktree_path,
            allow_stale_tree=allow_stale_tree,
            allow_inactive=allow_inactive,
            allow_stale_toolkit=allow_stale_toolkit,
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
    "GitQueryError",
    "GitRunner",
    "FakeGitRunner",
    "SubprocessGitRunner",
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
    "_check_tree_staleness",
    "_dirty_migration_paths",
]
