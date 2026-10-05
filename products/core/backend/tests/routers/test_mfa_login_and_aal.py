"""platform-admin-mfa M5 — core login challenge discovery + aal propagation.

DI only: the login reads its `MfaClient` from `app.state.mfa_gate` (the seed's
seam; tests assign an `MfaGateConfig` carrying a `FakeMfaClient`), and the
trusted-auth tests override `get_session_user` / `get_trusted_db` like the
billing tests. Nothing of ours is patched.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from noctusai_lib.api.auth.mfa.client import FakeMfaClient, MfaError, MfaFactor
from noctusai_lib.api.auth.mfa.gate import MfaGateConfig
from noctusai_lib.api.auth.mfa.policy import FakeMfaPolicy
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, OWNER_USER, make_ctx, seed_users

ACCESS = "aal1-access-token"


def _jwt(sub: str, aal: str) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'aal': aal})}.sig"


@pytest.fixture
def gate():
    """Install an MfaGateConfig for the test (the documented DI seam) and restore it."""
    previous = getattr(app.state, "mfa_gate", None)

    def install(mode: str = "off", client=None) -> MfaGateConfig:
        cfg = MfaGateConfig(
            product="core", policy=FakeMfaPolicy({"fleet": mode}), client=client, cache_ttl=0,
        )
        app.state.mfa_gate = cfg
        return cfg

    yield install
    app.state.mfa_gate = previous


def _stub_sign_in(client, token: str = ACCESS):
    session = MagicMock(access_token=token, refresh_token="refresh-1")
    user = MagicMock(id="user-123", email="u@example.com")
    client.mock_supabase.auth.sign_in_with_password = MagicMock(
        return_value=MagicMock(session=session, user=user)
    )


def _login(client):
    return client.post("/api/auth/login", json={"email": "u@example.com", "password": "password123"})


class _Raising(FakeMfaClient):
    async def list_factors(self, access_token):  # noqa: D401
        raise MfaError("upstream_down")


class TestLoginChallenge:
    def test_without_factors_login_is_unchanged(self, client, gate):
        gate("off", FakeMfaClient())
        _stub_sign_in(client)
        body = _login(client).json()
        assert body["access_token"] == ACCESS
        assert body["refresh_token"] == "refresh-1"
        assert body["mfa_required"] is False
        assert body["mfa_factors"] == []

    def test_no_mfa_client_configured_is_unchanged(self, client, gate):
        gate("off", None)
        _stub_sign_in(client)
        assert _login(client).json()["mfa_required"] is False

    @pytest.mark.parametrize("mode", ["off", "warn", "enforce"])
    def test_verified_factor_requires_challenge_under_every_policy(self, client, gate, mode):
        fake = FakeMfaClient()
        fake.factors[ACCESS] = [
            MfaFactor("f-ok", "totp", "verified", "Celular"),
            MfaFactor("f-pending", "totp", "unverified", "Meio enrolado"),
        ]
        gate(mode, fake)
        _stub_sign_in(client)
        resp = _login(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["mfa_required"] is True
        assert body["mfa_factors"] == [{"id": "f-ok", "friendly_name": "Celular"}]
        assert body["access_token"] == ACCESS  # aal1, needed as Bearer for /api/auth/mfa/verify

    def test_only_unverified_factors_do_not_challenge(self, client, gate):
        fake = FakeMfaClient()
        fake.factors[ACCESS] = [MfaFactor("f-pending", "totp", "unverified", "x")]
        gate("off", fake)
        _stub_sign_in(client)
        assert _login(client).json()["mfa_required"] is False

    def test_factor_lookup_failure_is_fail_open_but_logged(self, client, gate, caplog):
        gate("off", _Raising())
        _stub_sign_in(client)
        with caplog.at_level("WARNING"):
            resp = _login(client)
        assert resp.status_code == 200
        assert resp.json()["mfa_required"] is False
        assert "factor lookup failed" in caplog.text
        assert "u@example.com" not in caplog.text and ACCESS not in caplog.text

    def test_bad_credentials_still_401(self, client, gate):
        gate("off", FakeMfaClient())
        client.mock_supabase.auth.sign_in_with_password = MagicMock(side_effect=Exception("nope"))
        assert _login(client).status_code == 401

    def test_challenge_completes_through_the_m3_router_not_a_parallel_endpoint(self, client, gate):
        # The login response only points at /api/auth/mfa/verify; no second endpoint exists.
        paths = {r.path for r in app.routes}
        assert "/api/auth/mfa/verify" in paths
        assert not [p for p in paths if p.startswith("/api/auth/login/") and "mfa" in p]


@pytest.fixture
def env():
    ctx, fakes = make_ctx()
    seed_users(fakes.db)
    state = SimpleNamespace(user=ADMIN_USER)

    async def session_user():
        return SimpleNamespace(id=state.user)

    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


ADMIN_URL = "/api/admin/llm-usage"


class TestTrustedAuthAal:
    def test_no_token_is_401(self):
        app.dependency_overrides.clear()
        assert TestClient(app).get(ADMIN_URL).status_code == 401

    def test_enforce_aal1_platform_admin_is_403_mfa_required(self, env, gate):
        gate("enforce", FakeMfaClient())
        resp = env.client.get(ADMIN_URL, headers={"Authorization": f"Bearer {_jwt(ADMIN_USER, 'aal1')}"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"

    def test_enforce_unreadable_aal_fails_closed(self, env, gate):
        gate("enforce", FakeMfaClient())
        resp = env.client.get(ADMIN_URL, headers={"Authorization": "Bearer not-a-jwt"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"

    def test_enforce_aal2_platform_admin_passes_the_gate(self, env, gate):
        gate("enforce", FakeMfaClient())
        resp = env.client.get(ADMIN_URL, headers={"Authorization": f"Bearer {_jwt(ADMIN_USER, 'aal2')}"})
        assert resp.json().get("code") != "mfa_required"
        assert resp.status_code != 403

    def test_aal2_claim_of_another_user_does_not_bind(self, env, gate):
        gate("enforce", FakeMfaClient())
        resp = env.client.get(ADMIN_URL, headers={"Authorization": f"Bearer {_jwt('someone-else', 'aal2')}"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"

    def test_off_never_challenges(self, env, gate):
        gate("off", FakeMfaClient())
        resp = env.client.get(ADMIN_URL, headers={"Authorization": f"Bearer {_jwt(ADMIN_USER, 'aal1')}"})
        assert resp.status_code != 403

    def test_enforce_member_is_not_challenged_just_refused_by_role(self, env, gate):
        gate("enforce", FakeMfaClient())
        env.user = MEMBER_USER
        resp = env.client.get(ADMIN_URL, headers={"Authorization": f"Bearer {_jwt(MEMBER_USER, 'aal1')}"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "platform_admin_required"

    def test_get_trusted_auth_carries_aal(self, env):
        import asyncio

        from app.services.trusted_auth import get_session_aal, get_trusted_auth

        user = SimpleNamespace(id=ADMIN_USER)
        aal = asyncio.run(get_session_aal(f"Bearer {_jwt(ADMIN_USER, 'aal2')}", user))
        assert aal == "aal2"
        assert asyncio.run(get_session_aal(None, user)) is None
        db = env.client.app.dependency_overrides[get_trusted_db]()
        ctx = asyncio.run(get_trusted_auth(user, db, aal))
        assert ctx.aal == "aal2"
