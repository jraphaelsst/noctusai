"""
Unit tests for analise_credito_service — credit analysis, scoring, and dispatching.
"""
import pytest
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# consultar_serasa
# ---------------------------------------------------------------------------

class TestConsultarSerasa:

    def test_returns_pending_placeholder(self):
        from app.services.analise_credito_service import consultar_serasa

        result = consultar_serasa("12345678901")

        assert result["status"] == "pendente"
        assert result["score"] is None
        assert result["resultado"]["fonte"] == "serasa"
        assert "pendente de configura" in result["resultado"]["mensagem"].lower()

    def test_validade_30_days_from_today(self):
        from app.services.analise_credito_service import consultar_serasa

        result = consultar_serasa("12345678901")
        expected = (date.today() + timedelta(days=30)).isoformat()

        assert result["validade"] == expected

    def test_empty_pendencias_and_restricoes(self):
        from app.services.analise_credito_service import consultar_serasa

        result = consultar_serasa("12345678901")

        assert result["resultado"]["pendencias"] == []
        assert result["resultado"]["restricoes"] == []


# ---------------------------------------------------------------------------
# consultar_boa_vista
# ---------------------------------------------------------------------------

class TestConsultarBoaVista:

    def test_returns_pending_placeholder(self):
        from app.services.analise_credito_service import consultar_boa_vista

        result = consultar_boa_vista("98765432100")

        assert result["status"] == "pendente"
        assert result["score"] is None
        assert result["resultado"]["fonte"] == "boa_vista"

    def test_validade_30_days(self):
        from app.services.analise_credito_service import consultar_boa_vista

        result = consultar_boa_vista("98765432100")
        expected = (date.today() + timedelta(days=30)).isoformat()

        assert result["validade"] == expected


# ---------------------------------------------------------------------------
# analise_manual — score thresholds
# ---------------------------------------------------------------------------

class TestAnaliseManual:

    def test_high_score_approved(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=750)

        assert result["status"] == "aprovado"
        assert result["score"] == 750
        assert "aprovado" in result["resultado"]["recomendacao"].lower()

    def test_medium_score_em_analise(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=500)

        assert result["status"] == "em_analise"
        assert "adicional" in result["resultado"]["recomendacao"].lower()

    def test_low_score_reprovado(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=350)

        assert result["status"] == "reprovado"
        assert "reprovado" in result["resultado"]["recomendacao"].lower()

    def test_none_score_pendente(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=None)

        assert result["status"] == "pendente"
        assert result["score"] is None

    def test_boundary_score_700_approved(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=700)

        assert result["status"] == "aprovado"

    def test_boundary_score_400_em_analise(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=400)

        assert result["status"] == "em_analise"

    def test_boundary_score_399_reprovado(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=399)

        assert result["status"] == "reprovado"

    def test_manual_with_detalhes(self):
        from app.services.analise_credito_service import analise_manual

        detalhes = {"renda_mensal": 8000, "observacao": "Sem restricoes"}
        result = analise_manual("12345678901", score=800, detalhes=detalhes)

        assert result["resultado"]["renda_mensal"] == 8000
        assert result["resultado"]["observacao"] == "Sem restricoes"

    def test_validade_90_days(self):
        from app.services.analise_credito_service import analise_manual

        result = analise_manual("12345678901", score=500)
        expected = (date.today() + timedelta(days=90)).isoformat()

        assert result["validade"] == expected


# ---------------------------------------------------------------------------
# executar_analise — dispatching
# ---------------------------------------------------------------------------

class TestExecutarAnalise:

    def test_dispatch_serasa(self):
        from app.services.analise_credito_service import executar_analise

        result = executar_analise("12345678901", "Joao", fonte="serasa")

        assert result["resultado"]["fonte"] == "serasa"
        assert result["status"] == "pendente"

    def test_dispatch_boa_vista(self):
        from app.services.analise_credito_service import executar_analise

        result = executar_analise("12345678901", "Maria", fonte="boa_vista")

        assert result["resultado"]["fonte"] == "boa_vista"
        assert result["status"] == "pendente"

    def test_dispatch_manual(self):
        from app.services.analise_credito_service import executar_analise

        result = executar_analise(
            "12345678901", "Pedro",
            fonte="manual",
            score_manual=800,
        )

        assert result["resultado"]["fonte"] == "manual"
        assert result["status"] == "aprovado"
        assert result["score"] == 800

    def test_unknown_fonte_falls_back_to_manual(self):
        from app.services.analise_credito_service import executar_analise

        result = executar_analise(
            "12345678901", "Ana",
            fonte="desconhecida",
            score_manual=600,
        )

        assert result["resultado"]["fonte"] == "manual"
        assert result["status"] == "em_analise"
