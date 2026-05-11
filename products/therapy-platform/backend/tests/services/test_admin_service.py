"""
Service-level tests for admin Phase 2 additions.

Covers ``list_appointments_for_admin`` (DTO shape), ``admin_dashboard_metrics``
(aggregation math), ``suspend_entity`` (404 + invalid-type branches), and
the Phase-5 reject-flow audit-column invariants.
"""
from datetime import datetime, timezone

import pytest

from tests.conftest import MockSupabaseClient
from app.services import admin_service


SAMPLE_APPOINTMENT_ROW = {
    "id": "appt-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "clinic_id": "clinic-001",
    "scheduled_start": "2026-05-10T15:00:00Z",
    "scheduled_end": "2026-05-10T16:00:00Z",
    "status": "waiting",
    "patient_origin": "platform_assigned",
    "session_price_applied": 150.0,
    "created_at": "2026-05-01T10:00:00Z",
}


def _client():
    return MockSupabaseClient(validate_schema=False, schema="therapy")


@pytest.mark.asyncio
class TestListAppointmentsForAdmin:
    async def test_returns_dto_shape(self):
        db = _client()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_ROW])
        db.set_table_data("clinics", [
            {"id": "clinic-001", "name": "Clínica Alpha"},
        ])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        assert len(data) == 1
        row = data[0]
        assert row["id"] == "appt-001"
        assert row["clinic_name"] == "Clínica Alpha"
        # Identity resolver returns "" for unknown ids in the mock; the
        # key must still be present so the frontend doesn't crash.
        assert "patient_name" in row
        assert "therapist_name" in row
        assert row["status"] == "waiting"
        assert row["scheduled_start"] == "2026-05-10T15:00:00Z"

    async def test_clinic_name_missing_when_clinic_id_null(self):
        db = _client()
        row = {**SAMPLE_APPOINTMENT_ROW, "clinic_id": None}
        db.set_table_data("appointments", [row])
        db.set_table_data("clinics", [])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        assert data[0]["clinic_name"] is None

    async def test_empty_result(self):
        db = _client()
        db.set_table_data("appointments", [])
        db.set_table_data("clinics", [])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert data == []
        assert total == 0


@pytest.mark.asyncio
class TestAdminDashboardMetrics:
    async def test_metrics_shape(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "t1", "is_approved": False, "is_active": True},
        ])
        db.set_table_data("clinics", [
            {"id": "c1", "is_approved": False, "is_active": True},
            {"id": "c2", "is_approved": False, "is_active": True},
        ])
        db.set_table_data("appointments", [])
        db.set_table_data("transactions", [
            {"gross_amount": "200.00", "platform_fee_amount": "20.00", "status": "captured"},
        ])
        metrics = await admin_service.admin_dashboard_metrics(db)
        # MockSelectBuilder doesn't apply read-side filters — counts reflect
        # ALL rows in the table. The service code still issues the correct
        # PostgREST predicates against a real DB.
        assert "pending_therapists" in metrics
        assert "pending_clinics" in metrics
        assert "sessions_today" in metrics
        assert "total_revenue" in metrics
        assert "platform_fees" in metrics
        assert metrics["total_revenue"] == 200.0
        assert metrics["platform_fees"] == 20.0


