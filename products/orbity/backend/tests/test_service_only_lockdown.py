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


def _reaches_around(src: str) -> list[int]:
    """Lines that read the wrapped client / builder behind an org-bound result: ``_OrgScopedClient__inner``, ``_raw(``, or an
    ``._inner`` read off ``get_org_client(...)`` / a ``.table(...)`` call (an unrelated class's own ``_inner`` is not this)."""
    hits = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and node.attr in {"_OrgScopedClient__inner", "_inner"} or (
                isinstance(node, ast.Attribute) and node.attr.startswith("_OrgScopedTable__")):
            base = ast.unparse(node.value)
            if node.attr != "_inner" or "get_org_client(" in base or ".table(" in base or base.endswith("org_client"):
                hits.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_raw":
            hits.append(node.lineno)
    return hits


def test_the_reach_around_detector_sees_inner_on_org_client_results():
    assert _reaches_around("x = get_org_client(o).table('t')._inner.select()") == [1]
    assert _reaches_around("c = get_org_client(o)\nc._OrgScopedClient__inner.table('t')") == [2]
    assert _reaches_around("class A:\n    def f(self):\n        return self._inner.go()") == []


def test_nothing_reaches_the_wrapped_client_behind_the_scoped_one():
    """The org-bound client and its table builder hide what they wrap (name-mangled); the only reader is the seed module."""
    offenders = [f"{p.relative_to(APP)}:{ln}" for p in APP.rglob("*.py") for ln in _reaches_around(p.read_text(encoding="utf-8"))]
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


def _arg_types(arglist: str) -> tuple[str, ...]:
    """``p_org_id UUID, p_n INTEGER DEFAULT 5`` -> ``('uuid', 'integer')`` (names and defaults dropped, case folded)."""
    out, depth, cur = [], 0, ""
    for ch in arglist + ",":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                tokens = re.split(r"\s+DEFAULT\s+|\s*=\s*", cur.strip(), flags=re.I)[0].split()
                out.append(" ".join(tokens[1:] if len(tokens) > 1 else tokens).lower())
            cur = ""
        else:
            cur += ch
    return tuple(out)


_FN = r"(?:orbity\.)?(\w+)\s*\(([^)]*)\)"


