"""Router-level coverage for ``app.routers.appointments``.

Lands in Phase 1 of media-scheduling-wiring alongside the ghost-field
enrichment (`property_label` / `condominium_label` / `service_type_id` /
`service_type_label` / `crew_assignee_id` / `crew_assignee_label`).

Covers:
  - GET /api/appointments returns 200 + `{data, total}` envelope when
    rows exist.
  - GET /api/appointments enriches each row with the 6 ghost fields via
    two-step joins on properties / condominiums / appointment_request_
    services / service_types / route_groups / authorized_users.
  - GET /api/appointments rejects unknown status with 400.
  - GET /api/appointments/{id} returns 200 + enriched row.
  - GET /api/appointments/{id} returns 404 when no match.
  - Auth boundary (Pattern F adoption): missing Authorization header → 401.
"""
from __future__ import annotations

from unittest.mock import patch

from noctusai_lib.testing import MockSupabaseClient


def _patch_appointments_db(mock_sb):
    """`appointments.py` does `from app.database import get_supabase_client`,
    snapshotting the symbol at import time. Patch the router's bound
    symbol directly so writes from this test reach the route's
    in-process Supabase client."""
    return patch("app.routers.appointments.get_supabase_client", return_value=mock_sb)


def _seed_enrichment_tables(mock: MockSupabaseClient) -> None:
    """Seed the join-target tables so the enrichment helper has labels
    to look up. Each appointment in the test row set references these
    ids exactly."""
    mock.set_table_data(
        "properties",
        [
            {"id": 10, "code": "APT-A101"},
            {"id": 11, "code": "APT-B202"},
        ],
    )
    mock.set_table_data(
        "condominiums",
        [
            {"id": 100, "name": "Edificio Aurora"},
            {"id": 101, "name": "Edificio Boreal"},
        ],
    )
    mock.set_table_data(
        "appointment_request_services",
        [
            {"appointment_request_id": 500, "service_type_id": 1},
            {"appointment_request_id": 501, "service_type_id": 2},
        ],
    )
    mock.set_table_data(
        "service_types",
        [
            {"id": 1, "name": "Photo Shoot"},
            {"id": 2, "name": "Video Tour"},
        ],
    )
    mock.set_table_data(
        "route_groups",
        [
            {"id": 200, "media_crew_user_id": 30},
            {"id": 201, "media_crew_user_id": 31},
        ],
    )
    mock.set_table_data(
        "authorized_users",
        [
            {"id": 30, "name": "Alice Crew"},
            {"id": 31, "name": "Bob Crew"},
        ],
    )


def test_list_appointments_returns_envelope_with_enriched_rows(client):
    """200 + each row carries the 6 ghost fields populated via joins."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "appointments",
        [
            {
                "id": 1,
                "start_at": "2026-06-01T09:00:00+00:00",
                "end_at": "2026-06-01T10:00:00+00:00",
                "property_id": 10,
                "condominium_id": 100,
                "appointment_request_id": 500,
                "route_group_id": 200,
                "status": "scheduled",
                "created_at": "2026-05-15T00:00:00+00:00",
                "updated_at": "2026-05-15T00:00:00+00:00",
            },
            {
                "id": 2,
                "start_at": "2026-06-02T14:00:00+00:00",
                "end_at": "2026-06-02T15:00:00+00:00",
                "property_id": 11,
                "condominium_id": 101,
                "appointment_request_id": 501,
                "route_group_id": 201,
                "status": "confirmed",
                "created_at": "2026-05-15T00:00:00+00:00",
                "updated_at": "2026-05-15T00:00:00+00:00",
            },
        ],
    )
    _seed_enrichment_tables(mock)

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    rows = body["data"]
    assert len(rows) == 2

    # Wire-shape: starts_at / ends_at populated, start_at / end_at gone.
    assert rows[0]["starts_at"] == "2026-06-01T09:00:00+00:00"
    assert rows[0]["ends_at"] == "2026-06-01T10:00:00+00:00"
    assert "start_at" not in rows[0]
    assert "end_at" not in rows[0]

    # Ghost fields populated for row 0.
    assert rows[0]["property_label"] == "APT-A101"
    assert rows[0]["condominium_label"] == "Edificio Aurora"
    assert rows[0]["service_type_id"] == 1
    assert rows[0]["service_type_label"] == "Photo Shoot"
    assert rows[0]["crew_assignee_id"] == 30
    assert rows[0]["crew_assignee_label"] == "Alice Crew"

    # Ghost fields populated for row 1 (different FKs).
    assert rows[1]["property_label"] == "APT-B202"
    assert rows[1]["condominium_label"] == "Edificio Boreal"
    assert rows[1]["service_type_id"] == 2
    assert rows[1]["service_type_label"] == "Video Tour"
    assert rows[1]["crew_assignee_id"] == 31
    assert rows[1]["crew_assignee_label"] == "Bob Crew"


def test_list_appointments_returns_empty_envelope_when_no_rows(client):
    """0 rows → still 200 + `{data: [], total: 0}` — no enrichment failure."""
    mock = MockSupabaseClient()
    mock.set_table_data("appointments", [])

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments")

    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0}


def test_list_appointments_handles_missing_join_target_gracefully(client):
    """When a referenced label row is missing, the ghost field is null
    rather than raising — partial degradation, not whole-response loss."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "appointments",
        [
            {
                "id": 1,
                "start_at": "2026-06-01T09:00:00+00:00",
                "end_at": "2026-06-01T10:00:00+00:00",
                "property_id": 10,
                "condominium_id": 100,
                # No appointment_request_id → service_type fields null.
                "appointment_request_id": None,
                # No route_group_id → crew_assignee fields null.
                "route_group_id": None,
                "status": "scheduled",
                "created_at": "2026-05-15T00:00:00+00:00",
                "updated_at": "2026-05-15T00:00:00+00:00",
            },
        ],
    )
    mock.set_table_data(
        "properties", [{"id": 10, "code": "APT-A101"}],
    )
    mock.set_table_data(
        "condominiums", [{"id": 100, "name": "Edificio Aurora"}],
    )
    # No appointment_request_services / service_types / route_groups /
    # authorized_users seeded — partial-data scenario.

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments")

    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert rows[0]["property_label"] == "APT-A101"
    assert rows[0]["condominium_label"] == "Edificio Aurora"
    assert rows[0]["service_type_id"] is None
    assert rows[0]["service_type_label"] is None
    assert rows[0]["crew_assignee_id"] is None
    assert rows[0]["crew_assignee_label"] is None


