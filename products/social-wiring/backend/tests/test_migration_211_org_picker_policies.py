"""Structural tests for ``migrations/211_org_picker_policies.sql`` (org picker, pilot).

Every social_wiring RLS policy that resolves the caller's org by an identity
form (current_org_id(), current_user_org_id(), an inline noctus_users
subquery) must resolve it through ``(SELECT public.current_org_id_for('social_wiring'))``
instead -- the home org for everyone, the staff member's selected org while
acting. 211 is generated from the live ``pg_policies``; these tests keep it
honest against the migration files:

* nothing inside 211 still uses a home-only identity form for a policy;
* the (table, policy) set 211 alters == the set derived by walking the
  migrations (later DROP/CREATE/ALTER/RENAME wins);
* a policy added by a migration AFTER 211 with an identity form is rejected
  (it would silently stay home-only while ``org_picker_ready`` says otherwise).

Policies created by DO/format() loops (034, 046, 060, 065, 101) are invisible to
a static walk; ``DYNAMIC_IDENTITY`` pins them (verified against live pg_policies
on 2026-10-08). A new DO-loop policy trips ``test_no_unconverted_dynamic_policy``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast")
from pglast import ast, enums, parse_sql  # noqa: E402
from pglast.stream import RawStream  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
FILE_211 = MIGRATIONS / "211_org_picker_policies.sql"
SCHEMA = "social_wiring"
IDENTITY_FUNCS = {"current_org_id", "current_user_org_id"}

# Static-walk artefacts: these tables were renamed by DDL the walker cannot follow
# (046: clients -> marcas, mc_brand_owners -> mc_brand_owners_legacy); their live
# policies are accounted for under DYNAMIC_IDENTITY / the new names.
RENAMED_AWAY_TABLES = {"clients", "mc_brand_owners"}

# Owner/admin role checks that stay keyed on the caller's own noctus_users row
# (the org predicate beside them IS converted). Only these may still read it.
KEPT_ROLE_CHECK = {
    ("api_tokens", "api_tokens_insert_own_org_admin"),
    ("api_tokens", "api_tokens_update_own_org_admin"),
    ("portal_lead_forward_targets", "portal_lead_forward_targets_write_own_org_admin"),
    ("portal_receiver_tokens", "portal_receiver_tokens_insert_own_org_admin"),
    ("portal_receiver_tokens", "portal_receiver_tokens_update_own_org_admin"),
}

# Identity-form policies created/renamed by DO loops (live-verified 2026-10-08).
DYNAMIC_IDENTITY = {
    ("atendimentos", "atendimentos_own_org"),
    ("campanha_imoveis", "campanha_imoveis_select_own_org"),
    ("campanha_solicitacoes", "campanha_solicitacoes_select_own_org"),
    ("campanha_veiculacoes", "campanha_veiculacoes_select_own_org"),
    ("campanhas", "campanhas_select_own_org"),
    ("marcas", "marcas_delete_own_org"),
    ("marcas", "marcas_insert_own_org"),
    ("marcas", "marcas_select_own_org"),
    ("marcas", "marcas_update_own_org"),
    ("permuta_ativos", "permuta_ativos_select_own_org"),
    ("permuta_ativos", "permuta_ativos_write_own_org"),
    ("permuta_interesses", "permuta_interesses_select_own_org"),
    ("permuta_interesses", "permuta_interesses_write_own_org"),
    ("permuta_matches", "permuta_matches_select_own_org"),
    ("permuta_matches", "permuta_matches_write_own_org"),
    ("pipeline_movimentos", "pipeline_movimentos_own_org"),
    ("pipeline_stages", "pipeline_stages_own_org"),
    ("processos_venda", "processos_venda_own_org"),
}


def _nodes(obj):
    """Yield every pglast Node under ``obj`` (depth-first)."""
    if isinstance(obj, ast.Node):
        yield obj
        for name in obj.__slots__:
            yield from _nodes(getattr(obj, name, None))
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            yield from _nodes(x)


def _identity_forms(*bodies) -> set[str]:
    """Home-only org identity forms referenced in the given expression nodes."""
    found: set[str] = set()
    for body in bodies:
        for n in _nodes(body):
            if isinstance(n, ast.FuncCall):
                fn = n.funcname[-1].sval
                if fn in IDENTITY_FUNCS:
                    found.add(fn)
            elif isinstance(n, ast.RangeVar) and n.relname == "noctus_users":
                found.add("noctus_users")
    return found


def _acts_forms(*bodies) -> list[str]:
    """Args of every current_org_id_for(...) call (string literals)."""
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


def _stmts_211():
    return [s.stmt for s in parse_sql(FILE_211.read_text(encoding="utf-8"))]


def _alters_211():
    return [s for s in _stmts_211() if isinstance(s, ast.AlterPolicyStmt)]


def test_211_parses_and_has_policies():
    assert len(_alters_211()) > 100


def test_211_no_home_only_identity_form_left():
    for s in _alters_211():
        key = (s.table.relname, s.policy_name)
        bad = _identity_forms(s.qual, s.with_check)
        if key in KEPT_ROLE_CHECK:
            bad -= {"noctus_users"}
        assert not bad, f"{key} still uses {bad}"
    kept = {(s.table.relname, s.policy_name) for s in _alters_211() if "noctus_users" in _identity_forms(s.qual, s.with_check)}
    assert kept == KEPT_ROLE_CHECK


def test_211_every_policy_uses_current_org_id_for_social_wiring():
    for s in _alters_211():
        calls = _acts_forms(s.qual, s.with_check)
        assert calls, f"{s.table.relname}.{s.policy_name} has no current_org_id_for()"
        assert set(calls) == {SCHEMA}, f"{s.table.relname}.{s.policy_name}: {calls}"
        # wrapped in a scalar sub-select (planned once, not per row)
        flat = " ".join(
            re.sub(r"\s+", " ", RawStream()(b)) for b in (s.qual, s.with_check) if b
        )
        assert flat.count("current_org_id_for") == flat.count("SELECT public.current_org_id_for"), (
            f"{s.table.relname}.{s.policy_name}: current_org_id_for not wrapped in (SELECT ...)"
        )


def test_211_alters_only_social_wiring_and_no_storage():
    for s in _alters_211():
        assert s.table.schemaname == SCHEMA
    assert "storage.objects" not in FILE_211.read_text(encoding="utf-8").replace("-- ", "").split("DO $guard$")[1]


def test_211_helper_function_converted():
    fns = [s for s in _stmts_211() if isinstance(s, ast.CreateFunctionStmt)]
    assert [f.funcname[-1].sval for f in fns] == ["fotos_lote_visivel"]
    body = FILE_211.read_text(encoding="utf-8").split("CREATE OR REPLACE FUNCTION")[1].split("$function$")[1]
    assert "current_org_id_for('social_wiring')" in body
    assert not re.search(r"(?<!_for)\bcurrent_org_id\(\)", body)


def test_211_has_guard_and_does_not_flip_ready():
    text = FILE_211.read_text(encoding="utf-8")
    assert "current_org_id_for(text)" in text.split("DO $guard$")[1].split("$guard$;")[0]
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
    assert "org_picker_ready" not in code


def test_211_covers_exactly_the_walked_identity_policies():
    walked = {
        k
        for k, (_f, q, w) in _walk(upto_exclusive=FILE_211.name).items()
        if _identity_forms(q, w) and k[0] not in RENAMED_AWAY_TABLES
    }
    expected = walked | DYNAMIC_IDENTITY
    got = {(s.table.relname, s.policy_name) for s in _alters_211()}
    assert not (expected - got), f"identity policies NOT converted by 211: {sorted(expected - got)}"
    assert not (got - expected), f"211 alters policies the migrations do not define: {sorted(got - expected)}"


def test_no_unconverted_policy_after_211():
    """A migration numbered after 211 must create org-scoped policies via current_org_id_for."""
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name <= FILE_211.name:
            continue
        for s in parse_sql(f.read_text(encoding="utf-8")):
            n = s.stmt
            if isinstance(n, (ast.CreatePolicyStmt, ast.AlterPolicyStmt)) and _in_schema(n.table):
                assert not _identity_forms(n.qual, n.with_check), (
                    f"{f.name}: {n.table.relname}.{n.policy_name} uses a home-only identity form "
                    "-- use (SELECT public.current_org_id_for('social_wiring'))"
                )


def _do_bodies(path):
    for s in parse_sql(path.read_text(encoding="utf-8")):
        if isinstance(s.stmt, ast.DoStmt):
            yield "".join(a.arg.sval for a in s.stmt.args if a.defname == "as")


def test_no_unconverted_dynamic_policy():
    """A DO block that builds policies with format() is invisible to the static walk.

    Only the known loops (pinned in DYNAMIC_IDENTITY) may do it before 211; after
    211 a DO block must not create a policy on an identity form at all.
    """
    known = {"034", "046", "060", "065", "101", "209", "211"}
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        for body in _do_bodies(f):
            creates = re.search(r"(CREATE|ALTER)\s+POLICY", body, re.I)
            if not creates:
                continue
            if f.name[:3] > "211":
                assert not re.search(r"current_(user_)?org_id\(\)|noctus_users", body), (
                    f"{f.name}: DO block creates an identity-form policy -- use current_org_id_for"
                )
            elif "format(" in body and f.name[:3] not in known:
                pytest.fail(f"{f.name}: dynamic policy DDL not pinned in DYNAMIC_IDENTITY")
