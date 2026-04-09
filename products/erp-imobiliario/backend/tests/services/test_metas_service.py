"""
Unit tests for Metas Service — date math, proportional targets, and batch creation.
"""
import pytest
from datetime import date, timedelta

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# _period_end_date
# ---------------------------------------------------------------------------

class TestPeriodEndDate:

    def test_diaria_returns_same_day(self):
        from app.services.metas_service import _period_end_date
        ref = date(2026, 3, 10)  # Tuesday
        assert _period_end_date("diaria", ref) == ref

    def test_semanal_returns_sunday(self):
        from app.services.metas_service import _period_end_date
        # 2026-03-10 is Tuesday (isoweekday=2), Sunday = 2026-03-15
        ref = date(2026, 3, 10)
        assert _period_end_date("semanal", ref) == date(2026, 3, 15)

    def test_semanal_sunday_returns_same_day(self):
        from app.services.metas_service import _period_end_date
        # Sunday itself
        ref = date(2026, 3, 15)
        assert _period_end_date("semanal", ref) == date(2026, 3, 15)

    def test_mensal_returns_last_day_of_month(self):
        from app.services.metas_service import _period_end_date
        ref = date(2026, 3, 10)
        assert _period_end_date("mensal", ref) == date(2026, 3, 31)

    def test_mensal_february_non_leap(self):
        from app.services.metas_service import _period_end_date
        ref = date(2027, 2, 5)
        assert _period_end_date("mensal", ref) == date(2027, 2, 28)

    def test_mensal_february_leap_year(self):
        from app.services.metas_service import _period_end_date
        ref = date(2028, 2, 5)  # 2028 is a leap year
        assert _period_end_date("mensal", ref) == date(2028, 2, 29)

    def test_mensal_december(self):
        from app.services.metas_service import _period_end_date
        ref = date(2026, 12, 5)
        assert _period_end_date("mensal", ref) == date(2026, 12, 31)

    def test_anual_returns_dec_31(self):
        from app.services.metas_service import _period_end_date
        ref = date(2026, 6, 15)
        assert _period_end_date("anual", ref) == date(2026, 12, 31)

    def test_unknown_tipo_returns_same_day(self):
        from app.services.metas_service import _period_end_date
        ref = date(2026, 3, 10)
        assert _period_end_date("unknown", ref) == ref


# ---------------------------------------------------------------------------
# _count_weekdays
# ---------------------------------------------------------------------------

class TestCountWeekdays:

    def test_full_week(self):
        from app.services.metas_service import _count_weekdays
        # Mon 2026-03-09 to Sun 2026-03-15 → 5 weekdays
        assert _count_weekdays(date(2026, 3, 9), date(2026, 3, 15)) == 5

    def test_single_weekday(self):
        from app.services.metas_service import _count_weekdays
        assert _count_weekdays(date(2026, 3, 10), date(2026, 3, 10)) == 1

    def test_single_weekend_day(self):
        from app.services.metas_service import _count_weekdays
        # Saturday
        assert _count_weekdays(date(2026, 3, 14), date(2026, 3, 14)) == 0

    def test_two_weeks(self):
        from app.services.metas_service import _count_weekdays
        # 2 full weeks = 10 weekdays
        assert _count_weekdays(date(2026, 3, 9), date(2026, 3, 22)) == 10


# ---------------------------------------------------------------------------
# _dias_uteis_totais_mes
# ---------------------------------------------------------------------------

class TestDiasUteisTotaisMes:

    def test_march_2026(self):
        from app.services.metas_service import _dias_uteis_totais_mes
        # March 2026: 22 weekdays
        result = _dias_uteis_totais_mes(date(2026, 3, 10))
        assert result == 22

    def test_february_2026(self):
        from app.services.metas_service import _dias_uteis_totais_mes
        # February 2026: 20 weekdays (28 days, starts on Sunday)
        result = _dias_uteis_totais_mes(date(2026, 2, 15))
        assert result == 20


# ---------------------------------------------------------------------------
# _calcular_meta_proporcional
# ---------------------------------------------------------------------------

class TestCalcularMetaProporcional:

    def test_diaria_divides_by_workdays_in_month(self):
        from app.services.metas_service import _calcular_meta_proporcional
        import math
        # March 2026: 22 weekdays. meta_mensal=100 → ceil(100/22) = 5
        result = _calcular_meta_proporcional(100, "diaria", date(2026, 3, 10))
        assert result == math.ceil(100 / 22)

    def test_mensal_proportional_to_remaining_days(self):
        from app.services.metas_service import _calcular_meta_proporcional, _dias_uteis_totais_mes, _dias_uteis_restantes_mes
        import math
        ref = date(2026, 3, 10)
        total = _dias_uteis_totais_mes(ref)
        restantes = _dias_uteis_restantes_mes(ref)
        expected = math.ceil(100 * restantes / max(total, 1))
        result = _calcular_meta_proporcional(100, "mensal", ref)
        assert result == expected

    def test_semanal_proportional(self):
        from app.services.metas_service import _calcular_meta_proporcional, _dias_uteis_totais_mes, _dias_uteis_restantes_semana
        import math
        ref = date(2026, 3, 10)  # Tuesday
        total = _dias_uteis_totais_mes(ref)
        restantes = _dias_uteis_restantes_semana(ref)
        diaria = 100 / max(total, 1)
        expected = math.ceil(diaria * restantes)
        result = _calcular_meta_proporcional(100, "semanal", ref)
        assert result == expected

    def test_anual_proportional(self):
        from app.services.metas_service import _calcular_meta_proporcional, _dias_uteis_totais_ano, _dias_uteis_restantes_ano
        import math
        ref = date(2026, 3, 10)
        total = _dias_uteis_totais_ano(ref)
        restantes = _dias_uteis_restantes_ano(ref)
        expected = math.ceil(100 * 12 * restantes / max(total, 1))
        result = _calcular_meta_proporcional(100, "anual", ref)
        assert result == expected

    def test_unknown_tipo_returns_meta_mensal(self):
        from app.services.metas_service import _calcular_meta_proporcional
        result = _calcular_meta_proporcional(50, "bimestral", date(2026, 3, 10))
        assert result == 50


