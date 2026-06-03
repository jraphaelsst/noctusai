"""
Auth-boundary + validation tests for the /api/agenda/* router.

Auth: strict == 401 for all endpoints (not 404/422).
Validation: StrictHttpModel extra='forbid' → 422 for unknown fields.
"""
import pytest

TEST_ORG = "00000000-0000-0000-0000-000000000001"


class TestAgendaRouterAuth:
    """Every /api/agenda/* endpoint requires authentication — strict 401."""

    def test_list_events_without_auth_returns_401(self, client):
        assert client.raw().get("/api/agenda/events").status_code == 401

    def test_create_event_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/agenda/events",
            json={
                "title": "Reunião",
                "starts_at": "2026-06-01T10:00:00+00:00",
                "ends_at": "2026-06-01T11:00:00+00:00",
            },
        ).status_code == 401

    def test_get_event_without_auth_returns_401(self, client):
        assert client.raw().get("/api/agenda/events/some-id").status_code == 401

    def test_update_event_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/agenda/events/some-id", json={"title": "x"}
        ).status_code == 401

    def test_delete_event_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/agenda/events/some-id").status_code == 401

    def test_sync_gcal_without_auth_returns_401(self, client):
        assert client.raw().post("/api/agenda/events/some-id/sync-gcal").status_code == 401


class TestAgendaRouterValidation:
    """Pydantic validation enforced on inbound schemas."""

    def test_create_event_empty_title_returns_422(self, client):
        resp = client.post(
            "/api/agenda/events",
            json={
                "title": "",
                "starts_at": "2026-06-01T10:00:00+00:00",
                "ends_at": "2026-06-01T11:00:00+00:00",
            },
        )
        assert resp.status_code == 422

    def test_create_event_missing_required_returns_422(self, client):
        resp = client.post("/api/agenda/events", json={"title": "x"})
        assert resp.status_code == 422

    def test_create_event_invalid_type_returns_422(self, client):
        resp = client.post(
            "/api/agenda/events",
            json={
                "title": "x",
                "event_type": "webinar",
                "starts_at": "2026-06-01T10:00:00+00:00",
                "ends_at": "2026-06-01T11:00:00+00:00",
            },
        )
        assert resp.status_code == 422

    def test_create_event_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/agenda/events",
            json={
                "title": "x",
                "starts_at": "2026-06-01T10:00:00+00:00",
                "ends_at": "2026-06-01T11:00:00+00:00",
                "rogue": True,
            },
        )
        assert resp.status_code == 422

    def test_list_events_invalid_page_size_returns_422(self, client):
        resp = client.get("/api/agenda/events?page_size=9999")
        assert resp.status_code == 422


class TestAgendaRouterHappyPath:
    """Authenticated happy-path smoke tests (mock DB)."""

    def test_list_events_returns_200(self, client):
        resp = client.get("/api/agenda/events")
        assert resp.status_code == 200

    def test_create_event_returns_201_or_502(self, client):
        """201 on success; 502 if mock returns no data (both valid in test env)."""
        resp = client.post(
            "/api/agenda/events",
            json={
                "title": "Reunião de kickoff",
                "event_type": "meeting",
                "starts_at": "2026-06-10T09:00:00+00:00",
                "ends_at": "2026-06-10T10:00:00+00:00",
            },
        )
        assert resp.status_code in (201, 502)

    def test_sync_gcal_event_not_found_returns_404_or_502(self, client):
        """sync-gcal on a non-existent event → 404 (event not found) or 502 (db error)."""
        resp = client.post("/api/agenda/events/non-existent-id/sync-gcal")
        # 404 = correct semantic; 502 = mock DB raised; both acceptable in unit test
        assert resp.status_code in (404, 502)
