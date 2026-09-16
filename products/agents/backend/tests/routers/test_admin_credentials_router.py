"""`/api/admin/credentials` + `/api/admin/agent-settings` — platform-admin
only; no response and no log line ever carries a secret."""
from __future__ import annotations

import logging
from uuid import UUID

import pytest

from app.dependencies import (
    get_auth_context,
    get_credential_service_dep,
    get_runtime_settings_service_dep,
)
from app.services.runtime_settings import RuntimeSettingsService
from app.stores.runtime_settings import FakeRuntimeSettingsStore
from noctusai_lib.api.auth.session import AuthContext
from tests.credentials.conftest import (
    ANTHROPIC,
    JULIA_ID,
    OLD_ACADEMIA,
    assert_no_secret,
    build_kit,
    seed_academia_token,
)
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

#: (method, path, json) for EVERY route the two routers mount.
ROUTES = [
    ("get", "/api/admin/credentials", None),
    ("put", "/api/admin/credentials/anthropic_api_key", {"value": "sk-ant-api03-" + "N" * 40}),
    ("post", "/api/admin/credentials/academia_api_token/import-env", None),
    ("post", "/api/admin/credentials/anthropic_api_key/health", None),
    ("post", "/api/admin/credentials/academia_api_token/renew", None),
    ("post", "/api/admin/credentials/approval_assertion_secrets/rotate", None),
    ("post", "/api/admin/credentials/approval_assertion_secrets/prune", None),
    ("get", "/api/admin/agent-settings", None),
    ("put", "/api/admin/agent-settings", {"max_turns": 30}),
]


def _call(client, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    return getattr(client, method)(path, **kwargs)


def _seed_user(client, *, role: str, org_role: str = "owner") -> None:
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": role, "org_role": org_role}],
    )


@pytest.fixture
def admin_client(agents_client, caplog):
    from app.main import app

    caplog.set_level(logging.DEBUG)
    kit = build_kit(
        academia_api_token=OLD_ACADEMIA,
        anthropic_api_key=ANTHROPIC,
        approval_assertion_secrets="ring-secret-one,ring-secret-two",
        julia_agent_id=str(JULIA_ID),
    )
    runtime = RuntimeSettingsService(
        FakeRuntimeSettingsStore(),
        type("S", (), {"approval_timeout_seconds": 300, "julia_max_turns": None,
                       "messages_rate_limit": "20/minute", "turn_timeout_seconds": 600,
                       "julia_cli_slots": 3})(),
        ttl_seconds=0,
    )
    app.dependency_overrides[get_credential_service_dep] = lambda: kit.service
    app.dependency_overrides[get_runtime_settings_service_dep] = lambda: runtime
    agents_client.kit = kit
    agents_client.runtime_settings = runtime
    try:
        yield agents_client
    finally:
        app.dependency_overrides.pop(get_credential_service_dep, None)
        app.dependency_overrides.pop(get_runtime_settings_service_dep, None)
        assert_no_secret(caplog.text)


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_credential_is_401(self, admin_client, method, path, body):
        assert _call(admin_client.raw(), method, path, body).status_code == 401

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_org_owner_is_not_a_platform_admin_403(self, admin_client, method, path, body):
        _seed_user(admin_client, role="user", org_role="owner")
        resp = _call(admin_client, method, path, body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "platform_admin_required"

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_product_token_caller_403(self, admin_client, method, path, body):
        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["*"],
            raw_token="x", api_token_id=UUID(int=1),
        )
        try:
            resp = _call(admin_client, method, path, body)
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert resp.status_code == 403


