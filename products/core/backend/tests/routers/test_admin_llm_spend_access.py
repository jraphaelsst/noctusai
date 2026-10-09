"""Who may READ an org's LLM spend — GET /api/admin/llm-spend/{org_id}.

Owner decision 2026-10-09 ("org admins see their own"): a platform admin reads
any org; an org owner/admin reads ONLY their own org; everyone else is 403, a
missing/invalid bearer is 401. Roles and org come from the trusted
`noctus_users` row (`get_trusted_db`), never `user_metadata` — the rows below
are that row, and the real dependency runs: only the session user, the DB
client and the spend calculator are swapped, all through
`app.dependency_overrides`.

The bug this closes: the seed `<LLMSpendBadge/>` polls this endpoint for every
org owner/admin, and the old platform-admin-only gate answered 403 — a red
"Acesso restrito a administradores" toast on every page, fleet-wide.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.mfa.gate import MfaGateConfig
from noctusai_lib.api.auth.mfa.policy import FakeMfaPolicy

from app.main import app
from app.routers.admin_llm_spend import get_spend_calculator
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, ORG_ID, OTHER_ORG_ID, OWNER_USER, make_ctx

ORG_ADMIN_USER = "dddddddd-dddd-dddd-dddd-dddddddddddd"
MANAGER_USER = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
NO_ORG_OWNER = "ffffffff-ffff-ffff-ffff-ffffffffffff"
NO_ORG_PLATFORM_ADMIN = "99999999-9999-9999-9999-999999999999"
CUSTOMER_USER = "77777777-7777-7777-7777-777777777777"

USERS = [
    {"id": ADMIN_USER, "role": "admin", "org_role": "member", "org_id": OTHER_ORG_ID},
    {"id": OWNER_USER, "role": "user", "org_role": "owner", "org_id": ORG_ID},
    {"id": MEMBER_USER, "role": "user", "org_role": "member", "org_id": ORG_ID},
    {"id": ORG_ADMIN_USER, "role": "user", "org_role": "admin", "org_id": ORG_ID},
    {"id": MANAGER_USER, "role": "user", "org_role": "manager", "org_id": ORG_ID},
    {"id": NO_ORG_OWNER, "role": "user", "org_role": "owner", "org_id": None},
    {"id": NO_ORG_PLATFORM_ADMIN, "role": "admin", "org_role": None, "org_id": None},
    # SEC-2 end-customer role (noctusai_lib.primitives.roles.CUSTOMER_ORG_ROLES).
    {"id": CUSTOMER_USER, "role": "user", "org_role": "membro", "org_id": ORG_ID},
]

STATUS = {
    "spent_brl": 250.0, "budget_brl": 1000.0, "used_pct": 0.25,
    "status": "ok", "soft_pct": 0.8, "hard_pct": 1.0,
}


@pytest.fixture
def env():
    _ctx, fakes = make_ctx()
    fakes.db.set_table_data("noctus_users", [dict(u) for u in USERS])
    state = SimpleNamespace(user=OWNER_USER, metadata={}, calls=[])

    async def session_user():
        return SimpleNamespace(id=state.user, user_metadata=state.metadata)

    async def calcular(org_id: str) -> dict:
        state.calls.append(org_id)
        return dict(STATUS)

    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = session_user
    app.dependency_overrides[get_spend_calculator] = lambda: calcular
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


def _get(env, org_id: str):
    return env.client.get(f"/api/admin/llm-spend/{org_id}")


class TestAllowed:
    def test_org_owner_reads_own_org(self, env):
        env.user = OWNER_USER
        resp = _get(env, ORG_ID)
        assert resp.status_code == 200
        assert resp.json()["data"]["org_id"] == ORG_ID
        assert resp.json()["data"]["status"] == "ok"
        assert env.calls == [ORG_ID]

    def test_org_admin_reads_own_org(self, env):
        env.user = ORG_ADMIN_USER
        assert _get(env, ORG_ID).status_code == 200

    def test_platform_admin_reads_any_org(self, env):
        env.user = ADMIN_USER  # home org is OTHER_ORG_ID
        assert _get(env, ORG_ID).status_code == 200
        assert _get(env, OTHER_ORG_ID).status_code == 200

    def test_platform_admin_without_org_reads_any_org(self, env):
        env.user = NO_ORG_PLATFORM_ADMIN
        assert _get(env, ORG_ID).status_code == 200

    def test_uppercase_path_is_normalized_before_compute(self, env):
        env.user = OWNER_USER
        resp = _get(env, ORG_ID.upper())
        assert resp.status_code == 200
        # The id that was AUTHORIZED is the one computed and echoed — never the raw path.
        assert env.calls == [ORG_ID]
        assert resp.json()["data"]["org_id"] == ORG_ID


class TestRefused:
    def test_org_owner_cannot_read_another_org(self, env):
        env.user = OWNER_USER
        resp = _get(env, OTHER_ORG_ID)
        assert resp.status_code == 403
        assert "org_admin_required" in resp.text
        assert env.calls == []

    @pytest.mark.parametrize("user", [MANAGER_USER, MEMBER_USER, CUSTOMER_USER])
    def test_non_admin_org_roles_refused_on_own_org(self, env, user):
        env.user = user
        assert _get(env, ORG_ID).status_code == 403
        assert env.calls == []

    def test_forged_metadata_does_not_elevate(self, env):
        # user_metadata claims owner + platform admin; the trusted row says member.
        env.user = MEMBER_USER
        env.metadata = {"org_role": "owner", "noctus_role": "admin", "org_id": ORG_ID}
        assert _get(env, ORG_ID).status_code == 403

    def test_owner_without_org_refused(self, env):
        env.user = NO_ORG_OWNER
        assert _get(env, ORG_ID).status_code == 403

    @pytest.mark.parametrize("bad", ["org-1", "not-a-uuid", "1111"])
    def test_malformed_org_id_is_403_not_500(self, env, bad):
        env.user = ADMIN_USER
        assert _get(env, bad).status_code == 403
        assert env.calls == []

    def test_user_without_trusted_row_refused(self, env):
        env.user = "12345678-1234-1234-1234-123456789012"
        assert _get(env, ORG_ID).status_code == 403


class TestUnauthenticated:
    def test_no_bearer_is_strict_401(self):
        app.dependency_overrides.clear()
        assert TestClient(app).get(f"/api/admin/llm-spend/{ORG_ID}").status_code == 401


class TestAssurance:
    """Org owners/admins are admin-tier for the admin-MFA policy (its own owner
    decision), so this read is assurance-gated like every admin gate — the old
    `get_current_admin` was too. `off` (the fleet default) is a no-op."""

    @pytest.fixture
    def enforce(self):
        previous = getattr(app.state, "mfa_gate", None)
        app.state.mfa_gate = MfaGateConfig(
            product="core", policy=FakeMfaPolicy({"fleet": "enforce"}), client=None, cache_ttl=0,
        )
        yield
        app.state.mfa_gate = previous

    def test_enforce_refuses_aal1_owner(self, env, enforce):
        env.user = OWNER_USER
        resp = _get(env, ORG_ID)
        assert resp.status_code == 403
        assert "mfa_required" in resp.text
        assert env.calls == []

    def test_off_policy_lets_owner_through(self, env):
        env.user = OWNER_USER
        assert _get(env, ORG_ID).status_code == 200
