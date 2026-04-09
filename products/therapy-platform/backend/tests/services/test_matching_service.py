"""
Tests for the Matching Service.

Covers: composite scoring, individual scoring components,
find_matches, get_match_details, cosine similarity.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import matching_service


SAMPLE_PATIENT = {
    "user_id": "patient-001",
    "preferred_specialties": ["ansiedade", "depressão"],
    "preferred_approaches": ["TCC", "EMDR"],
    "max_budget": 300,
    "preferred_days": ["segunda", "quarta", "sexta"],
    "embedding": [0.1] * 10,
}

SAMPLE_THERAPIST_1 = {
    "user_id": "therapist-001",
    "nome": "Dra. Maria",
    "specialties": ["ansiedade", "depressão", "TEPT"],
    "approaches": ["TCC", "EMDR", "Psicodinâmica"],
    "default_session_price": 250,
    "availability_days": ["segunda", "terça", "quarta"],
    "is_active": True,
    "embedding": [0.1] * 10,
}

SAMPLE_THERAPIST_2 = {
    "user_id": "therapist-002",
    "nome": "Dr. João",
    "specialties": ["fobias"],
    "approaches": ["Psicanálise"],
    "default_session_price": 500,
    "availability_days": ["sábado"],
    "is_active": True,
    "embedding": [0.9] * 10,
}


# ---------------------------------------------------------------------------
# Cosine Similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        sim = matching_service._cosine_similarity(v, v)
        assert abs(sim - 1.0) < 0.0001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = matching_service._cosine_similarity(a, b)
        assert abs(sim) < 0.0001

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        sim = matching_service._cosine_similarity(a, b)
        assert sim == 0.0

    def test_similar_vectors(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 1.0, 0.1]
        sim = matching_service._cosine_similarity(a, b)
        assert sim > 0.9


# ---------------------------------------------------------------------------
# Individual Scoring Components
# ---------------------------------------------------------------------------

class TestSpecialtyOverlap:
    def test_full_overlap(self):
        patient = {"preferred_specialties": ["ansiedade", "depressão"]}
        therapist = {"specialties": ["ansiedade", "depressão", "TEPT"]}
        score = matching_service._score_specialty_overlap(patient, therapist)
        assert score == 1.0

    def test_partial_overlap(self):
        patient = {"preferred_specialties": ["ansiedade", "depressão"]}
        therapist = {"specialties": ["ansiedade"]}
        score = matching_service._score_specialty_overlap(patient, therapist)
        assert score == 0.5

    def test_no_overlap(self):
        patient = {"preferred_specialties": ["ansiedade"]}
        therapist = {"specialties": ["fobias"]}
        score = matching_service._score_specialty_overlap(patient, therapist)
        assert score == 0.0

    def test_no_preference(self):
        patient = {"preferred_specialties": []}
        therapist = {"specialties": ["ansiedade"]}
        score = matching_service._score_specialty_overlap(patient, therapist)
        assert score == 0.5  # Neutral


class TestApproachCompatibility:
    def test_full_overlap(self):
        patient = {"preferred_approaches": ["TCC"]}
        therapist = {"approaches": ["TCC", "EMDR"]}
        score = matching_service._score_approach_compatibility(patient, therapist)
        assert score == 1.0

    def test_no_overlap(self):
        patient = {"preferred_approaches": ["TCC"]}
        therapist = {"approaches": ["Psicanálise"]}
        score = matching_service._score_approach_compatibility(patient, therapist)
        assert score == 0.0


class TestPriceRange:
    def test_within_budget(self):
        patient = {"max_budget": 300}
        therapist = {"default_session_price": 250}
        score = matching_service._score_price_range(patient, therapist)
        assert score == 1.0

    def test_exact_budget(self):
        patient = {"max_budget": 250}
        therapist = {"default_session_price": 250}
        score = matching_service._score_price_range(patient, therapist)
        assert score == 1.0

    def test_slightly_over_budget(self):
        """Up to 20% over budget gives partial score."""
        patient = {"max_budget": 250}
        therapist = {"default_session_price": 280}
        score = matching_service._score_price_range(patient, therapist)
        assert score == 0.5

    def test_way_over_budget(self):
        patient = {"max_budget": 200}
        therapist = {"default_session_price": 500}
        score = matching_service._score_price_range(patient, therapist)
        assert score == 0.0

    def test_no_budget_specified(self):
        patient = {"max_budget": 0}
        therapist = {"default_session_price": 250}
        score = matching_service._score_price_range(patient, therapist)
        assert score == 0.5  # Neutral


class TestAvailabilityOverlap:
    def test_full_overlap(self):
        patient = {"preferred_days": ["segunda", "quarta"]}
        therapist = {"availability_days": ["segunda", "quarta", "sexta"]}
        score = matching_service._score_availability_overlap(patient, therapist)
        assert score == 1.0

    def test_partial_overlap(self):
        patient = {"preferred_days": ["segunda", "quarta", "sexta"]}
        therapist = {"availability_days": ["segunda"]}
        score = matching_service._score_availability_overlap(patient, therapist)
        assert abs(score - 1 / 3) < 0.01

    def test_no_overlap(self):
        patient = {"preferred_days": ["segunda"]}
        therapist = {"availability_days": ["sábado"]}
        score = matching_service._score_availability_overlap(patient, therapist)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_perfect_scores(self):
        score = matching_service._compute_composite_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score == 1.0

    def test_zero_scores(self):
        score = matching_service._compute_composite_score(0.0, 0.0, 0.0, 0.0, 0.0)
        assert score == 0.0

    def test_weight_distribution(self):
        """Embedding has 40% weight, specialty 20%, approach 15%, price 15%, availability 10%."""
        score = matching_service._compute_composite_score(1.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(score - 0.4) < 0.001

    def test_clamp_to_bounds(self):
        score = matching_service._compute_composite_score(1.5, 1.5, 1.5, 1.5, 1.5)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# find_matches
# ---------------------------------------------------------------------------

class TestFindMatches:
    @pytest.mark.asyncio
    async def test_find_matches(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("therapist_profiles", [SAMPLE_THERAPIST_1, SAMPLE_THERAPIST_2])
        matches = await matching_service.find_matches(
            patient_id="patient-001",
            db=db,
            threshold=0.0,
        )
        assert isinstance(matches, list)
        assert len(matches) >= 1
        # Matches should be sorted by score descending
        if len(matches) > 1:
            assert matches[0]["score"] >= matches[1]["score"]

    @pytest.mark.asyncio
    async def test_find_matches_no_patient_profile(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [])
        db.set_table_data("therapist_profiles", [SAMPLE_THERAPIST_1])
        matches = await matching_service.find_matches(
            patient_id="nonexistent",
            db=db,
        )
        assert matches == []

    @pytest.mark.asyncio
    async def test_find_matches_no_therapists(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("therapist_profiles", [])
        matches = await matching_service.find_matches(
            patient_id="patient-001",
            db=db,
        )
        assert matches == []

    @pytest.mark.asyncio
    async def test_find_matches_respects_limit(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("therapist_profiles", [SAMPLE_THERAPIST_1, SAMPLE_THERAPIST_2])
        matches = await matching_service.find_matches(
            patient_id="patient-001",
            db=db,
            limit=1,
            threshold=0.0,
        )
        assert len(matches) <= 1


# ---------------------------------------------------------------------------
# get_match_details
# ---------------------------------------------------------------------------

class TestGetMatchDetails:
    @pytest.mark.asyncio
    async def test_get_match_details(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("therapist_profiles", [SAMPLE_THERAPIST_1])
        details = await matching_service.get_match_details(
            therapist_id="therapist-001",
            patient_id="patient-001",
            db=db,
        )
        assert details is not None
        assert "score" in details
        assert "breakdown" in details
        assert "justificativa" in details

    @pytest.mark.asyncio
    async def test_get_match_details_no_patient(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [])
        db.set_table_data("therapist_profiles", [SAMPLE_THERAPIST_1])
        details = await matching_service.get_match_details(
            therapist_id="therapist-001",
            patient_id="nonexistent",
            db=db,
        )
        assert details is None

    @pytest.mark.asyncio
    async def test_get_match_details_no_therapist(self):
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("therapist_profiles", [])
        details = await matching_service.get_match_details(
            therapist_id="nonexistent",
            patient_id="patient-001",
            db=db,
        )
        assert details is None
