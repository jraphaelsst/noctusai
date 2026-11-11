"""Structural guard: the 23 tenant tables are service-only and reached ONLY through the org-bound client.

Why a test and not a runtime check: a router that reaches a tenant table with a raw client is correct on the day it is
written and a cross-tenant leak the day someone forgets one filter. These fail the build instead.
"""
import ast
import re
from pathlib import Path

from app.org_scope import FOREIGN_KEYS, SERVICE_ONLY_TABLES

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
MIGRATIONS = BACKEND / "migrations"
FRONTEND_SRC = BACKEND.parent / "frontend" / "src"

#: The nine routers moved off the user's JWT; the markers below are the only sanctioned raw-client uses.
ROUTERS = ("agenda", "automation", "clients", "content_plans", "crm", "meta_ads", "reports", "social_content", "tasks")


def _calls(path: Path, name: str):
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == name) or (isinstance(f, ast.Attribute) and f.attr == name):
                yield node.lineno, " ".join(lines[node.lineno - 1: node.end_lineno])


def test_no_orbity_code_uses_the_user_jwt_client_any_more():
    offenders = [f"{p.relative_to(APP)}:{ln}" for p in APP.rglob("*.py") if p.name != "dependencies.py"
                 for ln, _ in _calls(p, "get_user_client")]
    assert not offenders, f"get_user_client() reads under RLS, which migration 034 removed for these tables: {offenders}"


def _refs(path: Path, name: str):
    """Every use of ``name`` as a value (call, pass-through, alias), with the full text of its statement line(s)."""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        hit = (isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)) or (
            isinstance(node, ast.Attribute) and node.attr == name)
        if hit:
            yield node.lineno, " ".join(lines[node.lineno - 1: getattr(node, "end_lineno", node.lineno)])


def test_routers_and_services_reach_the_database_through_the_org_bound_client():
    """A raw ``get_admin_client`` in a router or a service is code that must scope its own queries: allowed only with a same-line
    ``# org-scope-ok: <reason>`` (RPC checked in SQL, token-resolved public link, a non-tenant store, ...)."""
    offenders = []
    files = [*(APP / "routers" / f"{n}_router.py" for n in ROUTERS), *(APP / "services").glob("*.py")]
    for path in files:
        for ln, text in _refs(path, "get_admin_client"):
            if "org-scope-ok:" not in text:
                offenders.append(f"{path.relative_to(APP)}:{ln}")
    assert not offenders, f"raw get_admin_client without an `# org-scope-ok: <reason>` marker: {offenders}"
    for name in ROUTERS:
        assert "get_org_client" in (APP / "routers" / f"{name}_router.py").read_text(encoding="utf-8"), name


def test_nothing_reaches_the_wrapped_client_behind_the_scoped_one():
    """The org-bound client hides its inner client (name-mangled); the only reader is the seed module itself."""
    offenders = []
    for path in APP.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "_OrgScopedClient__inner" in src or re.search(r"\b_raw\(", src):
            offenders.append(str(path.relative_to(APP)))
    assert not offenders, f"reaches around the org scope: {offenders}"


def test_routers_never_take_the_org_from_the_request_but_for_the_public_capture():
    """org_id comes from the authenticated context. The one path-borne org is the PUBLIC lead-capture URL (license-gated)."""
    for name in ROUTERS:
        src = (APP / "routers" / f"{name}_router.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_org_client":
                arg = node.args[0] if node.args else None
                assert isinstance(arg, ast.Name) and arg.id in {"org_id", "raw_org"}, f"{name}: get_org_client({ast.unparse(arg)})"


def _migration_034() -> str:
    return (MIGRATIONS / "034_orbity_service_only_batch3.sql").read_text(encoding="utf-8")


def test_migration_locks_every_table_to_the_service_role():
    sql = _migration_034()
    assert len(SERVICE_ONLY_TABLES) == 23
    for t in sorted(SERVICE_ONLY_TABLES):
        assert f"ALTER TABLE orbity.{t} ENABLE ROW LEVEL SECURITY;" in sql, t
        assert f'CREATE POLICY "service_role_bypass" ON orbity.{t} FOR ALL TO service_role USING (true) WITH CHECK (true);' in sql, t
        assert f"REVOKE ALL ON orbity.{t} FROM PUBLIC, anon, authenticated;" in sql, t
        assert f"GRANT ALL ON orbity.{t} TO service_role;" in sql, t
        assert f"COMMENT ON TABLE orbity.{t} IS 'tier:org';" in sql, t
    assert "TO authenticated" not in sql and "TO anon" not in sql and "GRANT SELECT" not in sql
    assert "DROP POLICY" in sql and "pg_policies" in sql  # the member policies of any name are removed


def test_no_later_migration_re_grants_a_locked_table_to_the_browser_roles():
    names = "|".join(sorted(SERVICE_ONLY_TABLES))
    pat = re.compile(rf"(GRANT\b[^;]*\bON\b[^;]*orbity\.({names})\b[^;]*\bTO\b[^;]*\b(anon|authenticated|PUBLIC)\b)", re.I | re.S)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name < "034":
            continue
        assert not pat.search(re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))), path.name