def _function_states(sqls: dict[str, str]) -> dict[tuple[str, tuple[str, ...]], dict]:
    """Per (name, arg types): the LATEST create (file + header) and every revoke / grant / search_path pin, in migration order. A
    DROP FUNCTION forgets the privileges (a re-CREATE starts again from the default PUBLIC execute); an overload is its own key."""
    states: dict[tuple[str, tuple[str, ...]], dict] = {}
    for fname, sql in sqls.items():
        events = []
        for m in re.finditer(rf"CREATE (?:OR REPLACE )?FUNCTION\s+{_FN}\s*(.*?)(?:AS\s+\$)", sql, re.S | re.I):
            events.append((m.start(), "create", m.group(1), _arg_types(m.group(2)), m.group(3)))
        for m in re.finditer(rf"DROP FUNCTION\s+(?:IF EXISTS\s+)?{_FN}", sql, re.I):
            events.append((m.start(), "drop", m.group(1), _arg_types(m.group(2)), ""))
        for m in re.finditer(rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+{_FN}\s+FROM\s+([^;]*);", sql, re.I):
            events.append((m.start(), "revoke", m.group(1), _arg_types(m.group(2)), m.group(3)))
        for m in re.finditer(rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{_FN}\s+TO\s+service_role", sql, re.I):
            events.append((m.start(), "grant", m.group(1), _arg_types(m.group(2)), ""))
        for m in re.finditer(rf"ALTER FUNCTION\s+{_FN}\s+SET\s+search_path", sql, re.I):
            events.append((m.start(), "pin", m.group(1), _arg_types(m.group(2)), ""))
        for _pos, kind, name, types, extra in sorted(events):
            st = states.setdefault((name, types), {})
            if kind in ("create", "drop"):
                st.clear()
                if kind == "create":
                    st.update(file=fname, header=extra, revoked=False, granted=False, pinned=bool(re.search(r"SET\s+search_path", extra, re.I)))
            elif st:
                if kind == "revoke":
                    st["revoked"] = "public" in extra.lower()
                elif kind == "grant":
                    st["granted"] = True
                elif kind == "pin":
                    st["pinned"] = True
    return {k: v for k, v in states.items() if v}


def test_the_function_checker_keys_on_signature_and_latest_create():
    """Unqualified names, overloads and a DROP+CREATE must not pass on an earlier REVOKE."""
    sqls = {
        "001.sql": "CREATE FUNCTION f(p_a UUID) RETURNS void LANGUAGE sql SET search_path = '' AS $$ SELECT 1 $$;\n"
                   "REVOKE ALL ON FUNCTION f(UUID) FROM PUBLIC;\nGRANT EXECUTE ON FUNCTION f(UUID) TO service_role;",
        "002.sql": "CREATE FUNCTION orbity.f(p_a UUID, p_b INTEGER DEFAULT 1) RETURNS void LANGUAGE sql AS $$ SELECT 1 $$;",
        "003.sql": "DROP FUNCTION orbity.f(UUID);\nCREATE FUNCTION orbity.f(p_a UUID) RETURNS void LANGUAGE sql AS $$ SELECT 1 $$;",
    }
    st = _function_states(sqls)
    assert st[("f", ("uuid",))]["revoked"] is False and st[("f", ("uuid",))]["pinned"] is False  # re-created after the DROP
    assert st[("f", ("uuid", "integer"))]["revoked"] is False  # the overload never inherits f(uuid)'s REVOKE


def test_every_orbity_function_is_locked_down():
    """Pinned search_path on every function (a SECURITY DEFINER with a mutable path is an injection seam) and no EXECUTE for the
    browser roles: a REVOKE ... FROM PUBLIC (+ GRANT to service_role) on every function that is not a trigger function. Keyed on
    name + argument types, qualified or not (search_path is orbity), judged from the LATEST create."""
    states = _function_states(_all_sql())
    assert {"seed_default_lead_stages", "set_updated_at", "offboard_client"} <= {n for n, _t in states}
    bad = []
    for (fn, types), st in states.items():
        trigger = bool(re.search(r"RETURNS\s+trigger", st["header"], re.I))
        if not st["pinned"]:
            bad.append(f"{fn}{types}: search_path not pinned")
        if not trigger and not st["revoked"]:
            bad.append(f"{fn}{types}: EXECUTE not revoked from PUBLIC")
        if not trigger and not st["granted"]:
            bad.append(f"{fn}{types}: not granted to service_role")
    assert not bad, bad


def test_the_browser_roles_hold_nothing_but_status_pagina_select():
    """001 granted ALL on every FUTURE table to `authenticated`; 035 revokes the defaults AND sweeps what exists. After the last
    sweep no migration may GRANT a table/sequence/function to a browser role; the one deliberate surface is SELECT on
    status_pagina (writes go through the seed admin router with the service role)."""
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
            what = m.group("what").strip().upper()
            if roles & {"anon", "authenticated", "public"} and not ("status_pagina" in m.group("on") and what == "SELECT"):
                leaks.append(f"{name}: {m.group(0)[:100]}")
    assert not leaks, leaks


def test_frontend_never_reads_these_tables_through_postgrest():
    if not FRONTEND_SRC.exists():
        return
    hits = [str(p.relative_to(FRONTEND_SRC)) for p in FRONTEND_SRC.rglob("*.ts*")
            if re.search(r"\.from\(\s*['\"](%s)['\"]" % "|".join(sorted(SERVICE_ONLY_TABLES)), p.read_text(encoding="utf-8"))]
    assert not hits, f"direct PostgREST reads of a service-only table: {hits}"
