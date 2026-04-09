"""
Tests for the Crisis Service.

Covers: keyword scanning, severity assessment (baixa -> critica),
alert CRUD, review workflow.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import crisis_service


SAMPLE_ALERT = {
    "id": "alert-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "source_type": "journal",
    "source_id": "journal-001",
    "keywords_found": ["quero morrer"],
    "severity": "alta",
    "status": "pendente",
    "detected_at": "2026-04-01T10:00:00Z",
}


# ---------------------------------------------------------------------------
# Text Scanning
# ---------------------------------------------------------------------------

class TestScanText:
    def test_scan_finds_keywords(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = crisis_service.scan_text(
            text="Eu quero morrer, não aguento mais",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="journal",
            source_id="journal-001",
            db=db,
        )
        assert result is not None

    def test_scan_no_keywords(self):
        db = MockSupabaseClient()
        result = crisis_service.scan_text(
            text="Tive um dia bom, me senti calmo e em paz",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="journal",
            source_id="journal-001",
            db=db,
        )
        assert result is None

    def test_scan_empty_text(self):
        db = MockSupabaseClient()
        result = crisis_service.scan_text(
            text="",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="journal",
            source_id="journal-001",
            db=db,
        )
        assert result is None

    def test_scan_whitespace_only(self):
        db = MockSupabaseClient()
        result = crisis_service.scan_text(
            text="   \n\t   ",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="journal",
            source_id="journal-001",
            db=db,
        )
        assert result is None

    def test_scan_case_insensitive(self):
        """Keywords match regardless of case."""
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = crisis_service.scan_text(
            text="Eu QUERO MORRER",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="journal",
            source_id="journal-001",
            db=db,
        )
        assert result is not None

    def test_scan_multiple_keywords(self):
        """Detects multiple keywords in a single text."""
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = crisis_service.scan_text(
            text="Quero morrer, não aguento mais, sem saída",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="session_transcript",
            source_id="session-001",
            db=db,
        )
        assert result is not None

    def test_scan_accented_keywords(self):
        """Detects accented Portuguese keywords."""
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = crisis_service.scan_text(
            text="Penso em suicídio",
            patient_id="patient-001",
            therapist_id="therapist-001",
            source_type="chat",
            source_id="chat-001",
            db=db,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Severity Assessment
# ---------------------------------------------------------------------------

class TestAssessSeverity:
    def test_single_low_keyword_is_baixa(self):
        result = crisis_service.assess_severity(
            text="ninguém se importa",
            keywords_found=["ninguém se importa"],
        )
        assert result == "baixa"

    def test_two_low_keywords_is_media(self):
        result = crisis_service.assess_severity(
            text="test",
            keywords_found=["ninguém se importa", "sem saída"],
        )
        assert result == "media"

    def test_three_low_keywords_is_alta(self):
        result = crisis_service.assess_severity(
            text="test",
            keywords_found=["ninguém se importa", "sem saída", "não aguento mais"],
        )
        assert result == "alta"

    def test_single_high_keyword_is_alta(self):
        result = crisis_service.assess_severity(
            text="test",
            keywords_found=["suicídio"],
        )
        assert result == "alta"

    def test_high_keyword_plus_multiple_is_critica(self):
        """High-severity keyword + 3+ total keywords = critica."""
        result = crisis_service.assess_severity(
            text="test",
            keywords_found=["suicídio", "me matar", "tirar minha vida"],
        )
        assert result == "critica"

    def test_multiple_high_keywords_is_critica(self):
        result = crisis_service.assess_severity(
            text="test",
            keywords_found=["suicídio", "overdose", "planejamento suicida"],
        )
        assert result == "critica"


# ---------------------------------------------------------------------------
# Alert Management
# ---------------------------------------------------------------------------

class TestListAlerts:
    @pytest.mark.asyncio
    async def test_list_alerts(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = await crisis_service.list_alerts(
            therapist_id="therapist-001",
            db=db,
        )
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_alerts_with_status_filter(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = await crisis_service.list_alerts(
            therapist_id="therapist-001",
            db=db,
            status_filter="pendente",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [])
        result = await crisis_service.list_alerts(
            therapist_id="therapist-001",
            db=db,
        )
        assert result == []


class TestReviewAlert:
    @pytest.mark.asyncio
    async def test_review_alert(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = await crisis_service.review_alert(
            alert_id="alert-001",
            reviewer_id="therapist-001",
            data={"status": "revisado"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_review_alert_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [])
        with pytest.raises(Exception) as exc_info:
            await crisis_service.review_alert(
                alert_id="nonexistent",
                reviewer_id="therapist-001",
                data={"status": "revisado"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_review_already_reviewed(self):
        """Cannot review an alert that is no longer pendente."""
        db = MockSupabaseClient()
        reviewed_alert = {**SAMPLE_ALERT, "status": "revisado"}
        db.set_table_data("crisis_alerts", [reviewed_alert])
        with pytest.raises(Exception) as exc_info:
            await crisis_service.review_alert(
                alert_id="alert-001",
                reviewer_id="therapist-001",
                data={"status": "falso_positivo"},
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_review_as_false_positive(self):
        db = MockSupabaseClient()
        db.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        result = await crisis_service.review_alert(
            alert_id="alert-001",
            reviewer_id="therapist-001",
            data={"status": "falso_positivo"},
            db=db,
        )
        assert result is not None
