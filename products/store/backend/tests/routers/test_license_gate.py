"""Round 2 — store is license-gated server-side like every product.

`require_store_admin` / `get_store_admin_org` ride the gated `get_current_user`, so
the CALLER's effective org must hold the `store` license (403 `org_sem_licenca`),
while key/data scoping stays on STORE_ORG_ID. Shop buyers are anonymous: the public
routes declare no auth dependency and stay untouched. Strict `== 403` / `== 401`.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate

ORG = "00000000-0000-0000-0000-00000000000a"


@pytest.fixture
def gate(client):
    sb = client.mock_supabase
    # the mock auth user id comes from MockUser(); resolve it for the trusted row
    uid = sb.auth.get_user.return_value.user.id
    sb.set_table_data("noctus_users", [{"id": uid, "org_id": ORG, "org_role": "owner", "role": "user"}])
    yield sb
    configure_license_gate(None)


def _set(licensed: bool, sb):
    configure_license_gate(
        "store",
        FakeLicenseChecker(allow_all=False, licensed={(ORG, "store")} if licensed else set()),
        get_core_client=lambda: sb,
    )


def test_store_get_current_user_is_gated_by_construction():
    from app.dependencies import get_current_user

    assert hasattr(get_current_user, "ungated")


def test_unlicensed_caller_is_403_on_admin_routes(client, gate):
    # the license gate (inside get_current_user) answers BEFORE the admin allow-list
    _set(False, gate)
    resp = client.get("/api/admin/settings")
    assert resp.status_code == 403
    assert resp.json()["code"] == "org_sem_licenca"


def test_public_routes_untouched_for_unlicensed(client, gate):
    _set(False, gate)
    assert client.get("/api/health").status_code == 200
