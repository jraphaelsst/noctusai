"""Mount-smoke tests for the seed `ai_outputs` standard router on daily-life.

Per PROJECT.md §6 Phase 3 / PF lessons §d.4: 2-test minimum per router
(status + body assertion). Extends with the ERP-canonical 5-test shape
(route-exists / auth-gate / happy-path / ref-isolation / shape-contract).

The seed `fetch_outputs_for` filters by `(ref_type, ref_id)`; wrong-ref
isolation here pins the `ref_id` query-param contract — a leak across refs
would expose AI outputs for entities the caller did not request.

The smoke passes against the seed Fake / MockRequestBuilder (no live table
needed at test time — migration 006_ai_outputs.sql makes it correct in prod).

Status-code assertions precede body assertions per the
`status-code-assertion-rule` (KB § PATTERNS/testing.md).
"""


class TestAiOutputsStandardRouterMountSmoke:
    """`GET /api/ai/outputs?ref_type=&ref_id=` — seed `ai_outputs` router."""

    def test_route_exists(self, client):
        """(a) /api/ai/outputs is mounted — not 404."""
        client.mock_supabase.set_table_data("ai_outputs", [])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "tarefa", "ref_id": "tarefa-1"},
        )
        assert resp.status_code != 404

    def test_requires_auth(self, client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = client.raw().get(
            "/api/ai/outputs",
            params={"ref_type": "tarefa", "ref_id": "tarefa-1"},
        )
        assert resp.status_code == 401

    def test_happy_path_returns_200_with_data(self, client):
        """(c) Happy path: authenticated GET returns 200 + matching rows."""
        client.mock_supabase.set_table_data("ai_outputs", [
            {
                "id": "aio-1",
                "ref_type": "tarefa",
                "ref_id": "tarefa-1",
                "kind": "classification",
                "label": "Alta prioridade",
                "created_at": "2026-05-25T10:00:00Z",
            },
        ])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "tarefa", "ref_id": "tarefa-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert body["count"] == len(body["data"])

    def test_isolates_other_refs(self, client):
        """(d) Wrong-ref isolation: seed `fetch_outputs_for` filters by
        `(ref_type, ref_id)`. Seed rows for two refs — assert only the
        queried one surfaces."""
        client.mock_supabase.set_table_data("ai_outputs", [
            {
                "id": "mine",
                "ref_type": "tarefa",
                "ref_id": "tarefa-1",
                "kind": "classification",
                "label": "Urgente",
                "created_at": "2026-05-25T10:00:00Z",
            },
            {
                "id": "other",
                "ref_type": "tarefa",
                "ref_id": "tarefa-99",
                "kind": "classification",
                "label": "Normal",
                "created_at": "2026-05-25T10:00:00Z",
            },
        ])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "tarefa", "ref_id": "tarefa-1"},
        )
        assert resp.status_code == 200
        ids = {o["id"] for o in resp.json()["data"]}
        # Only the requested ref's output should be returned.
        assert "other" not in ids

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `data` (list) + `count` (int)."""
        client.mock_supabase.set_table_data("ai_outputs", [])
        resp = client.get(
            "/api/ai/outputs",
            params={"ref_type": "tarefa", "ref_id": "tarefa-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "count" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["count"], int)