@pytest.mark.asyncio
class TestSuspendEntity:
    async def test_suspend_therapist_sets_is_active_false(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "t1", "is_active": True, "is_approved": True},
        ])
        result = await admin_service.suspend_entity(
            entity_type="therapist",
            entity_id="t1",
            admin_id="admin-1",
            db=db,
        )
        assert result["is_active"] is False

    async def test_suspend_clinic_sets_is_active_false(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1", "is_active": True, "is_approved": True},
        ])
        result = await admin_service.suspend_entity(
            entity_type="clinic",
            entity_id="c1",
            admin_id="admin-1",
            db=db,
        )
        assert result["is_active"] is False

    async def test_suspend_invalid_type_raises(self):
        db = _client()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.suspend_entity(
                entity_type="widget",
                entity_id="x",
                admin_id="admin-1",
                db=db,
            )
        assert exc.value.status_code == 400

    async def test_suspend_nonexistent_raises_404(self):
        db = _client()
        db.set_table_data("therapist_profiles", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.suspend_entity(
                entity_type="therapist",
                entity_id="missing",
                admin_id="admin-1",
                db=db,
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Phase 3 — DTO mapper service tests
# ---------------------------------------------------------------------------


SAMPLE_CLINIC = {
    "id": "clinic-alpha",
    "name": "Clínica Alpha",
    "cnpj": "11111111000111",
    "responsible_person": "Maria",
    "contact_email": "alpha@x.com",
    "phone": "+5511999999999",
    "is_approved": True,
    "is_active": True,
    "approved_by": "admin-uid-001",
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-02T10:00:00Z",
}


@pytest.mark.asyncio
class TestListClinicsForAdmin:
    async def test_dto_shape(self):
        db = _client()
        db.set_table_data("clinics", [SAMPLE_CLINIC])
        data, total = await admin_service.list_clinics_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        row = data[0]
        # Load-bearing ``Clinica`` fields the page reads.
        assert row["id"] == "clinic-alpha"
        assert row["nome"] == "Clínica Alpha"
        assert row["cnpj"] == "11111111000111"
        assert row["status"] == "aprovada"
        assert "responsavel" in row
        assert "email" in row

    async def test_derives_pending_status(self):
        db = _client()
        db.set_table_data(
            "clinics",
            [{**SAMPLE_CLINIC, "is_approved": False, "is_active": True}],
        )
        data, _ = await admin_service.list_clinics_for_admin(
            db, page=1, page_size=20,
        )
        # Read-side predicates aren't applied by MockSupabase, so the row
        # comes through; the derived-status mapper still classifies it.
        assert data[0]["status"] == "pendente"

    async def test_rejeitada_filter_accepts_status(self):
        # Phase 5: empty-fallback hack removed after migration 013 added
        # the reject-audit columns. The filter now resolves via PostgREST
        # predicates (`is_approved=False AND rejection_reason IS NOT NULL`)
        # against the real DB. MockSupabase doesn't apply read-side
        # filters, so we confirm the route accepts the filter and the
        # mapper runs.
        db = _client()
        db.set_table_data("clinics", [SAMPLE_CLINIC])
        data, total = await admin_service.list_clinics_for_admin(
            db, page=1, page_size=20, status="rejeitada",
        )
        assert isinstance(data, list)
        assert isinstance(total, int)

    async def test_busca_filter_does_not_blow_up(self):
        db = _client()
        db.set_table_data("clinics", [SAMPLE_CLINIC])
        data, total = await admin_service.list_clinics_for_admin(
            db, page=1, page_size=20, busca="Alpha",
        )
        # ``or_`` ilike isn't applied by MockSupabase on reads — we
        # just verify the route accepts it and the mapper still runs.
        assert isinstance(data, list)


SAMPLE_PATIENT = {
    "user_id": "patient-001",
    "current_therapist_id": "therapist-001",
    "clinic_id": "clinic-alpha",
    "origin": "platform",
    "phone": "+5511988887777",
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-02T10:00:00Z",
}


@pytest.mark.asyncio
class TestListPatientsForAdmin:
    async def test_dto_shape(self):
        db = _client()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("appointments", [])
        data, total = await admin_service.list_patients_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        row = data[0]
        # ``AdminPatient`` DTO fields the page reads.
        assert row["id"] == "patient-001"
        assert "nome" in row
        assert "email" in row
        assert "terapeuta_nome" in row  # key MUST exist (even null)
        assert row["origin"] == "platform"
        assert row["session_count"] == 0

    async def test_session_count_aggregates_completed(self):
        db = _client()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data(
            "appointments",
            [
                {"patient_id": "patient-001", "status": "completed"},
                {"patient_id": "patient-001", "status": "completed"},
            ],
        )
        data, _ = await admin_service.list_patients_for_admin(
            db, page=1, page_size=20,
        )
        assert data[0]["session_count"] == 2

    async def test_empty_input(self):
        db = _client()
        db.set_table_data("patient_profiles", [])
        db.set_table_data("appointments", [])
        data, total = await admin_service.list_patients_for_admin(
            db, page=1, page_size=20,
        )
        assert data == []
        assert total == 0


SAMPLE_REPORT = {
    "id": "report-001",
    "conversation_id": "convo-001",
    "message_id": "msg-001",
    "reported_by_user_id": "reporter-uid",
    "reason": "Spam",
    "status": "pending",
    "created_at": "2026-04-30T10:00:00Z",
}


@pytest.mark.asyncio
class TestListReportsForAdmin:
    async def test_dto_shape_with_preview(self):
        db = _client()
        db.set_table_data("message_reports", [SAMPLE_REPORT])
        db.set_table_data(
            "messages",
            [
                {
                    "id": "msg-001",
                    "content": "Conteúdo da mensagem",
                    "message_type": "text",
                },
            ],
        )
        data, total = await admin_service.list_reports_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        row = data[0]
        assert row["id"] == "report-001"
        assert row["reason"] == "Spam"
        assert "reporter_name" in row
        assert row["reported_message_preview"]  # non-empty
        assert row["conversation_id"] == "convo-001"

    async def test_preview_falls_back_to_type_tag(self):
        db = _client()
        db.set_table_data("message_reports", [SAMPLE_REPORT])
        db.set_table_data(
            "messages",
            [{"id": "msg-001", "content": "", "message_type": "system"}],
        )
        data, _ = await admin_service.list_reports_for_admin(
            db, page=1, page_size=20,
        )
        assert data[0]["reported_message_preview"] == "[system]"


@pytest.mark.asyncio
class TestResolveReport:
    async def test_resolves_and_returns_row(self):
        db = _client()
        db.set_table_data("message_reports", [SAMPLE_REPORT])
        result = await admin_service.resolve_report(
            report_id="report-001",
            admin_id="admin-uid",
            resolution="Resolvido manualmente",
            db=db,
        )
        assert "id" in result

    async def test_not_found_raises_404(self):
        db = _client()
        db.set_table_data("message_reports", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.resolve_report(
                report_id="missing",
                admin_id="admin-uid",
                resolution="Anything",
                db=db,
            )
        assert exc.value.status_code == 404


SAMPLE_T_REVIEW = {
    "id": "review-t-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "clinic_id": None,
    "star_rating": 1,
    "review_text": "Comentário",
    "is_flagged": True,
    "is_hidden": False,
    "flagged_by_therapist_id": "therapist-001",
    "flagged_reason": "Difamação",
    "created_at": "2026-04-30T10:00:00Z",
    "updated_at": "2026-04-30T10:00:00Z",
}

SAMPLE_C_REVIEW = {
    "id": "review-c-001",
    "patient_id": "patient-002",
    "clinic_id": "clinic-alpha",
    "star_rating": 2,
    "review_text": "Comentário clínica",
    "is_flagged": True,
    "is_hidden": False,
    "flagged_by_clinic_admin_id": "clinic-admin",
    "flagged_reason": "Inválida",
    "created_at": "2026-04-29T10:00:00Z",
    "updated_at": "2026-04-29T10:00:00Z",
}


@pytest.mark.asyncio
class TestListFlaggedReviewsForAdmin:
    async def test_dto_shape_both_tables(self):
        db = _client()
        db.set_table_data("reviews", [SAMPLE_T_REVIEW])
        db.set_table_data("clinic_reviews", [SAMPLE_C_REVIEW])
        db.set_table_data(
            "clinics",
            [{"id": "clinic-alpha", "name": "Clínica Alpha"}],
        )
        data, total = await admin_service.list_flagged_reviews_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 2
        assert len(data) == 2
        types = {r["entity_type"] for r in data}
        assert types == {"therapist", "clinic"}
        for row in data:
            assert "nota" in row
            assert "comentario" in row
            assert "patient_name" in row
            assert "entity_name" in row

    async def test_filter_to_clinic_only(self):
        db = _client()
        db.set_table_data("reviews", [SAMPLE_T_REVIEW])
        db.set_table_data("clinic_reviews", [SAMPLE_C_REVIEW])
        db.set_table_data(
            "clinics",
            [{"id": "clinic-alpha", "name": "Clínica Alpha"}],
        )
        data, _ = await admin_service.list_flagged_reviews_for_admin(
            db, page=1, page_size=20, entity_type="clinic",
        )
        assert all(r["entity_type"] == "clinic" for r in data)


@pytest.mark.asyncio
class TestModerateReview:
    async def test_dismiss_therapist_review(self):
        db = _client()
        db.set_table_data("reviews", [SAMPLE_T_REVIEW])
        db.set_table_data("clinic_reviews", [])
        row = await admin_service.moderate_review(
            review_id="review-t-001",
            action="dismiss",
            admin_id="admin-uid",
            db=db,
        )
        assert row["id"] == "review-t-001"

    async def test_hide_falls_through_to_clinic_reviews(self):
        db = _client()
        db.set_table_data("reviews", [])
        db.set_table_data("clinic_reviews", [SAMPLE_C_REVIEW])
        row = await admin_service.moderate_review(
            review_id="review-c-001",
            action="hide",
            admin_id="admin-uid",
            db=db,
        )
        assert row["id"] == "review-c-001"

    async def test_invalid_action_raises_400(self):
        db = _client()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.moderate_review(
                review_id="x",
                action="bogus",
                admin_id="admin-uid",
                db=db,
            )
        assert exc.value.status_code == 400

    async def test_unknown_review_raises_404(self):
        db = _client()
        db.set_table_data("reviews", [])
        db.set_table_data("clinic_reviews", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.moderate_review(
                review_id="missing",
                action="dismiss",
                admin_id="admin-uid",
                db=db,
            )
        assert exc.value.status_code == 404


SAMPLE_BLOCK = {
    "id": "block-001",
    "blocker_user_id": "user-a",
    "blocked_user_id": "user-b",
    "created_at": "2026-04-30T10:00:00Z",
}


@pytest.mark.asyncio
class TestListBlocksForAdmin:
    async def test_dto_shape(self):
        db = _client()
        db.set_table_data("user_blocks", [SAMPLE_BLOCK])
        data, total = await admin_service.list_blocks_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        row = data[0]
        assert row["id"] == "block-001"
        assert "blocker_name" in row
        assert "blocked_name" in row
        assert row["created_at"] == "2026-04-30T10:00:00Z"

    async def test_empty(self):
        db = _client()
        db.set_table_data("user_blocks", [])
        data, total = await admin_service.list_blocks_for_admin(
            db, page=1, page_size=20,
        )
        assert data == []
        assert total == 0


SAMPLE_SUPPORT_CONV = {
    "id": "convo-support-001",
    "mode": "human",
    "last_message_at": "2026-04-01T10:00:00Z",
    "created_at": "2026-04-01T09:00:00Z",
    "last_message_preview": "Olá",
    "unread_count": 2,
    "is_muted": False,
}


@pytest.mark.asyncio
class TestListSupportConversationsForAdmin:
    async def test_dto_shape(self):
        db = _client()
        db.set_table_data("conversations", [SAMPLE_SUPPORT_CONV])
        db.set_table_data(
            "conversation_participants",
            [
                {
                    "conversation_id": "convo-support-001",
                    "participant_type": "platform_support",
                    "participant_id": None,
                    "clinic_id": None,
                },
                {
                    "conversation_id": "convo-support-001",
                    "participant_type": "user",
                    "participant_id": "patient-uid-1",
                    "clinic_id": None,
                },
            ],
        )
        data, total = await admin_service.list_support_conversations_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        row = data[0]
        assert row["id"] == "convo-support-001"
        assert row["is_support"] is True
        assert "other_participant_name" in row
        assert row["other_participant_type"] in ("user", "clinic", "platform_support")
        assert row["unread_count"] == 2

    async def test_empty_when_no_support_participants(self):
        db = _client()
        db.set_table_data("conversations", [])
        db.set_table_data("conversation_participants", [])
        data, total = await admin_service.list_support_conversations_for_admin(
            db, page=1, page_size=20,
        )
        assert data == []
        assert total == 0


# ---------------------------------------------------------------------------
# Phase 5 — Reject flow audit-column invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRejectEntityAuditColumns:
    """``reject_entity`` writes all three reject-audit columns from migration 013."""

    async def test_reject_therapist_writes_audit_triplet(self):
        db = _client()
        db.set_table_data(
            "therapist_profiles",
            [{"user_id": "t1", "is_approved": False, "is_active": True}],
        )
        await admin_service.reject_entity(
            entity_type="therapist",
            entity_id="t1",
            admin_id="admin-uid-007",
            reason="CRP inválido",
            db=db,
        )
        payloads = db.table("therapist_profiles").updated_payloads
        assert len(payloads) == 1
        payload = payloads[0]
        assert payload["is_approved"] is False
        assert payload["rejection_reason"] == "CRP inválido"
        assert payload["rejected_by"] == "admin-uid-007"
        # rejected_at is ISO-formatted UTC; we don't pin the exact string but
        # confirm it parses + is recent.
        rejected_at = payload["rejected_at"]
        assert isinstance(rejected_at, str)
        parsed = datetime.fromisoformat(rejected_at)
        delta = datetime.now(timezone.utc) - parsed
        assert delta.total_seconds() < 5

    async def test_reject_clinic_writes_audit_triplet(self):
        db = _client()
        db.set_table_data(
            "clinics",
            [{"id": "c1", "is_approved": False, "is_active": True}],
        )
        await admin_service.reject_entity(
            entity_type="clinic",
            entity_id="c1",
            admin_id="admin-uid-007",
            reason="CNPJ inválido",
            db=db,
        )
        payloads = db.table("clinics").updated_payloads
        assert len(payloads) == 1
        payload = payloads[0]
        assert payload["is_approved"] is False
        assert payload["rejection_reason"] == "CNPJ inválido"
        assert payload["rejected_by"] == "admin-uid-007"
        assert isinstance(payload["rejected_at"], str)

    async def test_reject_idempotent_overwrites_reason(self):
        db = _client()
        db.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "old reason",
                    "rejected_by": "admin-uid-prev",
                }
            ],
        )
        await admin_service.reject_entity(
            entity_type="therapist",
            entity_id="t1",
            admin_id="admin-uid-new",
            reason="new reason",
            db=db,
        )
        payloads = db.table("therapist_profiles").updated_payloads
        # Latest reject wins: reason + actor on the live row reflect the
        # most recent call; chain lives in application logs.
        assert payloads[-1]["rejection_reason"] == "new reason"
        assert payloads[-1]["rejected_by"] == "admin-uid-new"


@pytest.mark.asyncio
class TestApproveEntityClearsAudit:
    """``approve_entity`` clears the reject-audit triplet on re-approval."""

    async def test_re_approve_therapist_clears_audit(self):
        db = _client()
        db.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "needs documentation",
                    "rejected_at": "2026-05-10T10:00:00+00:00",
                    "rejected_by": "admin-uid-prev",
                }
            ],
        )
        await admin_service.approve_entity(
            entity_type="therapist",
            entity_id="t1",
            admin_id="admin-uid-new",
            db=db,
        )
        payload = db.table("therapist_profiles").updated_payloads[0]
        assert payload["is_approved"] is True
        assert payload["is_active"] is True
        assert payload["rejection_reason"] is None
        assert payload["rejected_at"] is None
        assert payload["rejected_by"] is None

    async def test_re_approve_clinic_clears_audit(self):
        db = _client()
        db.set_table_data(
            "clinics",
            [
                {
                    "id": "c1",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "needs CNPJ verification",
                    "rejected_at": "2026-05-10T10:00:00+00:00",
                    "rejected_by": "admin-uid-prev",
                }
            ],
        )
        await admin_service.approve_entity(
            entity_type="clinic",
            entity_id="c1",
            admin_id="admin-uid-new",
            db=db,
        )
        payload = db.table("clinics").updated_payloads[0]
        assert payload["is_approved"] is True
        assert payload["is_active"] is True
        assert payload["rejection_reason"] is None
        assert payload["rejected_at"] is None
        assert payload["rejected_by"] is None


