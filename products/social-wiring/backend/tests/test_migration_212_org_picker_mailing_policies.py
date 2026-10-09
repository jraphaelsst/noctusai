"""Structural tests for ``migrations/212_org_picker_mailing_policies.sql``.

Same contract as 211 for social-wiring's own ``mailing`` schema: every identity-form
policy there resolves the org through ``(SELECT public.current_org_id_for('social_wiring'))``
(the selection is keyed by the PRODUCT; `mailing` belongs to its chain). 211's helpers are reused.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast")
from pglast import ast, enums, parse_sql  # noqa: E402
from pglast.stream import RawStream  # noqa: E402

from tests.test_migration_211_org_picker_policies import (  # noqa: E402
    MIGRATIONS,
    _acts_forms,
    _identity_forms,
)

SCHEMA = "mailing"
FILE_212 = MIGRATIONS / "212_org_picker_mailing_policies.sql"


def _alters():
    return [s.stmt for s in parse_sql(FILE_212.read_text(encoding="utf-8")) if isinstance(s.stmt, ast.AlterPolicyStmt)]


def _walk_mailing():
    pol: dict = {}
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name >= FILE_212.name:
            break
        for s in parse_sql(f.read_text(encoding="utf-8")):
            n = s.stmt
            if isinstance(n, ast.CreatePolicyStmt) and n.table.schemaname == SCHEMA:
                pol[(n.table.relname, n.policy_name)] = (n.qual, n.with_check)
            elif isinstance(n, ast.DropStmt) and n.removeType == enums.ObjectType.OBJECT_POLICY:
                for o in n.objects:
                    names = [x.sval for x in o]
                    if names[0] == SCHEMA:
                        pol.pop((names[-2], names[-1]), None)
    return pol


def test_212_parses_with_guard():
    assert len(_alters()) == 15
    assert "current_org_id_for(text)" in FILE_212.read_text(encoding="utf-8").split("DO $guard$")[1]


def test_212_no_home_only_identity_left_and_uses_social_wiring_literal():
    for s in _alters():
        assert s.table.schemaname == SCHEMA
        assert not _identity_forms(s.qual, s.with_check), s.policy_name
        calls = _acts_forms(s.qual, s.with_check)
        assert calls and set(calls) == {"social_wiring"}, s.policy_name
        flat = " ".join(re.sub(r"\s+", " ", RawStream()(b)) for b in (s.qual, s.with_check) if b)
        assert flat.count("current_org_id_for") == flat.count("SELECT public.current_org_id_for")


def test_212_covers_exactly_the_walked_identity_policies():
    walked = {k for k, (q, w) in _walk_mailing().items() if _identity_forms(q, w)}
    got = {(s.table.relname, s.policy_name) for s in _alters()}
    assert walked == got, (sorted(walked - got), sorted(got - walked))


def test_no_mailing_identity_policy_after_212():
    for f in sorted(MIGRATIONS.glob("[0-9]*.sql")):
        if f.name <= FILE_212.name:
            continue
        for s in parse_sql(f.read_text(encoding="utf-8")):
            n = s.stmt
            if isinstance(n, (ast.CreatePolicyStmt, ast.AlterPolicyStmt)) and n.table.schemaname == SCHEMA:
                assert not _identity_forms(n.qual, n.with_check), f"{f.name}: {n.policy_name}"
