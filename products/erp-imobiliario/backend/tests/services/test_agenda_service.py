"""
Unit tests for agenda_service — conflict detection for scheduling.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# check_conflict
# ---------------------------------------------------------------------------

class TestCheckConflict:

    def test_no_conflict_returns_none(self):
        db = MockSupabaseClient(data=[])

        from app.services.agenda_service import check_conflict
        result = check_conflict(
            corretor_id="c-1",
            data_inicio="2026-03-10T09:00:00",
            data_fim="2026-03-10T10:00:00",
            supabase=db,
        )

        assert result is None

    def test_conflict_returns_first_event(self):
        conflicting = {"id": "evt-1", "titulo": "Visita", "data_inicio": "2026-03-10T09:30:00", "data_fim": "2026-03-10T10:30:00"}
        db = MockSupabaseClient(data=[conflicting])

        from app.services.agenda_service import check_conflict
        result = check_conflict(
            corretor_id="c-1",
            data_inicio="2026-03-10T09:00:00",
            data_fim="2026-03-10T11:00:00",
            supabase=db,
        )

        assert result is not None
        assert result["id"] == "evt-1"

    def test_exclude_id_param_accepted(self):
        """When exclude_id is given, the query should still run without error."""
        db = MockSupabaseClient(data=[])

        from app.services.agenda_service import check_conflict
        result = check_conflict(
            corretor_id="c-1",
            data_inicio="2026-03-10T09:00:00",
            data_fim="2026-03-10T10:00:00",
            supabase=db,
            exclude_id="evt-self",
        )

        assert result is None

    def test_multiple_conflicts_returns_first(self):
        conflicts = [
            {"id": "evt-1", "titulo": "Reuniao 1", "data_inicio": "2026-03-10T09:00:00", "data_fim": "2026-03-10T10:00:00"},
            {"id": "evt-2", "titulo": "Reuniao 2", "data_inicio": "2026-03-10T09:30:00", "data_fim": "2026-03-10T10:30:00"},
        ]
        db = MockSupabaseClient(data=conflicts)

        from app.services.agenda_service import check_conflict
        result = check_conflict(
            corretor_id="c-1",
            data_inicio="2026-03-10T08:30:00",
            data_fim="2026-03-10T11:00:00",
            supabase=db,
        )

        assert result["id"] == "evt-1"

    def test_empty_data_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.agenda_service import check_conflict
        result = check_conflict(
            corretor_id="c-1",
            data_inicio="2026-03-10T09:00:00",
            data_fim="2026-03-10T10:00:00",
            supabase=db,
        )

        assert result is None
