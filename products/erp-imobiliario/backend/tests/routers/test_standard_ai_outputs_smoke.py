"""Mount-smoke tests for the seed `ai_outputs` standard router on ERP.

Per PROJECT §6 Phase 7 / PF lessons §d.4: 5-test pattern — (a) route
exists, (b) auth gate, (c) happy-path 200, (d) wrong-ref isolation
(seed router scopes by `ref_type`+`ref_id` per `ai_router.py:50`), (e) shape.

The seed `fetch_outputs_for` filters by `(ref_type, ref_id)`; wrong-ref
isolation here pins the `ref_id` query-param contract — a leak across
refs would expose AI outputs for entities the caller didn't request.

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`).
"""


class TestAiOutputsStandardRouterMountSmoke:
    """`GET /api/ai/outputs?ref_type=&ref_id=` — seed `ai_outputs` router."""

    def test_route_exists(self, client):
        """(a) /api/ai/outputs is mounted — not 404."""
        client._mock_supabase.set_table_data("ai_outputs", [])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "ativo", "ref_id": "ativo-1"},
        )
        assert resp.status_code != 404

    def test_requires_auth(self, client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = client.raw().get(
            "/api/ai/outputs",
            params={"ref_type": "ativo", "ref_id": "ativo-1"},
        )
        assert resp.status_code == 401

    def test_happy_path_returns_200_with_data(self, client):
        """(c) Happy path: authenticated GET returns 200 + matching rows."""
        client._mock_supabase.set_table_data("ai_outputs", [
            {
                "id": "aio-1", "ref_type": "ativo", "ref_id": "ativo-1",
                "kind": "indicator", "model": "gpt-4o-mini",
                "created_at": "2026-05-20T10:00:00Z",
            },
        ])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "ativo", "ref_id": "ativo-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert body["count"] == len(body["data"])

    def test_isolates_other_refs(self, client):
        """(d) Wrong-ref isolation: seed `fetch_outputs_for` filters by
        `(ref_type, ref_id)`. Seed rows for two refs — assert only the
        queried one surfaces."""
        client._mock_supabase.set_table_data("ai_outputs", [
            {
                "id": "mine", "ref_type": "ativo", "ref_id": "ativo-1",
                "kind": "indicator", "model": "gpt-4o-mini",
                "created_at": "2026-05-20T10:00:00Z",
            },
            {
                "id": "other", "ref_type": "ativo", "ref_id": "ativo-99",
                "kind": "indicator", "model": "gpt-4o-mini",
                "created_at": "2026-05-20T10:00:00Z",
            },
        ])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "ativo", "ref_id": "ativo-1"},
        )
        assert resp.status_code == 200
        ids = {o["id"] for o in resp.json()["data"]}
        # Only the requested ref's output should be returned. The mock
        # supabase respects `.eq()` filters when `fetch_outputs_for`
        # applies them; if a leak occurs we'd see "other" too.
        assert "other" not in ids

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `data` (list) + `count` (int) —
        the contract `create_ai_outputs_router` builds (ai_router.py:61)."""
        client._mock_supabase.set_table_data("ai_outputs", [])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "ativo", "ref_id": "ativo-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "count" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["count"], int)
