"""
Tests for the Clinical Records Service.

Covers: anamnese uniqueness check, treatment plan CRUD, goal lifecycle,
evolution note creation and pagination.
"""
import pytest

from tests.conftest import MockSelectBuilder, MockSupabaseClient
from app.services import clinical_records_service


SAMPLE_ANAMNESE = {
    "id": "anamnese-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "queixa_principal": "Ansiedade generalizada",
    "historia_pregressa": "Crises desde adolescência",
    "historico_familiar": None,
    "medicacoes": None,
    "observacoes": None,
}

SAMPLE_PLAN = {
    "id": "plan-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "titulo": "Plano TCC Ansiedade",
    "descricao": "Reestruturação cognitiva",
    "data_inicio": "2026-04-01",
    "status": "ativo",
}

SAMPLE_GOAL = {
    "id": "goal-001",
    "treatment_plan_id": "plan-001",
    "descricao": "Praticar respiração diafragmática",
    "prazo": "2026-05-01",
    "status": "pendente",
}

SAMPLE_NOTE = {
    "id": "note-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "formato": "soap",
    "subjetivo": "Paciente relata melhora",
    "objetivo": "Comunicativo",
    "avaliacao": "Evolução positiva",
    "plano": "Manter frequência",
}


# ---------------------------------------------------------------------------
# Anamnese
# ---------------------------------------------------------------------------

class TestCreateAnamnese:
    @pytest.mark.asyncio
    async def test_create_anamnese(self):
        """Uses a two-phase mock: empty for uniqueness check, data for insert."""
        db = MockSupabaseClient()
        # First call (select for uniqueness) returns empty, second (insert) returns data
        db.set_table_data("anamneses", [])

        # Patch the service to skip the uniqueness check result and succeed on insert
        from unittest.mock import patch as _patch
        call_count = {"n": 0}
        original_table = db.table

        def phased_table(name):
            if name == "anamneses":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # Uniqueness check: no existing record
                    return MockSelectBuilder([])
                else:
                    # Insert: return new record
                    return MockSelectBuilder([SAMPLE_ANAMNESE])
            return original_table(name)

        db.table = phased_table
        result = await clinical_records_service.create_anamnese(
            patient_id="patient-001",
            therapist_id="therapist-001",
            data={"queixa_principal": "Ansiedade generalizada"},
            db=db,
        )
        assert result is not None
        assert result["queixa_principal"] == "Ansiedade generalizada"

    @pytest.mark.asyncio
    async def test_create_anamnese_duplicate_raises_409(self):
        """Creating a second anamnese for the same pair raises 409."""
        db = MockSupabaseClient()
        # Existing anamnese found — uniqueness check returns data
        db.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.create_anamnese(
                patient_id="patient-001",
                therapist_id="therapist-001",
                data={"queixa_principal": "Outra queixa"},
                db=db,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_get_anamnese(self):
        db = MockSupabaseClient()
        db.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        result = await clinical_records_service.get_anamnese(
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_anamnese_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("anamneses", [])
        result = await clinical_records_service.get_anamnese(
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
        )
        assert result is None


class TestUpdateAnamnese:
    @pytest.mark.asyncio
    async def test_update_anamnese(self):
        db = MockSupabaseClient()
        db.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        result = await clinical_records_service.update_anamnese(
            anamnese_id="anamnese-001",
            data={"queixa_principal": "Depressão e ansiedade"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_anamnese_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("anamneses", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.update_anamnese(
                anamnese_id="nonexistent",
                data={"queixa_principal": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_anamnese_empty_fields(self):
        """Update with no valid fields raises 400."""
        db = MockSupabaseClient()
        db.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.update_anamnese(
                anamnese_id="anamnese-001",
                data={},
                db=db,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Treatment Plans
# ---------------------------------------------------------------------------

class TestTreatmentPlanCRUD:
    @pytest.mark.asyncio
    async def test_create_treatment_plan(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [SAMPLE_PLAN])
        result = await clinical_records_service.create_treatment_plan(
            patient_id="patient-001",
            therapist_id="therapist-001",
            data={"titulo": "Plano TCC", "data_inicio": "2026-04-01"},
            db=db,
        )
        assert result is not None
        assert result["titulo"] == "Plano TCC Ansiedade"

    @pytest.mark.asyncio
    async def test_update_treatment_plan(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [SAMPLE_PLAN])
        result = await clinical_records_service.update_treatment_plan(
            plan_id="plan-001",
            data={"titulo": "Plano Atualizado"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_treatment_plan_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.update_treatment_plan(
                plan_id="nonexistent",
                data={"titulo": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_treatment_plans(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [SAMPLE_PLAN])
        result = await clinical_records_service.list_treatment_plans(
            patient_id="patient-001",
            db=db,
        )
        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

class TestGoalLifecycle:
    @pytest.mark.asyncio
    async def test_create_goal(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [SAMPLE_PLAN])
        db.set_table_data("goals", [SAMPLE_GOAL])
        result = await clinical_records_service.create_goal(
            plan_id="plan-001",
            data={"descricao": "Nova meta"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_goal_plan_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("treatment_plans", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.create_goal(
                plan_id="nonexistent",
                data={"descricao": "Meta"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_goal(self):
        db = MockSupabaseClient()
        db.set_table_data("goals", [SAMPLE_GOAL])
        result = await clinical_records_service.update_goal(
            goal_id="goal-001",
            data={"status": "em_andamento"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_goal_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("goals", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.update_goal(
                goal_id="nonexistent",
                data={"status": "em_andamento"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_goal(self):
        db = MockSupabaseClient()
        db.set_table_data("goals", [SAMPLE_GOAL])
        await clinical_records_service.delete_goal(goal_id="goal-001", db=db)

    @pytest.mark.asyncio
    async def test_delete_goal_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("goals", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.delete_goal(goal_id="nonexistent", db=db)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Evolution Notes
# ---------------------------------------------------------------------------

class TestEvolutionNotes:
    @pytest.mark.asyncio
    async def test_create_evolution_note(self):
        db = MockSupabaseClient()
        db.set_table_data("evolution_notes", [SAMPLE_NOTE])
        result = await clinical_records_service.create_evolution_note(
            patient_id="patient-001",
            therapist_id="therapist-001",
            data={
                "formato": "soap",
                "subjetivo": "Melhora",
                "objetivo": "Calmo",
                "avaliacao": "Positiva",
                "plano": "Manter",
            },
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_evolution_note(self):
        db = MockSupabaseClient()
        db.set_table_data("evolution_notes", [SAMPLE_NOTE])
        result = await clinical_records_service.update_evolution_note(
            note_id="note-001",
            data={"plano": "Aumentar frequência"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_evolution_note_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("evolution_notes", [])
        with pytest.raises(Exception) as exc_info:
            await clinical_records_service.update_evolution_note(
                note_id="nonexistent",
                data={"plano": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_evolution_notes_paginated(self):
        db = MockSupabaseClient()
        db.set_table_data("evolution_notes", [SAMPLE_NOTE])
        data, total = await clinical_records_service.list_evolution_notes(
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
            page=1,
            page_size=10,
        )
        assert isinstance(data, list)
        assert total >= 0