@pytest.mark.asyncio
class TestGetTherapistForAdmin:
    """Phase 5 admin detail endpoint — single-therapist DTO."""

    async def test_returns_dto_shape(self):
        db = _client()
        db.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "crp": "06/123",
                    "is_approved": True,
                    "is_active": True,
                }
            ],
        )
        dto = await admin_service.get_therapist_for_admin(db, "t1")
        assert dto["id"] == "t1"
        assert dto["user_id"] == "t1"
        assert dto["status"] == "aprovado"
        # Reject-audit triplet is always present (None when not rejected).
        assert dto["rejection_reason"] is None
        assert dto["rejected_at"] is None
        assert dto["rejected_by"] is None
        assert dto["rejected_by_name"] is None

    async def test_returns_audit_fields_when_rejected(self):
        db = _client()
        db.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "needs docs",
                    "rejected_at": "2026-05-11T10:00:00+00:00",
                    "rejected_by": "admin-uid-007",
                }
            ],
        )
        dto = await admin_service.get_therapist_for_admin(db, "t1")
        assert dto["status"] == "rejeitado"
        assert dto["rejection_reason"] == "needs docs"
        assert dto["rejected_at"] == "2026-05-11T10:00:00+00:00"
        assert dto["rejected_by"] == "admin-uid-007"
        # rejected_by_name resolves to display_name (falls back to
        # "Usuário" via UserIdentity.display_name when the mock auth
        # can't resolve the admin's nome).
        assert "rejected_by_name" in dto

    async def test_404_when_not_found(self):
        db = _client()
        db.set_table_data("therapist_profiles", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.get_therapist_for_admin(db, "missing")
        assert exc.value.status_code == 404


@pytest.mark.asyncio
class TestGetClinicForAdmin:
    """Phase 5 admin detail endpoint — single-clinic DTO."""

    async def test_returns_dto_shape(self):
        db = _client()
        db.set_table_data(
            "clinics",
            [
                {
                    "id": "c1",
                    "name": "Clínica X",
                    "is_approved": True,
                    "is_active": True,
                }
            ],
        )
        dto = await admin_service.get_clinic_for_admin(db, "c1")
        assert dto["id"] == "c1"
        assert dto["nome"] == "Clínica X"
        assert dto["status"] == "aprovada"
        assert dto["rejection_reason"] is None
        assert dto["rejected_at"] is None
        assert dto["rejected_by"] is None
        assert dto["rejected_by_name"] is None

    async def test_returns_audit_fields_when_rejected(self):
        db = _client()
        db.set_table_data(
            "clinics",
            [
                {
                    "id": "c1",
                    "name": "Clínica X",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "CNPJ inválido",
                    "rejected_at": "2026-05-11T10:00:00+00:00",
                    "rejected_by": "admin-uid-007",
                }
            ],
        )
        dto = await admin_service.get_clinic_for_admin(db, "c1")
        assert dto["status"] == "rejeitada"
        assert dto["rejection_reason"] == "CNPJ inválido"
        assert dto["rejected_at"] == "2026-05-11T10:00:00+00:00"
        assert dto["rejected_by"] == "admin-uid-007"

    async def test_404_when_not_found(self):
        db = _client()
        db.set_table_data("clinics", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.get_clinic_for_admin(db, "missing")
        assert exc.value.status_code == 404
