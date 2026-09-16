"""Unit tests for `noctusai_lib.domain.permissions`.

Covers:
- `FakePermissionGrantRepository` Protocol contract (grant / revoke /
  has_permission round-trip; product-agnostic — no product name
  appears anywhere in the tested surface).
- `RealSupabasePermissionGrantRepository` (RPC-call shape via
  `MockSupabaseClient`).
- `make_permission_grant_repository` factory (fake vs real selection).

Network-free, deterministic. No monkey-patching of our own modules.
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.domain.permissions import (
    FakePermissionGrantRepository,
    PermissionGrantRepository,
    RealSupabasePermissionGrantRepository,
    make_permission_grant_repository,
)
from noctusai_lib.testing import MockSupabaseClient

_USER_A = "00000000-0000-4000-8000-0000000000aa"
_USER_B = "00000000-0000-4000-8000-0000000000bb"
_PERMISSION = "sample:generic-grant"


def _run(coro):
    return asyncio.run(coro)


class TestFakePermissionGrantRepository:
    def test_no_grant_denies(self):
        repo: PermissionGrantRepository = FakePermissionGrantRepository()
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_grant_then_check_allows(self):
        repo = FakePermissionGrantRepository()
        repo.grant(_USER_A, _PERMISSION)
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True

    def test_grant_is_scoped_to_user_and_permission(self):
        repo = FakePermissionGrantRepository()
        repo.grant(_USER_A, _PERMISSION)
        # Different user, same permission → denied.
        assert _run(repo.has_permission(user_id=_USER_B, permission=_PERMISSION)) is False
        # Same user, different permission → denied.
        assert _run(repo.has_permission(user_id=_USER_A, permission="other:grant")) is False

    def test_revoke_removes_grant(self):
        repo = FakePermissionGrantRepository()
        repo.grant(_USER_A, _PERMISSION)
        repo.revoke(_USER_A, _PERMISSION)
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_revoke_missing_grant_is_noop(self):
        repo = FakePermissionGrantRepository()
        repo.revoke(_USER_A, _PERMISSION)  # never granted — must not raise
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_initial_grants_seeded_at_construction(self):
        repo = FakePermissionGrantRepository(initial_grants=[(_USER_A, _PERMISSION)])
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True


class TestRealSupabasePermissionGrantRepository:
    def _client(self):
        return MockSupabaseClient(validate_schema=False)

    def test_rpc_true_grants(self):
        client = self._client()
        client.set_rpc_data("has_permission", True)
        repo = RealSupabasePermissionGrantRepository(client)

        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True

    def test_rpc_false_denies(self):
        client = self._client()
        client.set_rpc_data("has_permission", False)
        repo = RealSupabasePermissionGrantRepository(client)

        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_rpc_missing_data_defaults_to_deny(self):
        # No `set_rpc_data` call — mirrors an RPC the consumer has not
        # migrated yet. Must fail closed (deny), never raise or allow.
        client = self._client()
        repo = RealSupabasePermissionGrantRepository(client)

        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_custom_rpc_name(self):
        client = self._client()
        client.set_rpc_data("custom_has_permission", True)
        repo = RealSupabasePermissionGrantRepository(client, rpc_name="custom_has_permission")

        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True


class TestMakePermissionGrantRepository:
    def test_use_fake_true_returns_fake(self):
        repo = make_permission_grant_repository(use_fake=True)
        assert isinstance(repo, FakePermissionGrantRepository)

    def test_use_fake_true_seeds_initial_grants(self):
        repo = make_permission_grant_repository(
            use_fake=True, initial_grants=[(_USER_A, _PERMISSION)]
        )
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True

    def test_use_fake_false_without_client_raises(self):
        with pytest.raises(RuntimeError):
            make_permission_grant_repository(use_fake=False)

    def test_use_fake_false_with_client_returns_real(self):
        client = MockSupabaseClient(validate_schema=False)
        repo = make_permission_grant_repository(use_fake=False, supabase_client=client)
        assert isinstance(repo, RealSupabasePermissionGrantRepository)
