"""Structural tests for the org-picker rollout migrations (007 policies, 8 acting audit, 9 ready) of seed.

Every seed RLS policy that resolves the caller's org by an identity form
(current_org_id(), current_user_org_id(), an inline noctus_users subquery) must
resolve it through ``(SELECT public.current_org_id_for('seed'))`` instead --
the home org for everyone, the staff member's selected org while acting. The
policies migration is generated from the live ``pg_policies`` (2026-10-09); these
tests keep it honest against the migration files:

* nothing inside it still uses a home-only identity form (bar the api_tokens role checks);
* the (table, policy) set it alters == the set derived by walking the migrations
  (later DROP/CREATE/ALTER/RENAME wins);
* a policy added AFTER it with an identity form is rejected;
* no DO block builds policies dynamically (invisible to the static walk).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast")
from pglast import ast, enums, parse_sql  # noqa: E402
from pglast.stream import RawStream  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
FILE_A = MIGRATIONS / "007_org_picker_policies.sql"
FILE_B = MIGRATIONS / "008_org_picker_acting_audit.sql"
FILE_C = MIGRATIONS / "009_org_picker_ready.sql"


def _render(text: str) -> str:
    """The seed sync copies this test + the migrations into templates/product-seed with
    ``{{X}}`` placeholders; render them so the same test runs in both copies."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: f"tpl_{m.group(1).lower()}", text)


def _read(path: Path) -> str:
    return _render(path.read_text(encoding="utf-8"))


SCHEMA = _render("seed")
IDENTITY_FUNCS = {"current_org_id", "current_user_org_id"}

# Owner/admin role checks that stay keyed on the caller's own noctus_users row
# (the org predicate beside them IS converted). Only these may still read it.
KEPT_ROLE_CHECK = {
    ("api_tokens", "api_tokens_insert_own_org_admin"),
    ("api_tokens", "api_tokens_update_own_org_admin"),
}


def _nodes(obj):
    if isinstance(obj, ast.Node):
        yield obj
        for name in obj.__slots__:
            yield from _nodes(getattr(obj, name, None))
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            yield from _nodes(x)


def _identity_forms(*bodies) -> set[str]:
    found: set[str] = set()
    for body in bodies:
        for n in _nodes(body):
            if isinstance(n, ast.FuncCall):
                if n.funcname[-1].sval in IDENTITY_FUNCS:
                    found.add(n.funcname[-1].sval)
            elif isinstance(n, ast.RangeVar) and n.relname == "noctus_users":
                found.add("noctus_users")
    return found


def _acts_forms(*bodies) -> list[str]:
    out: list[str] = []
    for body in bodies:
        for n in _nodes(body):
            if isinstance(n, ast.FuncCall) and n.funcname[-1].sval == "current_org_id_for":
                out.append(n.args[0].val.sval)
    return out


def _in_schema(rel) -> bool:
    return (rel.schemaname or SCHEMA) == SCHEMA


def _walk(upto_exclusive: str | None = None):
    """Final static policy state across the migrations: {(table, policy): (file, qual, check)}."""
    pol: dict = {}
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if upto_exclusive and f.name >= upto_exclusive:
            break
        for s in parse_sql(_read(f)):
            n = s.stmt
            if isinstance(n, ast.CreatePolicyStmt) and _in_schema(n.table):
                pol[(n.table.relname, n.policy_name)] = (f.name, n.qual, n.with_check)
            elif isinstance(n, ast.AlterPolicyStmt) and _in_schema(n.table):
                k = (n.table.relname, n.policy_name)
                if k in pol:
                    fn, q, w = pol[k]
                    pol[k] = (f.name, n.qual or q, n.with_check or w)
            elif isinstance(n, ast.DropStmt) and n.removeType == enums.ObjectType.OBJECT_POLICY:
                for o in n.objects:
                    names = [x.sval for x in o]
                    if len(names) < 3 or names[0] == SCHEMA:
                        pol.pop((names[-2], names[-1]), None)
            elif isinstance(n, ast.DropStmt) and n.removeType == enums.ObjectType.OBJECT_TABLE:
                for o in n.objects:
                    names = [x.sval for x in o]
                    if len(names) < 2 or names[0] == SCHEMA:
                        for k in [k for k in pol if k[0] == names[-1]]:
                            pol.pop(k)
            elif isinstance(n, ast.RenameStmt) and n.renameType == enums.ObjectType.OBJECT_POLICY:
                if _in_schema(n.relation):
                    k = (n.relation.relname, n.subname)
                    if k in pol:
                        pol[(n.relation.relname, n.newname)] = pol.pop(k)
            elif isinstance(n, ast.RenameStmt) and n.renameType == enums.ObjectType.OBJECT_TABLE:
                if _in_schema(n.relation):
                    for k in [k for k in pol if k[0] == n.relation.relname]:
                        pol[(n.newname, k[1])] = pol.pop(k)
    return pol


