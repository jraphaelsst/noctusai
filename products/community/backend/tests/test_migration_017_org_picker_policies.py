"""Structural tests for ``migrations/017_org_picker_policies.sql`` (org picker rollout, community).

Every community RLS policy that resolves the caller's org by the home-only identity form
(current_org_id(), current_user_org_id(), an inline noctus_users subquery) must resolve it
through ``(SELECT public.current_org_id_for('community'))`` instead -- the home org for everyone,
the staff member's selected org while acting. 017 is generated from the live ``pg_policies``;
these tests keep it honest against the migration files (same contract as social-wiring 211):

* nothing inside 017 still uses a home-only identity form for a policy;
* the (table, policy) set 017 alters == the set derived by walking the migrations (later
  DROP/CREATE/ALTER/RENAME wins) plus ``DYNAMIC_IDENTITY`` (policies built by DO/format()
  loops, invisible to a static walk; verified against live pg_policies on 2026-10-09);
* a policy added AFTER 017 with an identity form is rejected (it would silently stay home-only
  while ``org_picker_ready`` says otherwise);
* 018 attaches the acting-write audit triggers behind a core-072 guard, 019 flips the flag.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast")
from pglast import ast, enums, parse_sql  # noqa: E402
from pglast.stream import RawStream  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
FILE_MAIN = MIGRATIONS / "017_org_picker_policies.sql"
FILE_AUDIT = MIGRATIONS / "018_org_picker_acting_audit.sql"
FILE_READY = MIGRATIONS / "019_org_picker_ready.sql"
SCHEMA = "community"
IDENTITY_FUNCS = {"current_org_id", "current_user_org_id"}

# Identity-form policies created by DO loops (live-verified 2026-10-09).
DYNAMIC_IDENTITY: set[tuple[str, str]] = set()  # placeholder
_X = {
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
            if isinstance(n, ast.FuncCall) and n.funcname[-1].sval in IDENTITY_FUNCS:
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
    pol: dict = {}
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if upto_exclusive and f.name >= upto_exclusive:
            break
        for s in parse_sql(f.read_text(encoding="utf-8")):
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
    return pol


def _stmts(path):
    return [s.stmt for s in parse_sql(path.read_text(encoding="utf-8"))]


def _alters():
    return [s for s in _stmts(FILE_MAIN) if isinstance(s, ast.AlterPolicyStmt)]


def _code(path) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("--"))


def test_main_parses_and_has_policies():
    assert len(_alters()) == 74


def test_no_home_only_identity_form_left():
    for s in _alters():
        bad = _identity_forms(s.qual, s.with_check)
        assert not bad, f"{s.table.relname}.{s.policy_name} still uses {bad}"


def test_every_policy_uses_current_org_id_for_schema():
    for s in _alters():
        calls = _acts_forms(s.qual, s.with_check)
        assert calls, f"{s.table.relname}.{s.policy_name} has no current_org_id_for()"
        assert set(calls) == {SCHEMA}, f"{s.table.relname}.{s.policy_name}: {calls}"
        flat = " ".join(re.sub(r"\s+", " ", RawStream()(b)) for b in (s.qual, s.with_check) if b)
        assert flat.count("current_org_id_for") == flat.count("SELECT public.current_org_id_for"), (
            f"{s.table.relname}.{s.policy_name}: current_org_id_for not wrapped in (SELECT ...)"
        )


def test_alters_only_this_schema_and_no_storage():
    for s in _alters():
        assert s.table.schemaname == SCHEMA
    assert "storage.objects" not in _code(FILE_MAIN)


def test_role_checks_untouched():
    """eh_equipe()/current_org_role() are caller-role checks (no org identity): they stay as-is."""
    text = _code(FILE_MAIN)
    assert "noctus_users" not in text


def test_has_guard_and_does_not_flip_ready():
    text = FILE_MAIN.read_text(encoding="utf-8")
    assert "current_org_id_for(text)" in text.split("DO $guard$")[1].split("$guard$;")[0]
    assert "org_picker_ready" not in _code(FILE_MAIN)


def test_covers_exactly_the_walked_identity_policies():
    walked = {k for k, (_f, q, w) in _walk(upto_exclusive=FILE_MAIN.name).items() if _identity_forms(q, w)}
    expected = walked | DYNAMIC_IDENTITY
    got = {(s.table.relname, s.policy_name) for s in _alters()}
    assert not (expected - got), f"identity policies NOT converted: {sorted(expected - got)}"
    assert not (got - expected), f"alters policies the migrations do not define: {sorted(got - expected)}"


def test_no_unconverted_policy_after_main():
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name <= FILE_MAIN.name:
            continue
        for s in parse_sql(f.read_text(encoding="utf-8")):
            n = s.stmt
            if isinstance(n, (ast.CreatePolicyStmt, ast.AlterPolicyStmt)) and _in_schema(n.table):
                assert not _identity_forms(n.qual, n.with_check), (
                    f"{f.name}: {n.table.relname}.{n.policy_name} uses a home-only identity form "
                    f"-- use (SELECT public.current_org_id_for('{SCHEMA}'))"
                )


def test_no_unconverted_dynamic_policy():
    """A DO block building policies with format() is invisible to the static walk: after 017 none may use an identity form."""
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name[:3] <= "017":
            continue
        for s in parse_sql(f.read_text(encoding="utf-8")):
            if isinstance(s.stmt, ast.DoStmt):
                body = "".join(a.arg.sval for a in s.stmt.args if a.defname == "as")
                if re.search(r"(CREATE|ALTER)\s+POLICY", body, re.I):
                    assert not re.search(r"current_(user_)?org_id\(\)|noctus_users", body), f.name


def test_audit_migration_attaches_triggers_behind_guard():
    text = FILE_AUDIT.read_text(encoding="utf-8")
    assert "attach_acting_audit_triggers(text, text)" in text.split("DO $guard$")[1].split("$guard$;")[0]
    assert "RAISE EXCEPTION" in text
    calls = [
        s for s in _stmts(FILE_AUDIT)
        if isinstance(s, ast.SelectStmt)
    ]
    assert len(calls) == 1
    assert "attach_acting_audit_triggers('community')" in _code(FILE_AUDIT)


def test_ready_migration_flips_only_this_product():
    code = _code(FILE_READY)
    assert "UPDATE public.products" in code and "org_picker_ready = true" in code
    assert "slug = 'community'" in code and "db_schema = 'community'" in code
    # ready must come after both the conversion and the audit attach
    assert FILE_MAIN.name < FILE_AUDIT.name < FILE_READY.name
