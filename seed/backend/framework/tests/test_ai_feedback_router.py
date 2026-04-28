"""Tests for the seed `ai_feedback` standard router (X3 from ai-expansion Phase 17)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def _build_app(deps):
    """Mount the ai_feedback router on a fresh FastAPI app for TestClient use."""
    from noctusai_seed.ai_feedback_router import create_ai_feedback_router

    app = FastAPI()
    router: APIRouter = create_ai_feedback_router(deps)
    app.include_router(router)
    return app


def _client_with_deps(deps):
    return TestClient(_build_app(deps))


def _wire_user_client(deps, *, upsert_data=None, select_data=None):
    """Hook deps.get_user_client(token) → mock supabase client whose
    chained `.schema().table().upsert/select.execute()` returns canned data."""
    sb = MagicMock()
    chain = MagicMock()
    sb.schema = MagicMock(return_value=chain)
    chain.table = MagicMock(return_value=chain)
    chain.upsert = MagicMock(return_value=chain)
    chain.select = MagicMock(return_value=chain)
    chain.eq = MagicMock(return_value=chain)
    chain.limit = MagicMock(return_value=chain)
    if upsert_data is not None:
        chain.execute = MagicMock(return_value=MagicMock(data=upsert_data))
    elif select_data is not None:
        chain.execute = MagicMock(return_value=MagicMock(data=select_data))
    deps.get_user_client = MagicMock(return_value=sb)
    return sb, chain


class TestUpsertEndpoint:
    def test_happy_path_returns_persisted_row(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, upsert_data=[{
            "id": "fb-1", "user_id": "user-1", "output_ref": "ai_output:abc",
            "rating": 1, "notes": None, "prompt_version": "v1",
        }])
        client = _client_with_deps(fake_deps)
        resp = client.post(
            "/api/ai/feedback",
            headers={"Authorization": "Bearer t"},
            json={"output_ref": "ai_output:abc", "rating": 1},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["rating"] == 1
        assert body["output_ref"] == "ai_output:abc"

    def test_invalid_rating_rejected(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        client = _client_with_deps(fake_deps)
        resp = client.post(
            "/api/ai/feedback",
            headers={"Authorization": "Bearer t"},
            json={"output_ref": "ai_output:abc", "rating": 5},
        )
        assert resp.status_code == 422

    def test_thumbs_down_accepted(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, upsert_data=[{
            "id": "fb-1", "rating": -1, "output_ref": "ai_output:abc",
        }])
        client = _client_with_deps(fake_deps)
        resp = client.post(
            "/api/ai/feedback",
            headers={"Authorization": "Bearer t"},
            json={"output_ref": "ai_output:abc", "rating": -1, "notes": "wrong"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["rating"] == -1

    def test_db_error_returns_500(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        sb, chain = _wire_user_client(fake_deps, upsert_data=[])
        chain.execute = MagicMock(side_effect=RuntimeError("boom"))
        client = _client_with_deps(fake_deps)
        resp = client.post(
            "/api/ai/feedback",
            headers={"Authorization": "Bearer t"},
            json={"output_ref": "ai_output:abc", "rating": 1},
        )
        assert resp.status_code == 500


class TestGetEndpoint:
    def test_returns_existing_row(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, select_data=[{
            "id": "fb-1", "rating": 1, "output_ref": "ai_output:abc",
        }])
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/ai/feedback?output_ref=ai_output:abc",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["rating"] == 1

    def test_returns_null_when_missing(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        _wire_user_client(fake_deps, select_data=[])
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/ai/feedback?output_ref=ai_output:nope",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    def test_db_error_returns_null_data(self, fake_deps):
        user = MagicMock()
        user.id = "user-1"
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        sb, chain = _wire_user_client(fake_deps, select_data=[])
        chain.execute = MagicMock(side_effect=RuntimeError("boom"))
        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/ai/feedback?output_ref=ai_output:abc",
            headers={"Authorization": "Bearer t"},
        )
        # GET swallows errors and returns null so the indicator UI stays silent.
        assert resp.status_code == 200
        assert resp.json()["data"] is None
