"""
/api/content/plans/* — strict-401 auth boundary, validation, and the
authed flows (tasks from items, delete semantics, AI honesty). The AI path
runs through the real seed LLM plumbing with a test-owned scripted provider.
"""
import json
from collections import deque

import pytest

from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm, get_llm_config
from noctusai_lib.integrations.llm.config import LLMConfig
from noctusai_lib.integrations.llm.registry import register

from app.dependencies import coerce_org_uuid
from noctusai_lib.testing import handler_status

ORG_UUID = str(coerce_org_uuid("test-org-123"))
PLAN_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "33333333-3333-3333-3333-333333333333"
TS = "2026-01-01T00:00:00+00:00"


def _plan(**over):
    return {"id": PLAN_ID, "org_id": ORG_UUID, "client_id": None,
            "campaign_id": None, "title": "Novembro", "month": "2026-11", "strategy_context": {},
            "status": "active", "creation_mode": "manual", "created_at": TS, "updated_at": TS, **over}


def _item(**over):
    return {"id": ITEM_ID, "org_id": ORG_UUID, "plan_id": PLAN_ID,
            "order_position": 0, "title": "Reels X", "description": "d", "format": "reels",
            "platform": "instagram", "post_date": "2026-11-10", "due_date": None, "caption": None,
            "reference_notes": None, "status": "planned", "task_id": None, "post_id": None,
            "created_at": TS, "updated_at": TS, **over}


AI_BODY = {"items_count": 2, "period_days": 7, "start_date": "2026-11-02",
           "weekdays": [1, 3, 5], "platforms": ["instagram"]}

ENDPOINTS = [
    ("get", "/api/content/plans"),
    ("post", "/api/content/plans"),
    ("get", f"/api/content/plans/{PLAN_ID}"),
    ("patch", f"/api/content/plans/{PLAN_ID}"),
    ("delete", f"/api/content/plans/{PLAN_ID}"),
    ("post", f"/api/content/plans/{PLAN_ID}/items"),
    ("put", f"/api/content/plans/{PLAN_ID}/items/order"),
    ("patch", f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}"),
    ("delete", f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}"),
    ("post", f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}/post"),
    ("post", f"/api/content/plans/{PLAN_ID}/tasks"),
    ("post", f"/api/content/plans/{PLAN_ID}/ai-items"),
]


@pytest.mark.parametrize("method,url", ENDPOINTS)
def test_unauthenticated_is_strict_401(client, method, url):
    assert client.raw().request(method.upper(), url, json={}).status_code == 401


class TestValidation:
    def test_create_requires_title_and_valid_month(self, client):
        assert client.post("/api/content/plans", json={"month": "2026-11"}).status_code == 422
        assert client.post("/api/content/plans", json={"title": "x", "month": "2026/11"}).status_code == 422

    def test_extra_field_rejected(self, client):
        r = client.post("/api/content/plans", json={"title": "x", "month": "2026-11", "rogue": 1})
        assert r.status_code == 422

    def test_creation_mode_literal(self, client):
        r = client.post("/api/content/plans",
                        json={"title": "x", "month": "2026-11", "creation_mode": "imported"})
        assert r.status_code == 422

    def test_item_platform_literal(self, client):
        r = client.post(f"/api/content/plans/{PLAN_ID}/items",
                        json={"items": [{"title": "t", "platform": "myspace"}]})
        assert r.status_code == 422

    def test_empty_patch_is_400(self, client):
        assert client.patch(f"/api/content/plans/{PLAN_ID}", json={}).status_code == 400
        assert client.patch(f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}", json={}).status_code == 400

    def test_ai_count_bounds_and_window(self, client):
        for body in ({**AI_BODY, "items_count": 21}, {**AI_BODY, "items_count": 0},
                     {**AI_BODY, "period_days": 10}, {**AI_BODY, "weekdays": []},
                     {**AI_BODY, "platforms": []}, {**AI_BODY, "weekdays": [9]}):
            assert client.post(f"/api/content/plans/{PLAN_ID}/ai-items", json=body).status_code == 422


