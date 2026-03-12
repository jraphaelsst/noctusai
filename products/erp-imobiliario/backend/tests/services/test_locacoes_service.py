"""
Unit tests for locacoes_service — rental/lease management and reajuste logic.
"""
import pytest
from datetime import date, timedelta

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# calculate_reajuste
# ---------------------------------------------------------------------------

class TestCalculateReajuste:

    def test_igpm_default_rate(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=2000.0, indice="IGPM")

        assert result["valor_anterior"] == 2000.0
        assert result["indice"] == "IGPM"
        assert result["percentual_aplicado"] == 4.52
        expected_new = round(2000.0 * (1 + 4.52 / 100), 2)
        assert result["valor_novo"] == expected_new
        assert result["diferenca"] == round(expected_new - 2000.0, 2)

    def test_ipca_default_rate(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=1500.0, indice="IPCA")

        assert result["percentual_aplicado"] == 4.62
        expected = round(1500.0 * (1 + 4.62 / 100), 2)
        assert result["valor_novo"] == expected

    def test_fixo_with_percentual(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=1000.0, indice="fixo", percentual=5.0)

        assert result["percentual_aplicado"] == 5.0
        assert result["valor_novo"] == 1050.0
        assert result["diferenca"] == 50.0

    def test_fixo_without_percentual_no_change(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=1000.0, indice="fixo")

        assert result["percentual_aplicado"] == 0.0
        assert result["valor_novo"] == 1000.0
        assert result["diferenca"] == 0.0

    def test_override_percentual(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=2000.0, indice="IGPM", percentual=10.0)

        assert result["percentual_aplicado"] == 10.0
        assert result["valor_novo"] == 2200.0

    def test_unknown_indice_defaults_to_zero(self):
        from app.services.locacoes_service import calculate_reajuste

        result = calculate_reajuste(valor_atual=1000.0, indice="DESCONHECIDO")

        assert result["percentual_aplicado"] == 0.0
        assert result["valor_novo"] == 1000.0


# ---------------------------------------------------------------------------
# generate_monthly_charges
# ---------------------------------------------------------------------------

class TestGenerateMonthlyCharges:

    def test_three_month_contract(self):
        db = MockSupabaseClient(data=[])

        from app.services.locacoes_service import generate_monthly_charges

        contrato = {
            "id": "c-1",
            "org_id": "org-1",
            "valor_aluguel": 2500.0,
            "dia_vencimento": 10,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-03-31",
        }

        charges = generate_monthly_charges(contrato, db)

        assert len(charges) == 3
        assert charges[0]["data_vencimento"] == "2026-01-10"
        assert charges[1]["data_vencimento"] == "2026-02-10"
        assert charges[2]["data_vencimento"] == "2026-03-10"
        for c in charges:
            assert c["valor"] == 2500.0
            assert c["tipo"] == "aluguel"
            assert c["status"] == "pendente"

    def test_day_clamping_february(self):
        """Vencimento dia 31 should be clamped to last day of Feb."""
        db = MockSupabaseClient(data=[])

        from app.services.locacoes_service import generate_monthly_charges

        contrato = {
            "id": "c-2",
            "org_id": "org-1",
            "valor_aluguel": 1000.0,
            "dia_vencimento": 31,
            "data_inicio": "2026-02-01",
            "data_fim": "2026-02-28",
        }

        charges = generate_monthly_charges(contrato, db)

        assert len(charges) == 1
        assert charges[0]["data_vencimento"] == "2026-02-28"


# ---------------------------------------------------------------------------
# _parse_date / _last_day_of_month (internal helpers, tested via generate)
# ---------------------------------------------------------------------------

class TestParseDate:

    def test_string_input(self):
        from app.services.locacoes_service import _parse_date

        result = _parse_date("2026-06-15")
        assert result == date(2026, 6, 15)

    def test_date_input_passthrough(self):
        from app.services.locacoes_service import _parse_date

        d = date(2026, 7, 20)
        assert _parse_date(d) == d
