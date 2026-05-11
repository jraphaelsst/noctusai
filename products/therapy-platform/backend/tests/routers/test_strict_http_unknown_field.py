"""Regression test — StrictHttpModel rejects unknown request keys with 422.

Closes the silent-drop bug-class (memory `feedback_pydantic_silent_drop_kills_writes`):
pre-migration, an unknown field on `AppointmentCreate` was silently dropped by
Pydantic's `extra="ignore"` default. Post-migration, `noctusai_lib.api.StrictHttpModel`
inherits `extra="forbid"`, so the request returns **422 Unprocessable Entity** with
a detail body that names the offending location.

`/api/appointments` is the original representative HTTP-boundary route. The
extended test class below covers the **dict-body-typing migration wave**
(`projects/therapy-dict-body-typing/PROJECT.md` 2026-05-11) — 22 routes
across 10 therapy routers swapped `body: dict` for a `StrictHttpModel`
subclass, and every route ships a regression test pinning the
unknown-field 422.

Pattern: each test sends a complete + valid payload PLUS one extra
`definitely_not_a_field` key. Pydantic short-circuits at the boundary so
no DB seeding is needed — the 422 fires before any service call. The
assertion checks both the status code AND the detail body to defend
against the false-green slip the YouTube Crawler audit surfaced
(`feedback_status_code_assertion_rule`).
"""
from __future__ import annotations


def _assert_422_with_unknown_field(resp, field_name: str = "definitely_not_a_field") -> None:
    """Shared assertion — 422 status + offending key surfaced in detail body.

    Defends against the YouTube-Crawler false-green slip
    (`feedback_status_code_assertion_rule`): every body assertion is
    paired with a status-code assertion.
    """
    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail_str = str(body.get("detail", body))
    assert field_name in detail_str


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


class TestDictBodyTypingUnknownFieldRejected:
    """Regression tests for the 22 routes typed in the dict-body-typing wave.

    One test per route. Each sends a complete valid payload PLUS a
    `definitely_not_a_field` key — Pydantic 422 short-circuits before
    any auth / DB code runs, so no fixture seeding is required.
    """

    # --- anamnese.py (2 routes) ---

    def test_create_anamnese_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/anamnese",
            json={
                "patient_id": "patient-001",
                "queixa_principal": "Ansiedade",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_anamnese_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/anamnese/anamnese-001",
            json={
                "medicacoes": "Sertralina 50mg",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- crisis.py (1 route) ---

    def test_review_crisis_alert_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/crisis-alerts/alert-001/review",
            json={
                "status": "revisado",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- evolution_notes.py (2 routes) ---

    def test_create_evolution_note_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/evolution-notes",
            json={
                "patient_id": "patient-001",
                "formato": "soap",
                "subjetivo": "Paciente relata melhora",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_evolution_note_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/evolution-notes/note-001",
            json={
                "subjetivo": "Atualização",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- homework.py (3 routes) ---

    def test_assign_homework_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/homework",
            json={
                "patient_id": "patient-001",
                "titulo": "Registro de pensamentos",
                "descricao": "Anotar 3 pensamentos automáticos por dia",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_submit_homework_rejects_unknown_field_with_422(self, patient_client):
        resp = patient_client.post(
            "/api/homework/hw-001/submit",
            json={
                "resposta_paciente": "Consegui registrar os pensamentos.",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_review_homework_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/homework/hw-001/review",
            json={
                "feedback_terapeuta": "Excelente trabalho!",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- invoices.py (1 route) ---

    def test_generate_invoice_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/invoices",
            json={
                "transaction_id": "tx-001",
                "patient_id": "patient-001",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- mood.py (1 route) ---

    def test_create_mood_entry_rejects_unknown_field_with_422(self, patient_client):
        resp = patient_client.post(
            "/api/mood",
            json={
                "rating": 7,
                "emocoes": ["calma"],
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- rooms.py (3 routes) ---

    def test_create_room_rejects_unknown_field_with_422(self, clinic_admin_client):
        resp = clinic_admin_client.post(
            "/api/rooms",
            json={
                "nome": "Sala 1",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_room_rejects_unknown_field_with_422(self, clinic_admin_client):
        resp = clinic_admin_client.patch(
            "/api/rooms/room-001",
            json={
                "nome": "Sala 1 - Renomeada",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_create_booking_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/rooms/bookings",
            json={
                "room_id": "room-001",
                "appointment_id": "appt-001",
                "data": "2026-04-10",
                "horario_inicio": "09:00",
                "horario_fim": "10:00",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- therapeutic_journal.py (2 routes) ---

    def test_create_journal_entry_rejects_unknown_field_with_422(self, patient_client):
        resp = patient_client.post(
            "/api/diary",
            json={
                "conteudo": "Reflexão do dia",
                "titulo": "Hoje",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_journal_entry_rejects_unknown_field_with_422(self, patient_client):
        resp = patient_client.patch(
            "/api/diary/journal-001",
            json={
                "conteudo": "Reflexão atualizada",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- treatment_plans.py (4 routes) ---

    def test_create_treatment_plan_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/treatment-plans",
            json={
                "patient_id": "patient-001",
                "titulo": "Plano para manejo de ansiedade",
                "data_inicio": "2026-04-01",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_treatment_plan_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/treatment-plans/plan-001",
            json={
                "titulo": "Plano renomeado",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_add_goal_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/treatment-plans/plan-001/metas",
            json={
                "descricao": "Reduzir crises a 1/semana",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_update_goal_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/treatment-plans/metas/goal-001",
            json={
                "status": "em_andamento",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    # --- whatsapp_therapy.py (3 routes) ---

    def test_send_whatsapp_message_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/whatsapp/enviar",
            json={
                "patient_id": "patient-001",
                "message": "Olá",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_send_whatsapp_reminder_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/whatsapp/lembrete",
            json={
                "appointment_id": "appt-001",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)

    def test_configure_whatsapp_reminders_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/whatsapp/configurar-lembretes",
            json={
                "antecedencia_horas": 24,
                "is_active": True,
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_with_unknown_field(resp)