def test_list_appointments_rejects_invalid_status(client):
    """status=garbage → 400 with allowed-list detail (seed error envelope)."""
    mock = MockSupabaseClient()
    mock.set_table_data("appointments", [])

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments?status=garbage")

    assert resp.status_code == 400
    body = resp.json()
    # Seed wraps HTTPException into `{"error": {"code", "message"}}`.
    assert "Invalid status" in body["error"]["message"]


def test_get_appointment_detail_returns_enriched_row(client):
    """GET /api/appointments/{id} runs the same enrichment as list.

    Note: seeded ``id`` is the string ``"1"`` so the route's
    ``.eq("id", appointment_id)`` predicate (where ``appointment_id``
    is the URL path string) matches under the mock's literal-eq
    evaluator. Production Supabase coerces; the mock doesn't.
    """
    mock = MockSupabaseClient()
    mock.set_table_data(
        "appointments",
        [
            {
                "id": "1",
                "start_at": "2026-06-01T09:00:00+00:00",
                "end_at": "2026-06-01T10:00:00+00:00",
                "property_id": 10,
                "condominium_id": 100,
                "appointment_request_id": 500,
                "route_group_id": 200,
                "status": "scheduled",
                "created_at": "2026-05-15T00:00:00+00:00",
                "updated_at": "2026-05-15T00:00:00+00:00",
            },
        ],
    )
    _seed_enrichment_tables(mock)

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments/1")

    assert resp.status_code == 200
    row = resp.json()
    assert row["starts_at"] == "2026-06-01T09:00:00+00:00"
    assert row["property_label"] == "APT-A101"
    assert row["service_type_label"] == "Photo Shoot"
    assert row["crew_assignee_label"] == "Alice Crew"


def test_get_appointment_detail_returns_404_when_missing(client):
    """No matching row → 404 with Appointment not found detail."""
    mock = MockSupabaseClient()
    mock.set_table_data("appointments", [])

    with _patch_appointments_db(mock):
        resp = client.get("/api/appointments/999")

    assert resp.status_code == 404
    # Seed wraps HTTPException into `{"error": {"code", "message"}}`.
    assert resp.json()["error"]["message"] == "Appointment not found"


def test_list_appointments_requires_auth(client):
    """Pattern F adoption: missing Authorization header → 401."""
    resp = client.raw().get("/api/appointments")
    assert resp.status_code == 401


def test_get_appointment_requires_auth(client):
    """Detail route also gated via `Depends(get_current_user_org)`."""
    resp = client.raw().get("/api/appointments/1")
    assert resp.status_code == 401
