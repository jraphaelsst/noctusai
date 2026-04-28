"""Tests for the Consent Service — auditable per-session consent records.

compliance-audit-reconciliation Phase 5 / Q5 (2026-04-22).

KNOWN LIMITATION — the current `MockSupabaseClient` does NOT validate column
names and does NOT mutate state on `.update()` / `.insert()` calls. These
tests assert call-shape + dispatch + 404/400 paths, not actual row state.
Real row-state verification requires the `mock-supabase-schema-validation`
follow-up project (deferred).
"""
from __future__ import annotations

import pytest

from tests.conftest import MockSupabaseClient
from app.services import consent_service
from fastapi import HTTPException


APPT = {
    "id": "appt-s-001",
    "therapist_id": "therapist-s-001",
    "patient_id": "patient-s-001",
    "clinic_id": None,
}


@pytest.fixture
def db():
    d = MockSupabaseClient()
    d.set_table_data("appointments", [APPT])
    d.set_table_data("consent_records", [])
    return d


class TestGrantConsent:
    @pytest.mark.asyncio
    async def test_grant_as_therapist_succeeds(self, db):
        result = await consent_service.grant_consent(
            appointment_id="appt-s-001",
            scope="recording",
            policy_version="v1",
            purpose_text="x",
            actor_user_id="therapist-s-001",
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_grant_as_patient_succeeds(self, db):
        result = await consent_service.grant_consent(
            appointment_id="appt-s-001",
            scope="transcription",
            policy_version="v1",
            purpose_text="x",
            actor_user_id="patient-s-001",
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_grant_by_unrelated_user_raises_403(self, db):
        with pytest.raises(HTTPException) as exc:
            await consent_service.grant_consent(
                appointment_id="appt-s-001",
                scope="recording",
                policy_version="v1",
                purpose_text="x",
                actor_user_id="stranger-001",
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_grant_unknown_appointment_raises_404(self, db):
        db.set_table_data("appointments", [])
        with pytest.raises(HTTPException) as exc:
            await consent_service.grant_consent(
                appointment_id="nope",
                scope="recording",
                policy_version="v1",
                purpose_text="x",
                actor_user_id="therapist-s-001",
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_grant_invalid_scope_raises_422(self, db):
        with pytest.raises(HTTPException) as exc:
            await consent_service.grant_consent(
                appointment_id="appt-s-001",
                scope="bogus",
                policy_version="v1",
                purpose_text="x",
                actor_user_id="therapist-s-001",
                db=db,
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_grant_re_grant_updates_existing_row(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-001",
            "appointment_id": "appt-s-001",
            "patient_id": "patient-s-001",
            "therapist_id": "therapist-s-001",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "old",
            "actor_user_id": "patient-s-001",
            "granted_at": "2026-04-01T00:00:00-03:00",
            "revoked_at": "2026-04-10T00:00:00-03:00",
        }])
        result = await consent_service.grant_consent(
            appointment_id="appt-s-001",
            scope="recording",
            policy_version="v2",
            purpose_text="renewed",
            actor_user_id="patient-s-001",
            db=db,
        )
        assert result is not None


class TestRevokeConsent:
    @pytest.mark.asyncio
    async def test_revoke_active_succeeds(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-002",
            "appointment_id": "appt-s-001",
            "scope": "recording",
            "revoked_at": None,
        }])
        result = await consent_service.revoke_consent(
            appointment_id="appt-s-001",
            scope="recording",
            actor_user_id="patient-s-001",
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_revoke_missing_raises_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await consent_service.revoke_consent(
                appointment_id="appt-s-001",
                scope="recording",
                actor_user_id="patient-s-001",
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_raises_400(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-003",
            "appointment_id": "appt-s-001",
            "scope": "recording",
            "revoked_at": "2026-04-10T00:00:00-03:00",
        }])
        with pytest.raises(HTTPException) as exc:
            await consent_service.revoke_consent(
                appointment_id="appt-s-001",
                scope="recording",
                actor_user_id="patient-s-001",
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_by_unrelated_user_raises_403(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-004",
            "appointment_id": "appt-s-001",
            "scope": "recording",
            "revoked_at": None,
        }])
        with pytest.raises(HTTPException) as exc:
            await consent_service.revoke_consent(
                appointment_id="appt-s-001",
                scope="recording",
                actor_user_id="stranger-001",
                db=db,
            )
        assert exc.value.status_code == 403


class TestCheckActiveConsent:
    @pytest.mark.asyncio
    async def test_check_returns_true_when_active(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-005",
            "appointment_id": "appt-s-001",
            "scope": "recording",
            "revoked_at": None,
        }])
        assert await consent_service.check_active_consent(
            "appt-s-001", "recording", db
        ) is True

    @pytest.mark.asyncio
    async def test_check_returns_false_when_revoked(self, db):
        db.set_table_data("consent_records", [{
            "id": "c-006",
            "appointment_id": "appt-s-001",
            "scope": "recording",
            "revoked_at": "2026-04-10T00:00:00-03:00",
        }])
        assert await consent_service.check_active_consent(
            "appt-s-001", "recording", db
        ) is False

    @pytest.mark.asyncio
    async def test_check_returns_false_when_missing(self, db):
        assert await consent_service.check_active_consent(
            "appt-s-001", "recording", db
        ) is False

    @pytest.mark.asyncio
    async def test_check_invalid_scope_returns_false(self, db):
        assert await consent_service.check_active_consent(
            "appt-s-001", "bogus", db
        ) is False


class TestListConsents:
    @pytest.mark.asyncio
    async def test_list_returns_empty_when_none(self, db):
        result = await consent_service.list_consents("appt-s-001", db)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_all_scopes(self, db):
        db.set_table_data("consent_records", [
            {"id": "c-a", "appointment_id": "appt-s-001", "scope": "recording"},
            {"id": "c-b", "appointment_id": "appt-s-001", "scope": "transcription"},
        ])
        result = await consent_service.list_consents("appt-s-001", db)
        assert len(result) == 2