class TestCredentials:
    def test_list_never_carries_a_secret(self, admin_client):
        _seed_user(admin_client, role="admin")
        seed_academia_token(admin_client.kit, days_left=12)
        resp = admin_client.get("/api/admin/credentials")
        assert resp.status_code == 200, resp.text
        assert_no_secret(resp.text)
        body = resp.json()
        assert body["total"] == 5
        academia = next(i for i in body["items"] if i["name"] == "academia_api_token")
        assert academia["prefix"] == OLD_ACADEMIA[:11]
        assert academia["days_left"] == 12
        assert academia["severity"] == "warning"
        assert body["alerts"] >= 1

    def test_set_is_write_only(self, admin_client):
        _seed_user(admin_client, role="admin")
        new = "sk-ant-api03-" + "W" * 50
        resp = admin_client.put("/api/admin/credentials/anthropic_api_key", json={"value": new})
        assert resp.status_code == 200, resp.text
        assert new not in resp.text
        assert resp.json()["source"] == "db"
        assert admin_client.kit.store.get("anthropic_api_key") == new

    def test_set_rejects_unknown_fields_and_bad_values(self, admin_client):
        _seed_user(admin_client, role="admin")
        assert admin_client.put(
            "/api/admin/credentials/anthropic_api_key", json={"value": "sk-x", "extra": 1}
        ).status_code == 422
        bad = admin_client.put("/api/admin/credentials/academia_api_token", json={"value": "nope"})
        assert bad.status_code == 422
        assert bad.json()["code"] == "invalid_value"

    def test_unknown_credential_404(self, admin_client):
        _seed_user(admin_client, role="admin")
        assert admin_client.post("/api/admin/credentials/nope/health").status_code == 404

    def test_health(self, admin_client):
        _seed_user(admin_client, role="admin")
        resp = admin_client.post("/api/admin/credentials/anthropic_api_key/health")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"
        assert_no_secret(resp.text)

    def test_renew_round_trip(self, admin_client):
        _seed_user(admin_client, role="admin")
        seed_academia_token(admin_client.kit, days_left=3)
        resp = admin_client.post("/api/admin/credentials/academia_api_token/renew")
        assert resp.status_code == 200, resp.text
        new_secret = admin_client.kit.store.get("academia_api_token")
        assert new_secret and new_secret not in resp.text
        assert_no_secret(resp.text)
        assert resp.json()["credential"]["days_left"] >= 89

    def test_renew_not_supported_409(self, admin_client):
        _seed_user(admin_client, role="admin")
        resp = admin_client.post("/api/admin/credentials/anthropic_api_key/renew")
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_supported"

    def test_import_then_rotate_ring(self, admin_client):
        _seed_user(admin_client, role="admin")
        assert admin_client.post(
            "/api/admin/credentials/approval_assertion_secrets/rotate"
        ).json()["code"] == "ring_not_in_db"
        assert admin_client.post(
            "/api/admin/credentials/approval_assertion_secrets/import-env"
        ).status_code == 200
        resp = admin_client.post("/api/admin/credentials/approval_assertion_secrets/rotate")
        assert resp.status_code == 200, resp.text
        assert [k["state"] for k in resp.json()["ring"]] == ["staged", "retiring", "retiring"]
        assert_no_secret(resp.text)
        pruned = admin_client.post("/api/admin/credentials/approval_assertion_secrets/prune")
        assert pruned.status_code == 200


class TestAgentSettings:
    def test_get_shows_env_defaults_and_read_only_slots(self, admin_client):
        _seed_user(admin_client, role="admin")
        resp = admin_client.get("/api/admin/agent-settings")
        assert resp.status_code == 200, resp.text
        items = {i["key"]: i for i in resp.json()["items"]}
        assert items["approval_timeout_seconds"]["value"] == 300
        assert items["max_turns"]["value"] == 40  # spec.yaml
        assert items["julia_cli_slots"]["editable"] is False

    def test_update_then_reset(self, admin_client):
        _seed_user(admin_client, role="admin")
        resp = admin_client.put(
            "/api/admin/agent-settings",
            json={"approval_timeout_seconds": 120, "messages_rate_limit": "5/minute"},
        )
        assert resp.status_code == 200, resp.text
        items = {i["key"]: i for i in resp.json()["items"]}
        assert (items["approval_timeout_seconds"]["value"], items["approval_timeout_seconds"]["source"]) == (120, "db")
        assert admin_client.runtime_settings.messages_rate_limit() == "5/minute"

        reset = admin_client.put("/api/admin/agent-settings", json={"approval_timeout_seconds": None})
        items = {i["key"]: i for i in reset.json()["items"]}
        assert (items["approval_timeout_seconds"]["value"], items["approval_timeout_seconds"]["source"]) == (300, "env")

    @pytest.mark.parametrize(
        "body",
        [
            {"approval_timeout_seconds": 5},
            {"approval_timeout_seconds": 590},  # would outlive the turn deadline
            {"max_turns": 0},
            {"messages_rate_limit": "lots"},
            {"julia_cli_slots": 5},  # read-only → unknown field
        ],
    )
    def test_invalid_updates_422(self, admin_client, body):
        _seed_user(admin_client, role="admin")
        assert admin_client.put("/api/admin/agent-settings", json=body).status_code == 422