def _stmts(path: Path):
    return [s.stmt for s in parse_sql(_read(path))]


def _alters():
    return [s for s in _stmts(FILE_A) if isinstance(s, ast.AlterPolicyStmt)]


def test_policies_parse_and_have_policies():
    assert len(_alters()) >= 4


def test_no_home_only_identity_form_left():
    for s in _alters():
        key = (s.table.relname, s.policy_name)
        bad = _identity_forms(s.qual, s.with_check)
        if key in KEPT_ROLE_CHECK:
            bad -= {"noctus_users"}
        assert not bad, f"{key} still uses {bad}"
    kept = {
        (s.table.relname, s.policy_name)
        for s in _alters()
        if "noctus_users" in _identity_forms(s.qual, s.with_check)
    }
    assert kept <= KEPT_ROLE_CHECK


def test_every_policy_uses_current_org_id_for_the_schema():
    for s in _alters():
        calls = _acts_forms(s.qual, s.with_check)
        assert calls, f"{s.table.relname}.{s.policy_name} has no current_org_id_for()"
        assert set(calls) == {SCHEMA}, f"{s.table.relname}.{s.policy_name}: {calls}"
        flat = " ".join(re.sub(r"\s+", " ", RawStream()(b)) for b in (s.qual, s.with_check) if b)
        assert flat.count("current_org_id_for") == flat.count("SELECT public.current_org_id_for"), (
            f"{s.table.relname}.{s.policy_name}: current_org_id_for not wrapped in (SELECT ...)"
        )


def test_alters_only_this_schema_no_storage_no_helper_functions():
    for s in _alters():
        assert s.table.schemaname == SCHEMA
    text = _read(FILE_A)
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
    assert "storage.objects" not in code
    assert not [s for s in _stmts(FILE_A) if isinstance(s, ast.CreateFunctionStmt)]


def test_has_core_070_guard_and_does_not_flip_ready():
    text = _read(FILE_A)
    assert "current_org_id_for(text)" in text.split("DO $guard$")[1].split("$guard$;")[0]
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
    assert "org_picker_ready" not in code


def test_covers_exactly_the_walked_identity_policies():
    walked = {
        k for k, (_f, q, w) in _walk(upto_exclusive=FILE_A.name).items() if _identity_forms(q, w)
    }
    got = {(s.table.relname, s.policy_name) for s in _alters()}
    assert not (walked - got), f"identity policies NOT converted: {sorted(walked - got)}"
    assert not (got - walked), f"alters policies the migrations do not define: {sorted(got - walked)}"


def test_no_unconverted_policy_after_the_conversion():
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name <= FILE_A.name:
            continue
        for s in parse_sql(_read(f)):
            n = s.stmt
            if isinstance(n, (ast.CreatePolicyStmt, ast.AlterPolicyStmt)) and _in_schema(n.table):
                if f.name in (FILE_B.name, FILE_C.name):
                    continue
                assert not _identity_forms(n.qual, n.with_check), (
                    f"{f.name}: {n.table.relname}.{n.policy_name} uses a home-only identity form "
                    f"-- use (SELECT public.current_org_id_for('{SCHEMA}'))"
                )


def test_no_dynamic_policy_ddl_in_do_blocks():
    """A DO block building policies (format()) is invisible to the static walk -- none may exist."""
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        for s in parse_sql(_read(f)):
            if isinstance(s.stmt, ast.DoStmt):
                body = "".join(a.arg.sval for a in s.stmt.args if a.defname == "as")
                if re.search(r"(CREATE|ALTER)\s+POLICY", body, re.I):
                    pytest.fail(f"{f.name}: DO block creates/alters a policy dynamically")


def test_acting_audit_migration():
    sql = _read(FILE_B)
    assert len(parse_sql(sql)) == 2
    assert "attach_acting_audit_triggers(text, text)" in sql.split("$guard$")[1]
    calls = re.findall(r"^SELECT public\.attach_acting_audit_triggers\(([^)]*)\);", sql, re.MULTILINE)
    assert calls == [f"'{SCHEMA}'"]


def test_ready_migration_is_last_and_scoped():
    sql = _read(FILE_C)
    assert len(parse_sql(sql)) == 1
    assert f"WHERE db_schema = '{SCHEMA}'" in sql and "slug" not in sql.split("UPDATE", 1)[1]
    assert re.search(r"org_picker_ready\s*=\s*true", sql)
    assert FILE_A.name < FILE_B.name < FILE_C.name
