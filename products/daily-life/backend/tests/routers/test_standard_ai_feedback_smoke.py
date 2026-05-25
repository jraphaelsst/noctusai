"""Mount-smoke tests for the seed `ai_feedback` standard router on daily-life.

Per PROJECT.md §6 Phase 3 / PF lessons §d.4: 2-test minimum per router
(status + body assertion). Extends with the ERP-canonical 5-test shape
(route-exists / auth-gate / happy-path / user-isolation / shape-contract)
since the pattern is already proven across ERP.

`ai_feedback` has two endpoints — `POST` to upsert and `GET` to read the
caller's row for a given `output_ref`. The smoke uses `GET` (read side)
which is safe to exercise without setting up upsert seams; the POST path is
exercised by other tests + the seed test suite.

Status-code assertions precede body assertions per the
`status-code-assertion-rule` (KB § PATTERNS/testing.md).
"""


class TestAiFeedbackStandardRouterMountSmoke:
    """`GET /api/ai/feedback?output_ref=...` — seed `ai_feedback` router."""

    def test_route_exists(self, client):
        """(a) /api/ai/feedback is mounted — not 404."""
        client.mock_supabase.set_table_data("ai_feedback", [])
        resp = client.get(
            "/api/ai/feedback",
            params={"output_ref": "ai_output:abc-123"},
        )
        assert resp.status_code != 404

    def test_requires_auth(self, client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = client.raw().get(
            "/api/ai/feedback",
            params={"output_ref": "ai_output:abc-123"},
        )
        assert resp.status_code == 401

    def test_happy_path_returns_200_with_data(self, client):
        """(c) Happy path: authenticated GET returns 200 + the row (or
        null when no feedback exists). Seed one matching feedback row."""
        client.mock_supabase.set_table_data("ai_feedback", [
            {
                "user_id": "test-user-123",
                "output_ref": "ai_output:abc-123",
                "rating": 1,
                "notes": None,
                "prompt_version": "v1",
            },
        ])
        resp = client.get(
            "/api/ai/feedback",
            params={"output_ref": "ai_output:abc-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_isolates_other_users_feedback(self, client):
        """(d) Wrong-user isolation: seed router filters
        `.eq("user_id", str(user.id))`. Default mock user is
        `test-user-123`; seed feedback for another user against the same
        `output_ref` and assert it is filtered out."""
        client.mock_supabase.set_table_data("ai_feedback", [
            {
                "user_id": "other-user-456",
                "output_ref": "ai_output:abc-123",
                "rating": -1,
                "notes": "their text",
                "prompt_version": "v1",
            },
        ])
        resp = client.get(
            "/api/ai/feedback",
            params={"output_ref": "ai_output:abc-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # `other-user-456`'s row must NOT leak through; data should be
        # null (no feedback for `test-user-123` on this ref).
        assert body["data"] is None

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `data` (the row dict or None)."""
        client.mock_supabase.set_table_data("ai_feedback", [])
        resp = client.get(
            "/api/ai/feedback",
            params={"output_ref": "ai_output:nothing"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        # When no feedback exists, data is None — the absence shape.
        assert body["data"] is None
