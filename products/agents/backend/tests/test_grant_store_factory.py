"""`get_grant_store` follows the seed IO factory rule (KB § PATTERNS/backend/seed-fake-real-adapter.md): the Fake is a
dev/test convenience only. In a deploy context without a service-role key it REFUSES instead of handing back an
in-memory ledger -- a Fake there would let a platform admin mint and deliver real tokens whose grant is recorded
nowhere (and every channel call would then 403 with no trace of why)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.grants.store import FakeGrantStore, get_grant_store


def test_no_key_outside_deploy_is_the_fake():
    assert isinstance(get_grant_store(SimpleNamespace(supabase_service_role_key=None), deploy_context=False),
                      FakeGrantStore)


def test_no_key_in_a_deploy_context_refuses_the_fake():
    with pytest.raises(RuntimeError, match="grant store"):
        get_grant_store(SimpleNamespace(supabase_service_role_key=None), deploy_context=True)


def test_deploy_context_defaults_to_the_seed_signal(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="grant store"):
        get_grant_store(SimpleNamespace(supabase_service_role_key=""))
