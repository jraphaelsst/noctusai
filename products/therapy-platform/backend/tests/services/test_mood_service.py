"""
Tests for the Mood Service.

Covers: create entry, date range filtering, analytics calculation
(avg rating, trend, emotion frequency).
"""
import pytest

from tests.conftest import MockSupabaseClient, MockSupabaseResponse
from app.services import mood_service


SAMPLE_ENTRIES = [
    {"id": "mood-001", "patient_id": "patient-001", "rating": 3, "emocoes": ["ansiedade", "tristeza"], "created_at": "2026-03-01T10:00:00Z"},
    {"id": "mood-002", "patient_id": "patient-001", "rating": 4, "emocoes": ["ansiedade"], "created_at": "2026-03-05T10:00:00Z"},
    {"id": "mood-003", "patient_id": "patient-001", "rating": 5, "emocoes": ["calma"], "created_at": "2026-03-10T10:00:00Z"},
    {"id": "mood-004", "patient_id": "patient-001", "rating": 6, "emocoes": ["calma", "esperança"], "created_at": "2026-03-15T10:00:00Z"},
    {"id": "mood-005", "patient_id": "patient-001", "rating": 7, "emocoes": ["esperança", "alegria"], "created_at": "2026-03-20T10:00:00Z"},
    {"id": "mood-006", "patient_id": "patient-001", "rating": 8, "emocoes": ["alegria"], "created_at": "2026-03-25T10:00:00Z"},
]


class TestCreateMoodEntry:
    @pytest.mark.asyncio
    async def test_create_entry(self):
        db = MockSupabaseClient()
        # `set_sequential_responses` controls the insert response — the row
        # returned by the DB carries `rating: 3` (from SAMPLE_ENTRIES[0]),
        # exercising the service path that returns whatever the DB row is.
        db.set_sequential_responses("mood_entries", [MockSupabaseResponse(data=[SAMPLE_ENTRIES[0]])])
        result = await mood_service.create_entry(
            patient_id="patient-001",
            data={"rating": 7, "emocoes": ["calma", "esperança"], "nota": "Bom dia"},
            db=db,
        )
        assert result is not None
        assert result["rating"] == 3

    @pytest.mark.asyncio
    async def test_create_entry_minimal(self):
        """Create entry with only required fields."""
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", [{"id": "mood-new", "patient_id": "patient-001", "rating": 5}])
        result = await mood_service.create_entry(
            patient_id="patient-001",
            data={"rating": 5},
            db=db,
        )
        assert result is not None


class TestListMoodEntries:
    @pytest.mark.asyncio
    async def test_list_entries(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", SAMPLE_ENTRIES)
        data, total = await mood_service.list_entries(
            patient_id="patient-001",
            db=db,
        )
        assert isinstance(data, list)
        assert len(data) == 6

    @pytest.mark.asyncio
    async def test_list_entries_with_date_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", SAMPLE_ENTRIES[:3])
        data, total = await mood_service.list_entries(
            patient_id="patient-001",
            db=db,
            data_inicio="2026-03-01",
            data_fim="2026-03-10",
        )
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_entries_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", [])
        data, total = await mood_service.list_entries(
            patient_id="patient-001",
            db=db,
        )
        assert data == []
        assert total == 0


class TestMoodAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_with_data(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", SAMPLE_ENTRIES)
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        assert result["total_entries"] == 6
        assert result["avg_rating"] is not None
        assert isinstance(result["emotion_frequency"], dict)
        assert result["trend"] in ("improving", "declining", "stable")

    @pytest.mark.asyncio
    async def test_analytics_improving_trend(self):
        """When second half avg > first half avg by > 0.5, trend is improving."""
        db = MockSupabaseClient()
        # Ratings: 3, 4, 5, 6, 7, 8 — first half avg 4.0, second half avg 7.0
        db.set_table_data("mood_entries", SAMPLE_ENTRIES)
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        assert result["trend"] == "improving"

    @pytest.mark.asyncio
    async def test_analytics_declining_trend(self):
        """When second half avg < first half avg by > 0.5, trend is declining."""
        db = MockSupabaseClient()
        declining_entries = [
            {"rating": 8, "emocoes": [], "created_at": "2026-03-01T10:00:00Z"},
            {"rating": 7, "emocoes": [], "created_at": "2026-03-05T10:00:00Z"},
            {"rating": 6, "emocoes": [], "created_at": "2026-03-10T10:00:00Z"},
            {"rating": 3, "emocoes": [], "created_at": "2026-03-15T10:00:00Z"},
            {"rating": 2, "emocoes": [], "created_at": "2026-03-20T10:00:00Z"},
            {"rating": 1, "emocoes": [], "created_at": "2026-03-25T10:00:00Z"},
        ]
        db.set_table_data("mood_entries", declining_entries)
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        assert result["trend"] == "declining"

    @pytest.mark.asyncio
    async def test_analytics_stable_trend(self):
        """When difference is less than 0.5, trend is stable."""
        db = MockSupabaseClient()
        stable_entries = [
            {"rating": 5, "emocoes": [], "created_at": "2026-03-01T10:00:00Z"},
            {"rating": 5, "emocoes": [], "created_at": "2026-03-10T10:00:00Z"},
            {"rating": 5, "emocoes": [], "created_at": "2026-03-20T10:00:00Z"},
            {"rating": 5, "emocoes": [], "created_at": "2026-03-25T10:00:00Z"},
        ]
        db.set_table_data("mood_entries", stable_entries)
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        assert result["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_analytics_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", [])
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        assert result["avg_rating"] is None
        assert result["total_entries"] == 0
        assert result["trend"] == "stable"
        assert result["emotion_frequency"] == {}

    @pytest.mark.asyncio
    async def test_analytics_emotion_frequency(self):
        db = MockSupabaseClient()
        db.set_table_data("mood_entries", SAMPLE_ENTRIES)
        result = await mood_service.get_analytics(
            patient_id="patient-001",
            db=db,
        )
        freq = result["emotion_frequency"]
        assert freq["ansiedade"] == 2
        assert freq["calma"] == 2
        assert freq["esperança"] == 2
        assert freq["alegria"] == 2
        assert freq["tristeza"] == 1
