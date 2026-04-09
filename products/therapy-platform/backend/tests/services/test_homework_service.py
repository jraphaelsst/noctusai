"""
Tests for the Homework Service.

Covers: assignment workflow (assign -> submit -> review),
invalid status transitions, listing by role.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import homework_service


SAMPLE_ASSIGNMENT = {
    "id": "hw-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "titulo": "Registro de pensamentos",
    "descricao": "Anotar 3 pensamentos automáticos por dia",
    "data_limite": "2026-04-15",
    "status": "pendente",
}


class TestAssign:
    @pytest.mark.asyncio
    async def test_assign_homework(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.assign(
            therapist_id="therapist-001",
            data={
                "patient_id": "patient-001",
                "titulo": "Registro de pensamentos",
                "descricao": "Anotar 3 pensamentos automáticos",
            },
            db=db,
        )
        assert result is not None
        assert result["status"] == "pendente"

    @pytest.mark.asyncio
    async def test_assign_with_deadline(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.assign(
            therapist_id="therapist-001",
            data={
                "patient_id": "patient-001",
                "titulo": "Tarefa",
                "descricao": "Descrição",
                "data_limite": "2026-04-15",
            },
            db=db,
        )
        assert result is not None


class TestSubmit:
    @pytest.mark.asyncio
    async def test_submit_homework(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.submit(
            assignment_id="hw-001",
            data={"resposta_paciente": "Consegui registrar os pensamentos."},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_submit_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [])
        with pytest.raises(Exception) as exc_info:
            await homework_service.submit(
                assignment_id="nonexistent",
                data={"resposta_paciente": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_already_reviewed(self):
        """Cannot submit homework that was already reviewed."""
        db = MockSupabaseClient()
        reviewed = {**SAMPLE_ASSIGNMENT, "status": "revisado"}
        db.set_table_data("homework_assignments", [reviewed])
        with pytest.raises(Exception) as exc_info:
            await homework_service.submit(
                assignment_id="hw-001",
                data={"resposta_paciente": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestReview:
    @pytest.mark.asyncio
    async def test_review_completed_homework(self):
        db = MockSupabaseClient()
        completed = {**SAMPLE_ASSIGNMENT, "status": "concluido"}
        db.set_table_data("homework_assignments", [completed])
        result = await homework_service.review(
            assignment_id="hw-001",
            data={"feedback_terapeuta": "Excelente trabalho!"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_review_in_progress_homework(self):
        """Can review homework that is em_andamento."""
        db = MockSupabaseClient()
        in_progress = {**SAMPLE_ASSIGNMENT, "status": "em_andamento"}
        db.set_table_data("homework_assignments", [in_progress])
        result = await homework_service.review(
            assignment_id="hw-001",
            data={"feedback_terapeuta": "Continue assim"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_review_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [])
        with pytest.raises(Exception) as exc_info:
            await homework_service.review(
                assignment_id="nonexistent",
                data={"feedback_terapeuta": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_review_pending_homework_fails(self):
        """Cannot review homework that is still pendente."""
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])  # status: pendente
        with pytest.raises(Exception) as exc_info:
            await homework_service.review(
                assignment_id="hw-001",
                data={"feedback_terapeuta": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestListHomework:
    @pytest.mark.asyncio
    async def test_list_for_patient(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.list_for_patient(
            patient_id="patient-001",
            db=db,
        )
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_for_patient_with_status_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.list_for_patient(
            patient_id="patient-001",
            db=db,
            status_filter="pendente",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_for_therapist(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.list_for_therapist(
            therapist_id="therapist-001",
            db=db,
        )
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_for_therapist_with_status_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("homework_assignments", [SAMPLE_ASSIGNMENT])
        result = await homework_service.list_for_therapist(
            therapist_id="therapist-001",
            db=db,
            status_filter="concluido",
        )
        assert isinstance(result, list)
