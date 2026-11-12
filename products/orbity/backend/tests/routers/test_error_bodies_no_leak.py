"""An HTTP error body is a CODE, never exception text (owner rule 2026-11-11, "NO-LEAKING").

Each case drives a REAL refusal through the mock DB (an unknown id, a foreign stage, a bad month ...) and asserts the
status the client sees is unchanged, the ``detail`` is the stable snake_case code, and nothing the service put in its
exception message (ids, "not found in org", driver text) reaches the body.
KB § PATTERNS/security/appsec-craft-canon.md.
"""
from __future__ import annotations

from tests.routers.test_financial_router import make_admin

SENTINEL = "LEAK-SENTINEL-9f3a"
UNKNOWN_UUID = "99999999-9999-4999-8999-999999999999"
CID = "c1000000-0000-4000-8000-000000000001"
PLAN_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "33333333-3333-3333-3333-333333333333"
TS = "2026-01-01T00:00:00+00:00"
# What the services put in their exception messages; none of it may appear in a body.
LEAKY_FRAGMENTS = ("not found", "does not belong", "Stage ", "Lead ", "Report ", "Flow ", "Ad account ", SENTINEL)


def _code_of(resp) -> str:
    """The seed's error envelope is ``{"error": {"code", "message"}}``; the HTTPException ``detail`` rides as ``message``."""
    body = resp.json()
    return body["error"]["message"] if "error" in body else body["detail"]


def _assert_code(resp, status_code: int, code: str) -> None:
    assert resp.status_code == status_code, resp.text
    assert _code_of(resp) == code
    for fragment in LEAKY_FRAGMENTS:
        assert fragment not in resp.text, f"{fragment!r} leaked in {resp.text}"


class TestCrmBodies:
    def test_move_to_a_foreign_stage_is_a_code(self, client):
        _assert_code(client.patch(f"/api/crm/leads/{SENTINEL}/stage", json={"stage_id": UNKNOWN_UUID}), 400, "invalid_stage")

    def test_activity_on_an_unknown_lead_is_a_code(self, client):
        _assert_code(client.post(f"/api/crm/leads/{SENTINEL}/activities", json={"type": "note"}), 404, "lead_not_found")

    def test_score_of_an_unknown_lead_is_a_code(self, client):
        _assert_code(client.post(f"/api/crm/leads/{SENTINEL}/score"), 404, "lead_not_found")


class TestOtherFamilies:
    def test_cash_flow_with_a_bad_month_is_a_code(self, client):
        _assert_code(client.get(f"/api/financial/cash-flow/{SENTINEL}"), 422, "invalid_month")

    def test_generating_an_unknown_report_is_a_code(self, client):
        _assert_code(client.post(f"/api/reports/{SENTINEL}/generate", json={}), 404, "report_not_found")

    def test_syncing_an_unknown_ad_account_is_a_code(self, client):
        _assert_code(client.post("/api/meta-ads/sync", json={"ad_account_id": UNKNOWN_UUID}), 404, "ad_account_not_found")

    def test_triggering_an_unknown_flow_is_a_code(self, client):
        _assert_code(
            client.post(f"/api/automation/flows/{SENTINEL}/trigger", json={"lead_id": UNKNOWN_UUID}),
            404, "flow_or_lead_not_found",
        )

    def test_archiving_an_unknown_client_carries_the_billing_code(self, client):
        make_admin(client)
        client.mock_supabase.set_table_data("clients", [])
        resp = client.post(f"/api/clients/{CID}/archive", json={})
        assert resp.status_code == 404, resp.text
        assert _code_of(resp) == "cliente_nao_encontrado"

    def test_promoting_an_already_posted_item_is_a_code(self, client):
        org = str(__import__("app.dependencies", fromlist=["x"]).coerce_org_uuid("test-org-123"))
        client.mock_supabase.set_table_data("content_plans", [{
            "id": PLAN_ID, "org_id": org, "client_id": None, "campaign_id": None, "title": "N", "month": "2026-11",
            "strategy_context": {}, "status": "active", "creation_mode": "manual", "created_at": TS, "updated_at": TS}])
        client.mock_supabase.set_table_data("content_plan_items", [{
            "id": ITEM_ID, "org_id": org, "plan_id": PLAN_ID, "order_position": 0, "title": "R", "description": "d",
            "format": "reels", "platform": "instagram", "post_date": "2026-11-10", "due_date": None, "caption": None,
            "reference_notes": None, "status": "planned", "task_id": None, "post_id": "p-1", "created_at": TS, "updated_at": TS}])
        resp = client.post(f"/api/content/plans/{PLAN_ID}/items/{ITEM_ID}/post")
        assert resp.status_code == 409, resp.text
        assert _code_of(resp) == "post_not_promotable"
        assert "já virou" not in resp.text