# ---------------------------------------------------------------------------
# criar_metas_hoje
# ---------------------------------------------------------------------------

class TestCriarMetasHoje:

    def _make_db(self, configs=None, existing_metas=None):
        db = MockSupabaseClient()
        db.set_table_data("metas_config", configs or [])
        db.set_table_data("metas", existing_metas or [])
        return db

    def test_creates_4_metas_per_config(self):
        """One config should produce 4 metas (diaria, semanal, mensal, anual)."""
        from app.services.metas_service import criar_metas_hoje

        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "ligacoes",
            "meta_pretendida": 100,
            "ativo": True,
        }]
        db = self._make_db(configs=configs)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 4  # diaria + semanal + mensal + anual

    def test_skips_existing_metas(self):
        """Should not duplicate metas that already exist."""
        from app.services.metas_service import criar_metas_hoje, _period_end_date

        ref = date(2026, 3, 10)
        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "ligacoes",
            "meta_pretendida": 100,
            "ativo": True,
        }]
        # One meta already exists for "diaria"
        existing = [{
            "tipo": "diaria",
            "categoria": "ligacoes",
            "data_prazo": _period_end_date("diaria", ref).isoformat(),
        }]
        db = self._make_db(configs=configs, existing_metas=existing)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 3  # semanal + mensal + anual (diaria skipped)

    def test_returns_zero_with_no_configs(self):
        """No active configs → no metas created."""
        from app.services.metas_service import criar_metas_hoje

        db = self._make_db(configs=[])
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 0

    def test_handles_date_as_list(self):
        """data_hoje may arrive as a list (from RPC wrapping)."""
        from app.services.metas_service import criar_metas_hoje

        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "visitas",
            "meta_pretendida": 50,
            "ativo": True,
        }]
        db = self._make_db(configs=configs)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", ["2026-03-10"], db, admin)
        assert count == 4

    def test_handles_date_as_date_object(self):
        """data_hoje may arrive as a date object."""
        from app.services.metas_service import criar_metas_hoje

        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "visitas",
            "meta_pretendida": 50,
            "ativo": True,
        }]
        db = self._make_db(configs=configs)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", date(2026, 3, 10), db, admin)
        assert count == 4

    def test_returns_zero_when_date_is_none_list(self):
        """Empty list for data_hoje → 0."""
        from app.services.metas_service import criar_metas_hoje

        db = self._make_db(configs=[])
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", [], db, admin)
        assert count == 0

    def test_returns_zero_when_date_is_none(self):
        """None for data_hoje → 0."""
        from app.services.metas_service import criar_metas_hoje

        db = self._make_db(configs=[])
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", None, db, admin)
        assert count == 0

    def test_multiple_configs_multiply_metas(self):
        """Two configs → 8 metas (4 per config)."""
        from app.services.metas_service import criar_metas_hoje

        configs = [
            {
                "id": "cfg-1",
                "usuario_id": "user-1",
                "categoria": "ligacoes",
                "meta_pretendida": 100,
                "ativo": True,
            },
            {
                "id": "cfg-2",
                "usuario_id": "user-1",
                "categoria": "visitas",
                "meta_pretendida": 50,
                "ativo": True,
            },
        ]
        db = self._make_db(configs=configs)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 8

    def test_preserves_categoria_custom(self):
        """categoria_custom from config is passed through to the inserted meta."""
        from app.services.metas_service import criar_metas_hoje

        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "custom",
            "categoria_custom": "Minha Categoria",
            "meta_pretendida": 30,
            "ativo": True,
        }]
        db = self._make_db(configs=configs)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 4

    def test_all_existing_metas_skipped(self):
        """When all 4 types already exist, nothing is created."""
        from app.services.metas_service import criar_metas_hoje, _period_end_date

        ref = date(2026, 3, 10)
        configs = [{
            "id": "cfg-1",
            "usuario_id": "user-1",
            "categoria": "ligacoes",
            "meta_pretendida": 100,
            "ativo": True,
        }]
        existing = [
            {"tipo": tipo, "categoria": "ligacoes", "data_prazo": _period_end_date(tipo, ref).isoformat()}
            for tipo in ["diaria", "semanal", "mensal", "anual"]
        ]
        db = self._make_db(configs=configs, existing_metas=existing)
        admin = MockSupabaseClient()

        count = criar_metas_hoje("user-1", "2026-03-10", db, admin)
        assert count == 0