_COMMENT = re.compile(r"--[^\n]*")


def derive_foreign_keys(sqls: list[str], tables: set[str]) -> dict[str, dict[str, str]]:
    """``{child: {column: parent}}`` among ``tables``, from CREATE TABLE bodies AND ``ALTER TABLE ... ADD [COLUMN] ... REFERENCES`` /
    ``ADD [CONSTRAINT n] FOREIGN KEY (col) REFERENCES`` (a column added later is a reference too)."""
    out: dict[str, dict[str, str]] = {}
    ref = r"REFERENCES\s+orbity\.(\w+)\s*\(\s*id\s*\)"
    for raw in sqls:
        sql = _COMMENT.sub("", raw)
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS orbity\.(\w+) \((.*?)\n\);", sql, re.S):
            table, body = m.groups()
            for col, parent in re.findall(rf"^\s+(\w+)\s+UUID\b[^,\n]*?{ref}", body, re.M):
                out.setdefault(table, {})[col] = parent
            for col, parent in re.findall(rf"^\s+(\w+)\s+UUID\s+(?:NOT NULL\s+)?(?:UNIQUE\s+)?\n?\s*{ref}", body, re.M):
                out.setdefault(table, {})[col] = parent
        for m in re.finditer(r"ALTER TABLE\s+(?:IF EXISTS\s+)?(?:ONLY\s+)?orbity\.(\w+)\s+(.*?);", sql, re.S):
            table, body = m.groups()
            for col, parent in re.findall(rf"ADD\s+(?:COLUMN\s+)?(?:IF NOT EXISTS\s+)?(\w+)\s+UUID\b[^,;]*?{ref}", body, re.S | re.I):
                out.setdefault(table, {})[col] = parent
            for col, parent in re.findall(rf"FOREIGN KEY\s*\(\s*(\w+)\s*\)\s*{ref}", body, re.I):
                out.setdefault(table, {})[col] = parent
    return {t: {c: p for c, p in cols.items() if p in tables} for t, cols in out.items() if t in tables and any(p in tables for p in cols.values())}


def test_the_fk_extractor_sees_alter_table_references():
    sql = """
CREATE TABLE IF NOT EXISTS orbity.a (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL,
    b_id UUID REFERENCES orbity.b(id) ON DELETE SET NULL
);
    ALTER TABLE orbity.a ADD COLUMN IF NOT EXISTS c_id UUID REFERENCES orbity.c(id) ON DELETE CASCADE;
    ALTER TABLE orbity.a ADD CONSTRAINT a_d_fk FOREIGN KEY (d_id) REFERENCES orbity.d(id);
    -- ALTER TABLE orbity.a ADD COLUMN ghost UUID REFERENCES orbity.b(id);
    """
    assert derive_foreign_keys([sql], {"a", "b", "c", "d"}) == {"a": {"b_id": "b", "c_id": "c", "d_id": "d"}}


def test_declared_foreign_keys_mirror_the_migrations():
    """FOREIGN_KEYS is hand-declared from the schema; derive the truth from the migrations (CREATE and ALTER) so it cannot drift."""
    derived = derive_foreign_keys([p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("0*.sql"))], set(SERVICE_ONLY_TABLES))
    assert derived == FOREIGN_KEYS


