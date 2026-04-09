"""
Tests for the Therapy Embedding Service.

Covers: text building (therapist/patient), embedding generation (mock OpenAI),
profile embedding workflows.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import MockSupabaseClient
from app.services import therapy_embedding_service


SAMPLE_THERAPIST_PROFILE = {
    "user_id": "therapist-001",
    "specialties": ["ansiedade", "depressão", "TEPT"],
    "approaches": ["TCC", "EMDR"],
    "bio": "Psicóloga clínica com 10 anos de experiência",
    "avg_rating": 4.8,
    "session_duration_minutes": 50,
    "default_session_price": 250.00,
    "accepts_convenio": True,
    "online_available": True,
    "in_person_available": False,
}

SAMPLE_PATIENT_PROFILE = {
    "user_id": "patient-001",
    "therapy_needs": "Ansiedade e ataques de pânico",
    "preferred_approaches": ["TCC"],
    "preferred_specialties": ["ansiedade"],
    "max_budget": 300,
    "prefers_online": True,
    "observacoes": "Prefere sessões no período da manhã",
}

MOCK_EMBEDDING = [0.1] * 1536


# ---------------------------------------------------------------------------
# Text Builders
# ---------------------------------------------------------------------------

class TestBuildTherapistText:
    def test_full_profile(self):
        text = therapy_embedding_service.build_therapist_text(SAMPLE_THERAPIST_PROFILE)
        assert "Especialidades: ansiedade, depressão, TEPT" in text
        assert "Abordagens: TCC, EMDR" in text
        assert "Bio:" in text
        assert "Avaliação média: 4.8" in text
        assert "Duração da sessão: 50 min" in text
        assert "Preço da sessão: R$ 250.0" in text
        assert "Aceita convênio" in text
        assert "Atendimento online disponível" in text

    def test_minimal_profile(self):
        text = therapy_embedding_service.build_therapist_text({})
        assert text == ""

    def test_partial_profile(self):
        text = therapy_embedding_service.build_therapist_text({
            "specialties": ["ansiedade"],
        })
        assert "Especialidades: ansiedade" in text

    def test_in_person_available(self):
        profile = {"in_person_available": True}
        text = therapy_embedding_service.build_therapist_text(profile)
        assert "Atendimento presencial disponível" in text


class TestBuildPatientText:
    def test_full_profile(self):
        text = therapy_embedding_service.build_patient_text(SAMPLE_PATIENT_PROFILE)
        assert "Necessidades: Ansiedade e ataques de pânico" in text
        assert "Abordagens preferidas: TCC" in text
        assert "Especialidades desejadas: ansiedade" in text
        assert "Orçamento máximo: R$ 300" in text
        assert "Prefere atendimento online" in text
        assert "Observações:" in text

    def test_minimal_profile(self):
        text = therapy_embedding_service.build_patient_text({})
        assert text == ""

    def test_prefers_in_person(self):
        profile = {"prefers_in_person": True}
        text = therapy_embedding_service.build_patient_text(profile)
        assert "Prefere atendimento presencial" in text

    def test_queixa_principal_fallback(self):
        """therapy_needs falls back to queixa_principal."""
        profile = {"queixa_principal": "Depressão"}
        text = therapy_embedding_service.build_patient_text(profile)
        assert "Necessidades: Depressão" in text


# ---------------------------------------------------------------------------
# Embedding Generation
# ---------------------------------------------------------------------------

class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_generate_embedding_success(self):
        """Mock OpenAI API to return embedding."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": MOCK_EMBEDDING}],
        }

        with patch("app.services.therapy_embedding_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await therapy_embedding_service.generate_embedding(
                text="Test text",
                api_key="test-key",
            )
            assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_generate_embedding_api_error(self):
        """API error raises ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("app.services.therapy_embedding_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with pytest.raises(ValueError, match="Erro na API OpenAI"):
                await therapy_embedding_service.generate_embedding(
                    text="Test",
                    api_key="test-key",
                )


# ---------------------------------------------------------------------------
# Profile Embedding Workflows
# ---------------------------------------------------------------------------

class TestEmbedTherapist:
    @pytest.mark.asyncio
    async def test_embed_therapist_no_api_key(self):
        db = MockSupabaseClient()
        with pytest.raises(ValueError, match="OpenAI API Key"):
            await therapy_embedding_service.embed_therapist(
                therapist_id="therapist-001",
                db=db,
                api_key=None,
            )

    @pytest.mark.asyncio
    async def test_embed_therapist_profile_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("therapist_profiles", [])
        result = await therapy_embedding_service.embed_therapist(
            therapist_id="nonexistent",
            db=db,
            api_key="test-key",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_therapist_empty_text(self):
        db = MockSupabaseClient()
        db.set_table_data("therapist_profiles", [{"user_id": "therapist-001"}])
        result = await therapy_embedding_service.embed_therapist(
            therapist_id="therapist-001",
            db=db,
            api_key="test-key",
        )
        assert result is False


class TestEmbedPatient:
    @pytest.mark.asyncio
    async def test_embed_patient_no_api_key(self):
        db = MockSupabaseClient()
        with pytest.raises(ValueError, match="OpenAI API Key"):
            await therapy_embedding_service.embed_patient(
                patient_id="patient-001",
                db=db,
                api_key=None,
            )

    @pytest.mark.asyncio
    async def test_embed_patient_profile_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [])
        result = await therapy_embedding_service.embed_patient(
            patient_id="nonexistent",
            db=db,
            api_key="test-key",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_patient_empty_text(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [{"user_id": "patient-001"}])
        result = await therapy_embedding_service.embed_patient(
            patient_id="patient-001",
            db=db,
            api_key="test-key",
        )
        assert result is False