class TestFlows:
    def test_get_missing_plan_is_404(self, client):
        client.mock_supabase.set_table_data("content_plans", [])
        assert client.get(f"/api/content/plans/{PLAN_ID}").status_code == 404

    def test_list_returns_plans_with_items(self, client):
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data("content_plan_items", [_item()])
        body = client.get("/api/content/plans").json()
        assert body["total"] == 1
        assert body["items"][0]["items"][0]["title"] == "Reels X"

    def test_create_tasks_skips_ineligible_items(self, client):
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data(
            "content_plan_items",
            [_item(), _item(id="44444444-4444-4444-4444-444444444444", task_id="t-1")],
        )
        r = client.post(f"/api/content/plans/{PLAN_ID}/tasks",
                        json={"item_ids": [ITEM_ID, "44444444-4444-4444-4444-444444444444"]})
        assert r.status_code == 201
        assert r.json()["created"] == 1 and r.json()["skipped"] == 1
        assert len(client.mock_supabase.table("tasks").inserted_payloads) == 1

    def test_delete_item_with_task_discards(self, client):
        client.mock_supabase.set_table_data("content_plan_items", [_item(task_id="t-1")])
        r = client.delete(f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}")
        assert r.status_code == 200 and r.json() == {"deleted": False, "discarded": True}

    def test_delete_item_without_task_deletes(self, client):
        client.mock_supabase.set_table_data("content_plan_items", [_item()])
        r = client.delete(f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}")
        assert r.json() == {"deleted": True, "discarded": False}

    def test_promote_conflict_when_already_posted(self, client):
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data("content_plan_items", [_item(post_id="p-1")])
        r = client.post(f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}/post")
        assert r.status_code == 409


class _Scripted:
    replies: deque = deque()

    async def chat_completion(self, messages, *, model, api_key, **kwargs):
        return type(self).replies.popleft()

    async def close(self):  # pragma: no cover
        return None


@pytest.fixture
def llm_state():
    """Swap the process LLM config for the test, restore the app's afterwards."""
    previous = get_llm_config()
    register("scriptedorbity", _Scripted)
    yield
    _provider_cache.clear()
    configure_llm(previous)


class TestAI:
    def test_not_configured_is_honest_503(self, client, llm_state):
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: None,
                                default_provider="scriptedorbity"))
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data("content_plan_items", [])
        r = client.post(f"/api/content/plans/{PLAN_ID}/ai-items", json=AI_BODY)
        assert r.status_code == 503
        assert "IA não configurada" in r.text

    def test_success_returns_preview_and_persists_nothing(self, client, llm_state):
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k",
                                default_provider="scriptedorbity"))
        _Scripted.replies = deque([json.dumps({"items": [
            {"title": "A", "description": "x", "format": "reels", "platform": "instagram",
             "post_date": "2026-11-02"},
            {"title": "B", "description": "y", "format": "feed", "platform": "instagram",
             "post_date": "2026-11-04"}]})])
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data("content_plan_items", [])
        r = client.post(f"/api/content/plans/{PLAN_ID}/ai-items", json=AI_BODY)
        assert r.status_code == 200, r.text
        assert [i["title"] for i in r.json()["items"]] == ["A", "B"]
        assert client.mock_supabase.table("content_plan_items").inserted_payloads == []

    def test_invalid_output_is_502_not_partial(self, client, llm_state):
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k",
                                default_provider="scriptedorbity"))
        bad = json.dumps({"items": [{"title": "A", "platform": "instagram", "post_date": "2026-11-02"}]})
        _Scripted.replies = deque([bad, bad])
        client.mock_supabase.set_table_data("content_plans", [_plan()])
        client.mock_supabase.set_table_data("content_plan_items", [])
        r = client.post(f"/api/content/plans/{PLAN_ID}/ai-items", json=AI_BODY)
        assert handler_status(r) == 502