# -- functions and default privileges (F2, F3) -------------------------------------------------------------------------
def _all_sql() -> dict[str, str]:
    return {p.name: _COMMENT.sub("", p.read_text(encoding="utf-8")) for p in sorted(MIGRATIONS.glob("0*.sql"))}


def test_every_orbity_function_is_locked_down():
    """Pinned search_path on every function (a SECURITY DEFINER with a mutable path is an injection seam) and no EXECUTE for the
    browser roles: a REVOKE ... FROM PUBLIC on every function that is not a trigger function (nobody calls those directly)."""
    sqls = _all_sql()
    everything = "\n".join(sqls.values())
    funcs = {}
    for name, sql in sqls.items():
        for m in re.finditer(r"CREATE (?:OR REPLACE )?FUNCTION\s+orbity\.(\w+)\s*\((.*?)\)\s*(.*?)(?:AS\s+\$)", sql, re.S | re.I):
            funcs[m.group(1)] = m.group(3)
    assert {"seed_default_lead_stages", "set_updated_at", "offboard_client"} <= set(funcs)
    bad = []
    for fn, header in funcs.items():
        pinned = re.search(r"SET\s+search_path", header, re.I) or re.search(rf"ALTER FUNCTION\s+orbity\.{fn}\s*\([^)]*\)\s+SET\s+search_path", everything, re.I)
        if not pinned:
            bad.append(f"{fn}: search_path not pinned")
        if not re.search(r"RETURNS\s+trigger", header, re.I) and not re.search(rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+orbity\.{fn}\s*\([^)]*\)\s+FROM\s+PUBLIC", everything, re.I):
            bad.append(f"{fn}: EXECUTE not revoked from PUBLIC")
        if not re.search(r"RETURNS\s+trigger", header, re.I) and not re.search(rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+orbity\.{fn}\s*\([^)]*\)\s+TO\s+service_role", everything, re.I):
            bad.append(f"{fn}: not granted to service_role")
    assert not bad, bad


def test_the_browser_roles_hold_nothing_but_status_pagina():
    """001 granted ALL on every FUTURE table to `authenticated`; 035 revokes the defaults AND sweeps what exists. After the last
    sweep no migration may GRANT a table/sequence/function to a browser role (the one deliberate surface is status_pagina)."""
    sqls = _all_sql()
    sweep = max(n for n, s in sqls.items() if re.search(r"REVOKE ALL ON ALL TABLES IN SCHEMA orbity FROM PUBLIC, anon, authenticated", s))
    s = sqls[sweep]
    assert re.search(r"ALTER DEFAULT PRIVILEGES IN SCHEMA orbity REVOKE ALL ON TABLES FROM[^;]*authenticated", s)
    assert re.search(r"ALTER DEFAULT PRIVILEGES IN SCHEMA orbity REVOKE ALL ON SEQUENCES FROM[^;]*anon[^;]*authenticated", s)
    assert re.search(r"REVOKE ALL ON ALL SEQUENCES IN SCHEMA orbity FROM PUBLIC, anon, authenticated", s)
    assert re.search(r"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA orbity FROM PUBLIC, anon, authenticated", s)
    grant = re.compile(r"GRANT\b(?P<what>[^;]*?)\bON\b(?P<on>[^;]*?)\bTO\b(?P<to>[^;]*);", re.I | re.S)
    leaks = []
    for name, sql in sqls.items():
        if name < sweep:
            continue
        for m in grant.finditer(sql):
            roles = {r.strip().lower() for r in m.group("to").split(",")}
            if roles & {"anon", "authenticated", "public"} and "status_pagina" not in m.group("on"):
                leaks.append(f"{name}: {m.group(0)[:100]}")
    assert not leaks, leaks


def test_frontend_never_reads_these_tables_through_postgrest():
    if not FRONTEND_SRC.exists():
        return
    hits = [str(p.relative_to(FRONTEND_SRC)) for p in FRONTEND_SRC.rglob("*.ts*")
            if re.search(r"\.from\(\s*['\"](%s)['\"]" % "|".join(sorted(SERVICE_ONLY_TABLES)), p.read_text(encoding="utf-8"))]
    assert not hits, f"direct PostgREST reads of a service-only table: {hits}"
