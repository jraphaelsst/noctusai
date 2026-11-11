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


def test_routers_reach_the_database_through_the_org_bound_client():
    """A raw ``get_admin_client()`` in one of the nine routers is a router that must scope its own queries: allowed only
    with a same-line ``# org-scope-ok: <reason>`` (RPC checked in SQL, token-resolved public link, ...)."""
    offenders = []
    for name in ROUTERS:
        path = APP / "routers" / f"{name}_router.py"
        for ln, text in _calls(path, "get_admin_client"):
            if "org-scope-ok:" not in text:
                offenders.append(f"{path.name}:{ln}")
        assert "get_org_client" in path.read_text(encoding="utf-8"), f"{path.name} does not use get_org_client"
    assert not offenders, f"raw get_admin_client() without an `# org-scope-ok: <reason>` marker: {offenders}"


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


def test_declared_foreign_keys_mirror_the_migrations():
    """FOREIGN_KEYS is hand-declared from the schema; derive the truth from the migrations so it cannot drift."""
    derived: dict[str, dict[str, str]] = {}
    for path in sorted(MIGRATIONS.glob("0*.sql")):
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS orbity\.(\w+) \((.*?)\n\);", sql, re.S):
            table, body = m.groups()
            if table not in SERVICE_ONLY_TABLES:
                continue
            for col, parent in re.findall(r"^\s+(\w+)\s+UUID\b[^,\n]*?REFERENCES orbity\.(\w+)\(id\)", body, re.M):
                derived.setdefault(table, {})[col] = parent
            for col, parent in re.findall(r"^\s+(\w+)\s+UUID\s+(?:NOT NULL\s+)?(?:UNIQUE\s+)?\n?\s*REFERENCES orbity\.(\w+)\(id\)", body, re.M):
                derived.setdefault(table, {})[col] = parent
    derived = {t: {c: p for c, p in cols.items() if p in SERVICE_ONLY_TABLES} for t, cols in derived.items()}
    assert {t: v for t, v in derived.items() if v} == FOREIGN_KEYS


def test_frontend_never_reads_these_tables_through_postgrest():
    if not FRONTEND_SRC.exists():
        return
    hits = [str(p.relative_to(FRONTEND_SRC)) for p in FRONTEND_SRC.rglob("*.ts*")
            if re.search(r"\.from\(\s*['\"](%s)['\"]" % "|".join(sorted(SERVICE_ONLY_TABLES)), p.read_text(encoding="utf-8"))]
    assert not hits, f"direct PostgREST reads of a service-only table: {hits}"
