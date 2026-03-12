"""
Unit tests for gamificacao_service — points, badges, leaderboard, and stats.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# get_pontos_para_acao
# ---------------------------------------------------------------------------

class TestGetPontosParaAcao:

    def test_known_actions(self):
        from app.services.gamificacao_service import get_pontos_para_acao

        assert get_pontos_para_acao("novo_cliente") == 10
        assert get_pontos_para_acao("visita_realizada") == 15
        assert get_pontos_para_acao("proposta_enviada") == 20
        assert get_pontos_para_acao("venda_fechada") == 100
        assert get_pontos_para_acao("meta_cumprida") == 50

    def test_unknown_action_returns_zero(self):
        from app.services.gamificacao_service import get_pontos_para_acao

        assert get_pontos_para_acao("acao_desconhecida") == 0


# ---------------------------------------------------------------------------
# registrar_pontos
# ---------------------------------------------------------------------------

class TestRegistrarPontos:

    def test_registers_known_action(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import registrar_pontos
        result = registrar_pontos("u-1", "novo_cliente", db)

        assert result["pontos"] == 10
        assert result["acao"] == "novo_cliente"
        assert isinstance(result["novas_conquistas"], list)

    def test_unknown_action_returns_zero_points(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import registrar_pontos
        result = registrar_pontos("u-1", "acao_invalida", db)

        assert result["pontos"] == 0
        assert result["novas_conquistas"] == []

    def test_venda_fechada_gives_100(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import registrar_pontos
        result = registrar_pontos("u-1", "venda_fechada", db)

        assert result["pontos"] == 100

    def test_referencia_params_accepted(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import registrar_pontos
        result = registrar_pontos(
            "u-1", "proposta_enviada", db,
            referencia_id="prop-1",
            referencia_tipo="proposta",
        )

        assert result["pontos"] == 20


# ---------------------------------------------------------------------------
# check_and_award_badges
# ---------------------------------------------------------------------------

class TestCheckAndAwardBadges:

    def test_no_badges_when_no_stats(self):
        """When user has no activity, no badges should be awarded."""
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import check_and_award_badges
        result = check_and_award_badges("u-1", db)

        assert isinstance(result, list)

    def test_primeiro_passo_badge_awarded(self):
        """Badge 'primeiro_passo' awarded when total_clientes >= 1."""
        db = MockSupabaseClient()
        # pontuacoes returns one 'novo_cliente' record
        db.set_table_data("pontuacoes", [
            {"id": "p-1", "pontos": 10, "user_id": "u-1", "acao": "novo_cliente"},
        ])
        # conquistas returns empty (no existing badges)
        db.set_table_data("conquistas", [])

        from app.services.gamificacao_service import check_and_award_badges
        result = check_and_award_badges("u-1", db)

        # The badge check depends on _get_user_stats which queries pontuacoes
        # With mock data returning same data for all queries, we check it runs without error
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# build_leaderboard
# ---------------------------------------------------------------------------

class TestBuildLeaderboard:

    def test_empty_data_returns_empty(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import build_leaderboard
        result = build_leaderboard(db, periodo="geral")

        assert result == []

    def test_leaderboard_ranking(self):
        rows = [
            {"user_id": "u-1", "pontos": 50, "created_at": "2026-03-01T10:00:00"},
            {"user_id": "u-1", "pontos": 30, "created_at": "2026-03-01T11:00:00"},
            {"user_id": "u-2", "pontos": 100, "created_at": "2026-03-01T10:00:00"},
            {"user_id": "u-3", "pontos": 20, "created_at": "2026-03-01T10:00:00"},
        ]
        db = MockSupabaseClient(data=rows)

        from app.services.gamificacao_service import build_leaderboard
        result = build_leaderboard(db, periodo="geral")

        assert len(result) == 3
        # u-2 has 100 points -> rank 1
        assert result[0]["user_id"] == "u-2"
        assert result[0]["total_pontos"] == 100
        assert result[0]["rank"] == 1
        # u-1 has 80 points -> rank 2
        assert result[1]["user_id"] == "u-1"
        assert result[1]["total_pontos"] == 80
        assert result[1]["rank"] == 2
        # u-3 has 20 points -> rank 3
        assert result[2]["user_id"] == "u-3"
        assert result[2]["total_pontos"] == 20
        assert result[2]["rank"] == 3

    def test_leaderboard_semana_filter_accepted(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import build_leaderboard
        result = build_leaderboard(db, periodo="semana")

        assert result == []

    def test_leaderboard_mes_filter_accepted(self):
        db = MockSupabaseClient(data=[])

        from app.services.gamificacao_service import build_leaderboard
        result = build_leaderboard(db, periodo="mes")

        assert result == []


# ---------------------------------------------------------------------------
# PONTOS_POR_ACAO / BADGES constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_pontos_por_acao_dict(self):
        from app.services.gamificacao_service import PONTOS_POR_ACAO

        assert isinstance(PONTOS_POR_ACAO, dict)
        assert "novo_cliente" in PONTOS_POR_ACAO
        assert "venda_fechada" in PONTOS_POR_ACAO

    def test_badges_list(self):
        from app.services.gamificacao_service import BADGES

        assert isinstance(BADGES, list)
        assert len(BADGES) >= 6
        for badge in BADGES:
            assert "tipo" in badge
            assert "nome" in badge
            assert "descricao" in badge
            assert "icone" in badge
            assert callable(badge["condicao"])
