"""SEC-1 (2026-09-28) — `ProductDependencies.get_user_role` never reads
`user_metadata.role`.

The platform never writes `user_metadata.role` (core's SSO sync writes
`noctus_role` / `org_role`), so the only party that could set it was the user,
via `auth.updateUser({data})` — and every `role in (...)` gate built on this
method honoured it. The role now comes from `public.noctus_users` only.
"""
from __future__ import annotations

from types import SimpleNamespace

from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.dependencies import ProductDependencies

SPOOF = {"role": "admin", "org_role": "owner", "noctus_role": "admin"}


class _Db:
    def __init__(self, rows):
        self._core = MockSupabaseClient(validate_schema=False, schema="public")
        self._core.set_table_data("noctus_users", rows)

    def get_core_client(self):
        return self._core


def _user(user_id="u1", metadata=None):
    return SimpleNamespace(id=user_id, user_metadata=metadata or {})


def test_spoofed_metadata_role_is_ignored_for_a_plain_member():
    deps = ProductDependencies(_Db([{"id": "u1", "org_id": "o", "org_role": "member", "role": "user"}]))
    assert deps.get_user_role(_user(metadata=SPOOF)) == "member"


def test_trusted_manager_org_role_is_returned():
    deps = ProductDependencies(_Db([{"id": "u1", "org_id": "o", "org_role": "manager", "role": "user"}]))
    assert deps.get_user_role(_user()) == "manager"


def test_trusted_owner_cascades_to_platform_admin():
    deps = ProductDependencies(_Db([{"id": "u1", "org_id": "o", "org_role": "owner", "role": "user"}]))
    assert deps.get_user_role(_user()) == "platform_admin"


def test_metadata_role_alone_never_grants_admin():
    """Row exists with no org role: least privilege, whatever metadata says."""
    deps = ProductDependencies(_Db([{"id": "u1", "org_id": None, "org_role": None, "role": "user"}]))
    assert deps.get_user_role(_user(metadata={"role": "admin"})) == "user"
