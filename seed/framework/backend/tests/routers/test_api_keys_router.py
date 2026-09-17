"""Tests for `noctusai_seed.api_keys_router.create_api_keys_router`.

The lifted (`community uses social-wiring's mechanisms`, Slice A)
org-scoped managed-API-keys router — the seed generalization of
`social-wiring`'s `/api/settings/api-keys*` surface. Drives the router
with `social-wiring`-shaped fixtures (its actual `openai_api_key` /
`llm_vision_provider`-style specs) to assert the frozen SW contract:
paths, response shapes, status codes.

Auth-boundary tests assert strict `== 401` (never `in (401, 404, 422)`)
per `KB § PATTERNS/compliance/auth-boundary-false-green.md`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from noctusai_lib.security.api_keys import (
    ApiKeyOption,
    ApiKeySpec,
    EncryptionNotConfigured,
    build_api_key_store,
)
from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_seed.api_keys_router import create_api_keys_router


SPECS = (
    ApiKeySpec(
        name="openai_api_key",
        label="OpenAI API Key",
        description="desc",
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-...",
    ),
    ApiKeySpec(
        name="infosimples_email_envio",
        label="E-mail de Envio",
        description="desc",
        is_secret=False,
        testable=False,
        input_type="email",
    ),
    ApiKeySpec(
        name="llm_vision_provider",
        label="Provedor de leitura",
        description="desc",
        is_secret=False,
        input_type="select",
        options=(
            ApiKeyOption(value="openai", label="OpenAI"),
            ApiKeyOption(value="anthropic", label="Anthropic"),
        ),
        default="openai",
    ),
)


def _fresh_store():
    return build_api_key_store(None, encryption_key=generate_key().decode())


def _org_dep(*, raise_401=False):
    def _dep():
        if raise_401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        user = MagicMock()
        user.id = "user-1"
        return (user, "tok", "org-1")

    return _dep


def _app(*, store=None, testers=None, require_admin=None, raise_401=False):
    store = store or _fresh_store()
    kwargs = {}
    if require_admin is not None:
        kwargs["require_admin"] = require_admin
    router = create_api_keys_router(
        MagicMock(),
        MagicMock(),
        specs=SPECS,
        store_factory=lambda: store,
        get_current_user_org=_org_dep(raise_401=raise_401),
        testers=testers,
        # DI seam — never the ambient `resolve_credential` chain; see
        # test_social_wiring_parity.py's `_app()` for why.
        resolver=lambda key, org_id: None,
        **kwargs,
    )
    app = FastAPI()
    app.include_router(router)
    return app, store


class TestListApiKeys:
    def test_path_and_shape(self):
        app, _store = _app()
        resp = TestClient(app).get("/api/settings/api-keys")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        item = next(i for i in body["items"] if i["key"] == "openai_api_key")
        assert item["is_secret"] is True
        assert item["testable"] is True
        assert item["configured"] is False
        assert item["hint"] is None
        assert item["source"] is None

    def test_choice_spec_exposes_options_and_default(self):
        app, _store = _app()
        body = TestClient(app).get("/api/settings/api-keys").json()
        item = next(i for i in body["items"] if i["key"] == "llm_vision_provider")
        assert item["options"] == [
            {"value": "openai", "label": "OpenAI", "description": ""},
            {"value": "anthropic", "label": "Anthropic", "description": ""},
        ]
        assert item["default"] == "openai"

    def test_auth_boundary_strict_401(self):
        app, _store = _app(raise_401=True)
        resp = TestClient(app).get("/api/settings/api-keys")
        assert resp.status_code == 401


class TestUpdateApiKey:
    def test_put_persists_and_masks_hint(self):
        app, store = _app()
        resp = TestClient(app).put(
            "/api/settings/api-keys/openai_api_key", json={"value": "sk-abcdef1234"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["hint"] == "...1234"
        assert body["source"] == "local"
        # secret value never rides the response
        assert "sk-abcdef1234" not in resp.text

    def test_put_blank_value_422(self):
        app, _store = _app()
        resp = TestClient(app).put(
            "/api/settings/api-keys/openai_api_key", json={"value": "   "}
        )
        assert resp.status_code == 422

    def test_put_unknown_key_404(self):
        app, _store = _app()
        resp = TestClient(app).put(
            "/api/settings/api-keys/does_not_exist", json={"value": "x"}
        )
        assert resp.status_code == 404

    def test_put_invalid_choice_422(self):
        app, _store = _app()
        resp = TestClient(app).put(
            "/api/settings/api-keys/llm_vision_provider", json={"value": "not-a-real-vendor"}
        )
        assert resp.status_code == 422

    def test_put_valid_choice_200(self):
        app, _store = _app()
        resp = TestClient(app).put(
            "/api/settings/api-keys/llm_vision_provider", json={"value": "anthropic"}
        )
        assert resp.status_code == 200
        assert resp.json()["hint"] == "anthropic"  # non-secret shown verbatim

    def test_admin_gate_enforced_when_configured(self):
        def _deny(user, context):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=context)

        app, _store = _app(require_admin=_deny)
        resp = TestClient(app).put(
            "/api/settings/api-keys/openai_api_key", json={"value": "sk-x"}
        )
        assert resp.status_code == 403

    def test_auth_boundary_strict_401(self):
        app, _store = _app(raise_401=True)
        resp = TestClient(app).put(
            "/api/settings/api-keys/openai_api_key", json={"value": "sk-x"}
        )
        assert resp.status_code == 401

    def test_encryption_not_configured_maps_to_503(self):
        def _raising_store():
            raise EncryptionNotConfigured("no key")

        router = create_api_keys_router(
            MagicMock(), MagicMock(), specs=SPECS, store_factory=_raising_store,
            get_current_user_org=_org_dep(),
        )
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).put(
            "/api/settings/api-keys/openai_api_key", json={"value": "sk-x"}
        )
        assert resp.status_code == 503


class TestRemoveApiKey:
    def test_delete_returns_rerresolved_status(self):
        app, store = _app()
        TestClient(app).put("/api/settings/api-keys/openai_api_key", json={"value": "sk-x"})
        resp = TestClient(app).delete("/api/settings/api-keys/openai_api_key")
        assert resp.status_code == 200
        assert resp.json()["configured"] is False

    def test_delete_unknown_key_404(self):
        app, _store = _app()
        resp = TestClient(app).delete("/api/settings/api-keys/nope")
        assert resp.status_code == 404

    def test_auth_boundary_strict_401(self):
        app, _store = _app(raise_401=True)
        resp = TestClient(app).delete("/api/settings/api-keys/openai_api_key")
        assert resp.status_code == 401


class TestTestApiKey:
    async def _pass_tester(self, value: str):
        from noctusai_seed.api_keys_router import ApiKeyTestResultOut

        return ApiKeyTestResultOut(key="openai_api_key", success=True, message="ok")

    def test_no_tester_registered_400(self):
        app, _store = _app()
        resp = TestClient(app).post("/api/settings/api-keys/openai_api_key/test")
        assert resp.status_code == 400

    def test_not_configured_422(self):
        app, _store = _app(testers={"openai_api_key": self._pass_tester})
        resp = TestClient(app).post("/api/settings/api-keys/openai_api_key/test")
        assert resp.status_code == 422

    def test_configured_dispatches_to_tester(self):
        app, _store = _app(testers={"openai_api_key": self._pass_tester})
        TestClient(app).put("/api/settings/api-keys/openai_api_key", json={"value": "sk-x"})
        resp = TestClient(app).post("/api/settings/api-keys/openai_api_key/test")
        assert resp.status_code == 200
        assert resp.json() == {"key": "openai_api_key", "success": True, "message": "ok"}

    def test_auth_boundary_strict_401(self):
        app, _store = _app(raise_401=True, testers={"openai_api_key": self._pass_tester})
        resp = TestClient(app).post("/api/settings/api-keys/openai_api_key/test")
        assert resp.status_code == 401
