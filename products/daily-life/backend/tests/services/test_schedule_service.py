"""Tests for schedule service — recurrence expansion logic."""
from datetime import date, timedelta

from app.services.schedule_service import expandir_recorrencias


def _event(recorrencia="nenhuma", data_inicio="2026-04-14T09:00:00", recorrencia_fim=None, **extra):
    return {
        "id": "evt-1",
        "titulo": "Test Event",
        "data_inicio": data_inicio,
        "data_fim": None,
        "recorrencia": recorrencia,
        "recorrencia_fim": recorrencia_fim,
        **extra,
    }


class TestNoRecurrence:
    def test_passes_through_unchanged(self):
        events = [_event()]
        result = expandir_recorrencias(events, date(2026, 4, 1), date(2026, 4, 30))
        assert len(result) == 1
        assert result[0]["id"] == "evt-1"

    def test_none_recurrence_passes_through(self):
        events = [_event(recorrencia=None)]
        result = expandir_recorrencias(events, date(2026, 4, 1), date(2026, 4, 30))
        assert len(result) == 1


class TestDailyRecurrence:
    def test_expands_daily(self):
        events = [_event(recorrencia="diario", data_inicio="2026-04-14T09:00:00")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 4, 20))
        # Original + 6 daily occurrences (15, 16, 17, 18, 19, 20)
        assert len(result) == 7

    def test_respects_recorrencia_fim(self):
        events = [_event(recorrencia="diario", data_inicio="2026-04-14T09:00:00", recorrencia_fim="2026-04-16")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 4, 30))
        # Original + 2 (15, 16)
        assert len(result) == 3

    def test_occurrences_have_evento_pai_id(self):
        events = [_event(recorrencia="diario")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 4, 16))
        expanded = [e for e in result if e.get("is_recorrencia")]
        assert len(expanded) == 2
        for occ in expanded:
            assert occ["evento_pai_id"] == "evt-1"


class TestWeeklyRecurrence:
    def test_expands_weekly(self):
        events = [_event(recorrencia="semanal", data_inicio="2026-04-14T09:00:00")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 5, 12))
        # Original + 4 weekly (21, 28, May 5, May 12)
        assert len(result) == 5


class TestMonthlyRecurrence:
    def test_expands_monthly(self):
        events = [_event(recorrencia="mensal", data_inicio="2026-04-14T09:00:00")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 7, 14))
        # Original + 3 monthly (May 14, Jun 14, Jul 14)
        assert len(result) == 4


class TestAnnualRecurrence:
    def test_expands_annual(self):
        events = [_event(recorrencia="anual", data_inicio="2026-04-14T09:00:00")]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2028, 4, 14))
        # Original + 2 annual (2027, 2028)
        assert len(result) == 3


class TestEdgeCases:
    def test_empty_events(self):
        result = expandir_recorrencias([], date(2026, 4, 1), date(2026, 4, 30))
        assert result == []

    def test_preserves_duration(self):
        events = [_event(
            recorrencia="diario",
            data_inicio="2026-04-14T09:00:00",
            data_fim="2026-04-14T10:30:00",
        )]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 4, 15))
        expanded = [e for e in result if e.get("is_recorrencia")]
        assert len(expanded) == 1
        # Duration should be 1.5 hours
        assert "10:30" in expanded[0]["data_fim"]

    def test_sorted_by_data_inicio(self):
        events = [
            _event(id="b", data_inicio="2026-04-16T09:00:00"),
            _event(id="a", data_inicio="2026-04-14T09:00:00"),
        ]
        result = expandir_recorrencias(events, date(2026, 4, 1), date(2026, 4, 30))
        assert result[0]["data_inicio"] < result[1]["data_inicio"]

    def test_mixed_recurring_and_non(self):
        events = [
            _event(recorrencia="nenhuma", data_inicio="2026-04-15T12:00:00"),
            _event(recorrencia="diario", data_inicio="2026-04-14T09:00:00"),
        ]
        result = expandir_recorrencias(events, date(2026, 4, 14), date(2026, 4, 16))
        # Non-recurring: 1, Recurring: 1 original + 2 occurrences = 4
        assert len(result) == 4
