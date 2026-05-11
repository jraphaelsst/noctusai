"""Regression test — StrictHttpModel rejects unknown request keys with 422.

Closes the silent-drop bug-class (memory `feedback_pydantic_silent_drop_kills_writes`):
pre-migration, an unknown field on `AppointmentCreate` was silently dropped by
Pydantic's `extra="ignore"` default. Post-migration, `noctusai_lib.api.StrictHttpModel`
inherits `extra="forbid"`, so the request returns **422 Unprocessable Entity** with
a detail body that names the offending location.

`/api/appointments` is the representative HTTP-boundary route — `AppointmentCreate`
is annotated as the request body and lives in `app/schemas/scheduling.py`, the file
migrated by this wave.
"""
from __future__ import annotations


class TestStrictHttpUnknownFieldRejected:
    def test_create_appointment_rejects_unknown_field_with_422(self, patient_client):
        # An unknown key on the JSON body must produce 422, not a silent drop.
        resp = patient_client.post(
            "/api/appointments",
            json={
                "therapist_id": "therapist-001",
                "scheduled_start": "2026-04-10T15:00:00Z",
                "definitely_not_a_field": "trojan",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        detail_str = str(body.get("detail", body))
        assert "definitely_not_a_field" in detail_str
