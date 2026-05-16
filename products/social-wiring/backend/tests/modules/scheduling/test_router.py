"""HTTP-boundary tests for the ``scheduling`` module router (Wave 2.3).

Deferred at W2.3 with the explicit named destination "router-level
TestClient tests after the 001 splice lands the ``sched_*`` tables"
(MockSupabaseClient schema validation needs the tables to exist). The
W2-INTEGRATE pass spliced ``scheduling.sql`` into
``migrations/001_social-wiring.sql``, so these now collect + run clean.

Exercises the FastAPI layer through the real ``register()`` seam:
auth wiring, StrictHttpModel validation, status codes, the engine-backed
``/propose`` 404 path. Engine/tool/LID/support internals are covered in
``test_engine.py`` / ``test_tool_registry.py`` / ``test_authorization.py``
/ ``test_support_services.py``. Every assertion pins ``.status_code``
(status-code-assertion keeper).
"""
from __future__ import annotations


class TestCondominiumsRouter:
    def test_list_condominiums_empty_ok(self, client):
        resp = client.get("/api/scheduling/condominiums")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_create_condominium_requires_fields(self, client):
        resp = client.post("/api/scheduling/condominiums", json={})
        assert resp.status_code == 422, resp.text

    def test_create_condominium_rejects_unknown_field(self, client):
        # StrictHttpModel → extra="forbid" → 422 on unknown keys.
        resp = client.post(
            "/api/scheduling/condominiums",
            json={"name": "Edf X", "address": "Rua 1", "bogus": 1},
        )
        assert resp.status_code == 422, resp.text

    def test_create_condominium_validates_latitude_bound(self, client):
        resp = client.post(
            "/api/scheduling/condominiums",
            json={"name": "Edf X", "address": "Rua 1", "latitude": 999.0},
        )
        assert resp.status_code == 422, resp.text

    def test_update_unknown_condominium_404(self, client):
        resp = client.patch(
            "/api/scheduling/condominiums/"
            "00000000-0000-0000-0000-000000000000",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 404, resp.text

    def test_update_condominium_empty_body_400(self, client):
        resp = client.patch(
            "/api/scheduling/condominiums/"
            "00000000-0000-0000-0000-000000000000",
            json={},
        )
        assert resp.status_code == 400, resp.text

    def test_update_condominium_bad_uuid_422(self, client):
        resp = client.patch(
            "/api/scheduling/condominiums/not-a-uuid",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 422, resp.text


class TestPropertiesRouter:
    def test_list_properties_empty_ok(self, client):
        resp = client.get("/api/scheduling/properties")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_create_property_requires_condominium_and_code(self, client):
        resp = client.post("/api/scheduling/properties", json={})
        assert resp.status_code == 422, resp.text

    def test_create_property_validates_code_length(self, client):
        resp = client.post(
            "/api/scheduling/properties",
            json={
                "condominium_id": "00000000-0000-0000-0000-000000000000",
                "code": "",
            },
        )
        assert resp.status_code == 422, resp.text

    def test_update_unknown_property_404(self, client):
        resp = client.patch(
            "/api/scheduling/properties/"
            "00000000-0000-0000-0000-000000000000",
            json={"code": "A-101"},
        )
        assert resp.status_code == 404, resp.text


class TestServicesRouter:
    def test_list_services_empty_ok(self, client):
        resp = client.get("/api/scheduling/services")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_create_service_requires_name(self, client):
        resp = client.post("/api/scheduling/services", json={})
        assert resp.status_code == 422, resp.text

    def test_create_service_rejects_nonpositive_duration(self, client):
        resp = client.post(
            "/api/scheduling/services",
            json={"name": "Photo", "default_duration_minutes": 0},
        )
        assert resp.status_code == 422, resp.text


class TestUsersRouter:
    def test_list_users_empty_ok(self, client):
        resp = client.get("/api/scheduling/users")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_create_user_requires_role_and_phone(self, client):
        resp = client.post(
            "/api/scheduling/users", json={"name": "Crew A"}
        )
        assert resp.status_code == 422, resp.text

    def test_create_user_rejects_unknown_role(self, client):
        resp = client.post(
            "/api/scheduling/users",
            json={
                "name": "Crew A",
                "role": "intergalactic_pilot",
                "phone_number": "+5511999999999",
            },
        )
        assert resp.status_code == 422, resp.text


class TestAppointmentReads:
    def test_list_appointments_empty_ok(self, client):
        resp = client.get("/api/scheduling/appointments")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_list_appointments_with_status_filter_ok(self, client):
        resp = client.get(
            "/api/scheduling/appointments",
            params={"appointment_status": "scheduled"},
        )
        assert resp.status_code == 200, resp.text

    def test_list_appointment_requests_empty_ok(self, client):
        resp = client.get("/api/scheduling/appointment-requests")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []


class TestPendingChatIdentities:
    def test_list_pending_chat_identities_empty_ok(self, client):
        resp = client.get("/api/scheduling/pending-chat-identities")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_resolve_unknown_identity_404(self, client):
        resp = client.patch(
            "/api/scheduling/pending-chat-identities/"
            "00000000-0000-0000-0000-000000000000",
            json={"status": "resolved"},
        )
        assert resp.status_code == 404, resp.text

    def test_resolve_rejects_unknown_field(self, client):
        resp = client.patch(
            "/api/scheduling/pending-chat-identities/"
            "00000000-0000-0000-0000-000000000000",
            json={"status": "resolved", "bogus": True},
        )
        assert resp.status_code == 422, resp.text


class TestProposeEndpoint:
    def test_propose_requires_body(self, client):
        resp = client.post("/api/scheduling/propose", json={})
        assert resp.status_code == 422, resp.text

    def test_propose_rejects_unknown_time_window(self, client):
        resp = client.post(
            "/api/scheduling/propose",
            json={
                "property_code": "A-101",
                "requested_date": "2026-06-01",
                "time_window": "midnight",
            },
        )
        assert resp.status_code == 422, resp.text

    def test_propose_unknown_property_404(self, client):
        # No sched_properties rows seeded → the engine raises ValueError
        # for the unknown property_code, which the router maps to 404.
        resp = client.post(
            "/api/scheduling/propose",
            json={
                "property_code": "DOES-NOT-EXIST",
                "requested_date": "2026-06-01",
                "time_window": "any",
            },
        )
        assert resp.status_code == 404, resp.text


class TestSchedulingAuth:
    def test_unauthenticated_list_rejected(self, client):
        resp = client.raw().get("/api/scheduling/condominiums")
        assert resp.status_code in (401, 403), resp.text

    def test_unauthenticated_propose_rejected(self, client):
        resp = client.raw().post(
            "/api/scheduling/propose",
            json={
                "property_code": "A-101",
                "requested_date": "2026-06-01",
            },
        )
        assert resp.status_code in (401, 403), resp.text
