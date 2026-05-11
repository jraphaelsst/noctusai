"""Mount-smoke tests for the seed standard routers PF opts into.

Per PROJECT §5.2.8 / §6 Phase 7: assert each of the 3 standard routers
mounted in `app/main.py § standard_routers=[..., "ai_outputs", "ai_feedback"]`
plus the always-on `health` router returns a 200 (or a 200-shaped body)
on the canonical GET. These guard against future seed-side wiring
regressions surfacing as 404/405/422 in PF's mount of the standard
surface (the slip that §5.2.8 called out — no per-product smoke).

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`): every body assertion is paired with a
status-code assertion in the SAME test method.
"""


class TestAiOutputsStandardRouter:
    """`GET /api/ai/outputs?ref_type=&ref_id=` — seed `ai_outputs` router."""

    def test_lists_outputs_for_ref(self, client):
        # Seed PF's ai_outputs table with a single matching row so the
        # router-shape contract (`{"data": [...], "count": N}`) is exercised
        # rather than the empty-list fallback path.
        client.mock_supabase.set_table_data("ai_outputs", [
            {
                "id": "aio-1",
                "ref_type": "ativo",
                "ref_id": "ativo-1",
                "kind": "indicator",
                "model": "gpt-4o-mini",
                "created_at": "2026-05-11T00:00:00Z",
            },
        ])
        resp = client.get("/api/ai/outputs", params={"ref_type": "ativo", "ref_id": "ativo-1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "count" in body
        assert isinstance(body["data"], list)

    def test_requires_auth(self, client):
        resp = client.raw().get("/api/ai/outputs", params={"ref_type": "ativo", "ref_id": "x"})
        assert resp.status_code == 401


class TestAiFeedbackStandardRouter:
    """`GET /api/ai/feedback?output_ref=...` — seed `ai_feedback` router.

    Note: PROJECT §6 Phase 7 line 578 referenced `?ref_type=&ref_id=` from an
    earlier draft of the router spec. The current shipped router (`seed/
    framework/backend/noctusai_seed/ai_feedback_router.py:85-106`) keys on
    a single `output_ref` query param; this test pins the current contract.
    """

    def test_returns_null_when_no_feedback(self, client):
        # Empty `ai_feedback` table → handler returns `{"data": null}` (200).
        client.mock_supabase.set_table_data("ai_feedback", [])
        resp = client.get("/api/ai/feedback", params={"output_ref": "ai_output:nope"})
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_requires_auth(self, client):
        resp = client.raw().get("/api/ai/feedback", params={"output_ref": "ai_output:x"})
        assert resp.status_code == 401


class TestHealthStandardRouter:
    """`GET /api/health` — seed `health` router (unauthenticated probe)."""

    def test_returns_ok_status_and_product_id(self, client):
        # `/api/health` is unauthenticated by seed contract; use the raw
        # TestClient to ensure auth-header isn't masking anything.
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["product"] == "Financas Pessoais"
        assert "version" in body
