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


class TestFakeGrantAdministration:
    def test_add_list_remove_round_trip(self):
        repo = FakePermissionGrantRepository()
        grant = _run(repo.add_grant(user_id=_USER_A, permission=_PERMISSION, granted_by=_USER_B))
        assert grant.user_id == _USER_A and grant.granted_by == _USER_B
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is True
        listed = _run(repo.list_grants(permission=_PERMISSION))
        assert [g.user_id for g in listed] == [_USER_A]
        assert _run(repo.list_grants(permission="other:grant")) == []
        assert _run(repo.remove_grant(user_id=_USER_A, permission=_PERMISSION)) is True
        assert _run(repo.has_permission(user_id=_USER_A, permission=_PERMISSION)) is False
        assert _run(repo.remove_grant(user_id=_USER_A, permission=_PERMISSION)) is False

    def test_add_grant_is_idempotent_and_keeps_original_grantor(self):
        repo = FakePermissionGrantRepository()
        first = _run(repo.add_grant(user_id=_USER_A, permission=_PERMISSION, granted_by=_USER_B))
        again = _run(repo.add_grant(user_id=_USER_A, permission=_PERMISSION, granted_by="someone-else"))
        assert again == first
        assert len(_run(repo.list_grants(permission=_PERMISSION))) == 1

    def test_seeded_grants_are_listed(self):
        repo = FakePermissionGrantRepository([(_USER_A, _PERMISSION)])
        assert [g.user_id for g in _run(repo.list_grants(permission=_PERMISSION))] == [_USER_A]


class TestRealGrantAdministration:
    def _repo(self):
        client = MockSupabaseClient(validate_schema=False)
        return client, RealSupabasePermissionGrantRepository(client)

    def test_add_grant_inserts_bare_table_row(self):
        client, repo = self._repo()
        grant = _run(repo.add_grant(user_id=_USER_A, permission=_PERMISSION, granted_by=_USER_B))
        assert grant.user_id == _USER_A
        assert grant.granted_by == _USER_B
        rows = client.table("user_permission_grants").inserted_payloads
        assert rows == [{"user_id": _USER_A, "permission": _PERMISSION, "granted_by": _USER_B}]

    def test_add_grant_returns_existing_without_insert(self):
        client, repo = self._repo()
        client.set_table_data(
            "user_permission_grants",
            [{"user_id": _USER_A, "permission": _PERMISSION, "granted_by": None,
              "created_at": "2026-09-16T10:00:00Z"}],
        )
        grant = _run(repo.add_grant(user_id=_USER_A, permission=_PERMISSION, granted_by=_USER_B))
        assert grant.granted_by is None
        assert grant.created_at is not None and grant.created_at.tzinfo is not None
        assert client.table("user_permission_grants").inserted_payloads == []

    def test_list_grants_decodes_rows(self):
        client, repo = self._repo()
        client.set_table_data(
            "user_permission_grants",
            [{"user_id": _USER_A, "permission": _PERMISSION, "granted_by": _USER_B,
              "created_at": "2026-09-16T10:00:00+00:00"}],
        )
        grants = _run(repo.list_grants(permission=_PERMISSION))
        assert [(g.user_id, g.granted_by) for g in grants] == [(_USER_A, _USER_B)]

    def test_remove_grant_reports_absence(self):
        _client, repo = self._repo()
        assert _run(repo.remove_grant(user_id=_USER_A, permission=_PERMISSION)) is False
