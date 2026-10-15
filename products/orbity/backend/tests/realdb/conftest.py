"""
Fixtures for real-DB integration tests against a live Supabase instance
(orbity schema).

Uses the service-role key (bypasses RLS) for setup/teardown + CRUD. RLS
isolation is tested explicitly with anon/per-org user-scoped clients.

`core_db` targets ``public`` (org management); `orbity_db`/`fin_db` target
the ``orbity`` schema (both are the service-role client — kept as two names
so the financial and tasks/agenda realdb suites each read naturally).

Tests skip automatically when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are
not set (CI without secrets, or local dev without a Supabase project).

IMPORTANT: requires migrations 006_financial_core.sql + 007_tasks_agenda.sql
applied to the live Supabase project BEFORE running. The tech-lead applies
migrations at integration time.
"""
from __future__ import annotations

import os
import uuid

import pytest
from supabase import create_client
from supabase.lib.client_options import ClientOptions

pytestmark = pytest.mark.realdb


def _get_credentials():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping real-DB tests"
        )
    return url, key


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (org/user management)."""
    url, key = _get_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def orbity_db():
    """Service-role client for the orbity schema."""
    url, key = _get_credentials()
    return create_client(url, key, options=ClientOptions(schema="orbity"))


@pytest.fixture(scope="session")
def fin_db():
    """Service-role client for the orbity schema (financial tables)."""
    url, key = _get_credentials()
    return create_client(url, key, options=ClientOptions(schema="orbity"))


class _AnonQuery:
    """Proxy a PostgREST query builder; `execute()` maps SQLSTATE 42501 to NO ROWS.

    Migration 016 revoked table privileges from anon outright, so an anon read now
    fails with `permission denied` (42501) instead of returning an RLS-filtered
    empty set. Both outcomes mean "org A's rows are invisible to anon" — the
    property these tests assert — so the denial is normalised to `data == []`.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def _call(*a, **k):
            out = attr(*a, **k)
            return _AnonQuery(out) if hasattr(out, "execute") else out

        return _call

    def execute(self):
        from postgrest.exceptions import APIError

        try:
            return self._inner.execute()
        except APIError as exc:
            if getattr(exc, "code", None) == "42501":
                return type("DeniedResponse", (), {"data": [], "count": None})()
            raise


class _AnonIsolationClient:
    def __init__(self, inner):
        self._inner = inner

    def table(self, name):
        return _AnonQuery(self._inner.table(name))


@pytest.fixture(scope="session")
def anon_fin_db():
    """Anon-key client for RLS isolation tests.

    The anon key has no org claim → current_org_id() returns NULL → RLS
    USING (org_id = public.current_org_id()) evaluates to false for every row.
    This is how we assert org-isolation: org A's data is invisible to an anon
    (or wrong-org) JWT.
    """
    url, _ = _get_credentials()
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not anon_key:
        pytest.skip("SUPABASE_ANON_KEY not set — skipping RLS isolation tests")
    return _AnonIsolationClient(create_client(url, anon_key, options=ClientOptions(schema="orbity")))


@pytest.fixture(scope="session")
def test_org(core_db):
    """Create a test organization, yield it, then delete on teardown."""
    slug = f"test-financial-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB Financial Test {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture(scope="session")
def test_org_a(core_db):
    """Create a test organization A, yield it, then delete on teardown."""
    slug = f"test-tasks-a-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB Tasks Test A {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture(scope="session")
def test_org_b(core_db):
    """Create a test organization B for RLS isolation tests."""
    slug = f"test-tasks-b-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB Tasks Test B {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture
def cleanup(fin_db):
    """Collects (table, id) tuples and deletes them in reverse order after test."""
    records: list[tuple[str, str]] = []
    yield records
    for table, rid in reversed(records):
        try:
            fin_db.table(table).delete().eq("id", rid).execute()
        except Exception:
            pass
