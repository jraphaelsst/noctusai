"""Tests for the seed `llm` standard router runtime path.

The original sin pinned here: `obter_preferences`, `salvar_preferences`,
and `obter_usage` previously called `deps._db.get_user_client()` — a
method `DatabaseModule` does NOT expose. The router imported and mounted
fine (so `test_build_standard_routers` was green), but the first GET
crashed at runtime with AttributeError. The fix routes the call through
`deps.get_user_client(token)` (the canonical seam used by
`ai_router` + `ai_feedback_router`).

Project ref: `projects/seed-llm-router-obter-preferences-hotfix/PROJECT.md`.

Status assertions are explicit (`assert resp.status_code == ...`) per
`KB § PATTERNS/testing.md § Status-code-assertion rule`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def _build_app(deps):
    """Mount the llm router on a fresh FastAPI app for TestClient use."""
    from noctusai_seed.llm_router import create_llm_router

    app = FastAPI()
    router: APIRouter = create_llm_router(deps)
    app.include_router(router)
    return app


def _client_with_deps(deps):
    return TestClient(_build_app(deps))


def _wire_user_client(deps, *, single_data=None, upsert_data=None, select_data=None):
    """Hook deps.get_user_client(token) → mock supabase client whose
    chained `.table().select/upsert/eq/...execute()` returns canned data.

    Mirrors the ai_feedback_router test's helper but tracks the chain
    methods llm_router uses (no schema() wrap; the schema is bound at
    DatabaseModule construction)."""
    sb = MagicMock()
    chain = MagicMock()
    sb.table = MagicMock(return_value=chain)
    chain.select = MagicMock(return_value=chain)
    chain.upsert = MagicMock(return_value=chain)
    chain.eq = MagicMock(return_value=chain)
    chain.gte = MagicMock(return_value=chain)
    chain.lte = MagicMock(return_value=chain)
    chain.order = MagicMock(return_value=chain)
    chain.limit = MagicMock(return_value=chain)
    chain.maybe_single = MagicMock(return_value=chain)
    # Default result shape used by `obter_preferences` (maybe_single).
    result = MagicMock()
    if single_data is not None:
        result.data = single_data
    elif upsert_data is not None:
        result.data = upsert_data
    elif select_data is not None:
        result.data = select_data
    else:
        result.data = None
    chain.execute = MagicMock(return_value=result)
    deps.get_user_client = MagicMock(return_value=sb)
    return sb, chain


class TestObterPreferencesDoesNotCrash:
    """The bug class: `obter_preferences` MUST NOT call a method
    `DatabaseModule` doesn't expose. Pre-fix this crashed with
    AttributeError on first request."""

    def test_returns_200_with_existing_prefs(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, single_data={
            "provider": "openai",
            "chat_model": "gpt-4",
            "embedding_model": "text-embedding-3-small",
        })
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "openai"
        assert body["chat_model"] == "gpt-4"

    def test_returns_200_with_null_defaults_when_unset(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, single_data=None)
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
        )
        # The endpoint must not crash — falls back to null-shape per spec.
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"provider": None, "chat_model": None, "embedding_model": None}

    def test_wires_through_deps_get_user_client_not_db_get_user_client(self, fake_deps):
        """Regression pin: the call site MUST be `deps.get_user_client(token)`,
        NOT `deps._db.get_user_client(...)`. We assert by verifying
        `deps.get_user_client` was called with the token; `deps._db.get_user_client`
        must NOT be a configured method on DatabaseModule (the bug class)."""
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok-abc"))
        _wire_user_client(fake_deps, single_data=None)
        # Deliberately remove `_db.get_user_client` from the mock to mirror
        # the production DatabaseModule shape (it does NOT have that method).
        # If the call site regresses, the request will raise AttributeError.
        del fake_deps._db.get_user_client
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        fake_deps.get_user_client.assert_called_with("tok-abc")


class TestSalvarPreferencesDoesNotCrash:
    """Same bug class on the PUT path."""

    def test_owner_can_save(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        fake_deps.get_user_role = MagicMock(return_value="owner")
        _wire_user_client(fake_deps, upsert_data=[{"org_id": "org-123", "provider": "openai"}])
        del fake_deps._db.get_user_client  # mirror real DatabaseModule shape
        client = _client_with_deps(fake_deps)
        resp = client.put(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
            json={"provider": "openai", "chat_model": "gpt-4"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_non_admin_rejected_403(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        fake_deps.get_user_role = MagicMock(return_value="user")  # not in allowed roles
        # No need to wire user_client — 403 fires before DB touch.
        client = _client_with_deps(fake_deps)
        resp = client.put(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
            json={"provider": "openai"},
        )
        assert resp.status_code == 403

    def test_unknown_provider_rejected_400(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        fake_deps.get_user_role = MagicMock(return_value="owner")
        client = _client_with_deps(fake_deps)
        resp = client.put(
            "/api/llm/preferences",
            headers={"Authorization": "Bearer t"},
            json={"provider": "made-up-provider-xyz"},
        )
        assert resp.status_code == 400


class TestObterUsageDoesNotCrash:
    """Same bug class also lived in `obter_usage` (GET /usage). Pin it."""

    def test_returns_200_with_empty_rows(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, select_data=[])
        del fake_deps._db.get_user_client  # mirror real DatabaseModule shape
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/llm/usage",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["aggregate"] == []
        assert "window" in body


class TestModelsStillWorks:
    """Guard that the `_require_org` 2→3-tuple return change didn't break
    the other endpoints (the language-level tuple-unpack hazard).

    `listar_providers` is NOT guarded here because its body calls
    `resolve_credential(...)` which reaches into a real Supabase
    client — guarding it would require monkey-patching our own
    `noctusai_lib.config.credentials` seam (forbidden by CLAUDE.md §1
    `no-monkey-patching-our-code` rule). The behavior pin for
    `/api/llm/providers` lives in `test_build_standard_routers.py`
    (registration). The tuple-unpack hazard on line 82 of llm_router
    is caught by Python at import-call time — every other endpoint
    test below exercising `_require_org` would crash if it regressed.
    """

    def test_models_returns_200(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/llm/models?provider=openai",
            headers={"Authorization": "Bearer t"},
        )
        # 200 if openai is registered (it is in the seed catalog); the
        # endpoint must at minimum not crash on the _require_org change.
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
