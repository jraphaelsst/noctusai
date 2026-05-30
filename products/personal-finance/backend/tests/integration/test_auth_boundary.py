"""
Auth boundary tests for Personal Finance endpoints.

Every protected endpoint must return 401 when called without authentication.
"""
import pytest


class TestAuthBoundaryContas:
    def test_contas_list_401(self, client):
        assert client.raw().get("/api/contas").status_code == 401

    def test_contas_saldos_401(self, client):
        assert client.raw().get("/api/contas/saldos").status_code == 401

    def test_contas_detail_401(self, client):
        assert client.raw().get("/api/contas/fake-id").status_code == 401

    def test_contas_create_401(self, client):
        assert client.raw().post("/api/contas", json={}).status_code == 401

    def test_contas_update_401(self, client):
        assert client.raw().patch("/api/contas/fake-id", json={}).status_code == 401

    def test_contas_delete_401(self, client):
        assert client.raw().delete("/api/contas/fake-id").status_code == 401


class TestAuthBoundaryTransacoes:
    def test_transacoes_list_401(self, client):
        assert client.raw().get("/api/transacoes").status_code == 401

    def test_transacoes_por_categoria_401(self, client):
        assert client.raw().get("/api/transacoes/por-categoria").status_code == 401

    def test_transacoes_detail_401(self, client):
        assert client.raw().get("/api/transacoes/fake-id").status_code == 401

    def test_transacoes_create_401(self, client):
        assert client.raw().post("/api/transacoes", json={}).status_code == 401

    def test_transacoes_update_401(self, client):
        assert client.raw().patch("/api/transacoes/fake-id", json={}).status_code == 401

    def test_transacoes_delete_401(self, client):
        assert client.raw().delete("/api/transacoes/fake-id").status_code == 401


class TestAuthBoundaryCategorias:
    def test_categorias_list_401(self, client):
        assert client.raw().get("/api/categorias").status_code == 401

    def test_categorias_arvore_401(self, client):
        assert client.raw().get("/api/categorias/arvore").status_code == 401

    def test_categorias_detail_401(self, client):
        assert client.raw().get("/api/categorias/fake-id").status_code == 401

    def test_categorias_create_401(self, client):
        assert client.raw().post("/api/categorias", json={}).status_code == 401

    def test_categorias_update_401(self, client):
        assert client.raw().patch("/api/categorias/fake-id", json={}).status_code == 401

    def test_categorias_delete_401(self, client):
        assert client.raw().delete("/api/categorias/fake-id").status_code == 401


class TestAuthBoundaryOrcamentos:
    def test_orcamentos_list_401(self, client):
        assert client.raw().get("/api/orcamentos").status_code == 401

    def test_orcamentos_detail_401(self, client):
        assert client.raw().get("/api/orcamentos/fake-id").status_code == 401

    def test_orcamentos_progresso_401(self, client):
        assert client.raw().get("/api/orcamentos/fake-id/progresso").status_code == 401

    def test_orcamentos_itens_401(self, client):
        assert client.raw().get("/api/orcamentos/fake-id/itens").status_code == 401

    def test_orcamentos_create_401(self, client):
        assert client.raw().post("/api/orcamentos", json={}).status_code == 401

    def test_orcamentos_update_401(self, client):
        assert client.raw().patch("/api/orcamentos/fake-id", json={}).status_code == 401

    def test_orcamentos_delete_401(self, client):
        assert client.raw().delete("/api/orcamentos/fake-id").status_code == 401

    def test_orcamentos_create_item_401(self, client):
        assert client.raw().post("/api/orcamentos/fake-id/itens", json={}).status_code == 401

    def test_orcamentos_update_item_401(self, client):
        assert client.raw().patch("/api/orcamentos/itens/fake-id", json={}).status_code == 401

    def test_orcamentos_delete_item_401(self, client):
        assert client.raw().delete("/api/orcamentos/itens/fake-id").status_code == 401


class TestAuthBoundaryMetas:
    def test_metas_list_401(self, client):
        assert client.raw().get("/api/metas").status_code == 401

    def test_metas_detail_401(self, client):
        assert client.raw().get("/api/metas/fake-id").status_code == 401

    def test_metas_progresso_401(self, client):
        assert client.raw().get("/api/metas/fake-id/progresso").status_code == 401

    def test_metas_create_401(self, client):
        assert client.raw().post("/api/metas", json={}).status_code == 401

    def test_metas_update_401(self, client):
        assert client.raw().patch("/api/metas/fake-id", json={}).status_code == 401

    def test_metas_delete_401(self, client):
        assert client.raw().delete("/api/metas/fake-id").status_code == 401

    def test_metas_contribuicao_401(self, client):
        assert client.raw().post("/api/metas/fake-id/contribuicao", json={}).status_code == 401


class TestAuthBoundaryCarteira:
    def test_carteiras_list_401(self, client):
        assert client.raw().get("/api/carteiras").status_code == 401

    def test_carteiras_detail_401(self, client):
        assert client.raw().get("/api/carteiras/fake-id").status_code == 401

    def test_carteiras_resumo_401(self, client):
        assert client.raw().get("/api/carteiras/fake-id/resumo").status_code == 401

    def test_carteiras_create_401(self, client):
        assert client.raw().post("/api/carteiras", json={}).status_code == 401

    def test_carteiras_update_401(self, client):
        assert client.raw().patch("/api/carteiras/fake-id", json={}).status_code == 401

    def test_carteiras_delete_401(self, client):
        assert client.raw().delete("/api/carteiras/fake-id").status_code == 401

    def test_carteiras_alocacao_401(self, client):
        assert client.raw().post("/api/carteiras/fake-id/alocacao", json={}).status_code == 401


class TestAuthBoundaryAtivos:
    def test_ativos_list_401(self, client):
        assert client.raw().get("/api/ativos").status_code == 401

    def test_ativos_por_carteira_401(self, client):
        assert client.raw().get("/api/ativos/por-carteira/fake-id").status_code == 401

    def test_ativos_detail_401(self, client):
        assert client.raw().get("/api/ativos/fake-id").status_code == 401

    def test_ativos_create_401(self, client):
        assert client.raw().post("/api/ativos", json={}).status_code == 401

    def test_ativos_update_401(self, client):
        assert client.raw().patch("/api/ativos/fake-id", json={}).status_code == 401

    def test_ativos_delete_401(self, client):
        assert client.raw().delete("/api/ativos/fake-id").status_code == 401


class TestAuthBoundaryOperacoes:
    def test_operacoes_list_401(self, client):
        assert client.raw().get("/api/operacoes").status_code == 401

    def test_operacoes_por_ativo_401(self, client):
        assert client.raw().get("/api/operacoes/por-ativo/fake-id").status_code == 401

    def test_operacoes_detail_401(self, client):
        assert client.raw().get("/api/operacoes/fake-id").status_code == 401

    def test_operacoes_create_401(self, client):
        assert client.raw().post("/api/operacoes", json={}).status_code == 401

    def test_operacoes_delete_401(self, client):
        assert client.raw().delete("/api/operacoes/fake-id").status_code == 401


class TestAuthBoundaryWatchlist:
    def test_watchlists_list_401(self, client):
        assert client.raw().get("/api/watchlists").status_code == 401

    def test_watchlists_detail_401(self, client):
        assert client.raw().get("/api/watchlists/fake-id").status_code == 401

    def test_watchlists_create_401(self, client):
        assert client.raw().post("/api/watchlists", json={}).status_code == 401

    def test_watchlists_delete_401(self, client):
        assert client.raw().delete("/api/watchlists/fake-id").status_code == 401

    def test_watchlists_add_item_401(self, client):
        assert client.raw().post("/api/watchlists/fake-id/itens", json={}).status_code == 401

    def test_watchlists_delete_item_401(self, client):
        assert client.raw().delete("/api/watchlists/itens/fake-id").status_code == 401


class TestAuthBoundaryRecorrentes:
    def test_recorrentes_list_401(self, client):
        assert client.raw().get("/api/recorrentes").status_code == 401

    def test_recorrentes_executar_all_401(self, client):
        assert client.raw().post("/api/recorrentes/executar", json={}).status_code == 401

    def test_recorrentes_proximas_401(self, client):
        assert client.raw().get("/api/recorrentes/proximas").status_code == 401

    def test_recorrentes_executar_single_401(self, client):
        assert client.raw().post("/api/recorrentes/fake-id/executar", json={}).status_code == 401

    def test_recorrentes_detail_401(self, client):
        assert client.raw().get("/api/recorrentes/fake-id").status_code == 401

    def test_recorrentes_create_401(self, client):
        assert client.raw().post("/api/recorrentes", json={}).status_code == 401

    def test_recorrentes_update_401(self, client):
        assert client.raw().patch("/api/recorrentes/fake-id", json={}).status_code == 401

    def test_recorrentes_delete_401(self, client):
        assert client.raw().delete("/api/recorrentes/fake-id").status_code == 401


class TestAuthBoundaryPatrimonio:
    def test_patrimonio_atual_401(self, client):
        assert client.raw().get("/api/patrimonio/atual").status_code == 401

    def test_patrimonio_historico_401(self, client):
        assert client.raw().get("/api/patrimonio/historico").status_code == 401

    def test_patrimonio_snapshot_401(self, client):
        assert client.raw().post("/api/patrimonio/snapshot", json={}).status_code == 401


class TestAuthBoundaryRelatorios:
    def test_relatorios_mensal_401(self, client):
        assert client.raw().get("/api/relatorios/mensal").status_code == 401

    def test_relatorios_anual_401(self, client):
        assert client.raw().get("/api/relatorios/anual").status_code == 401

    def test_relatorios_fluxo_caixa_401(self, client):
        assert client.raw().get("/api/relatorios/fluxo-caixa").status_code == 401


class TestAuthBoundaryCotacoes:
    def test_cotacoes_ticker_401(self, client):
        assert client.raw().get("/api/cotacoes/PETR4").status_code == 401

    def test_cotacoes_batch_401(self, client):
        # Valid BatchRequest body (tickers: List[str]) so body-validation passes
        # and the auth dependency is what fires → strict 401 (an empty body would
        # 422 on validation BEFORE auth — the false-green this assertion avoids).
        assert client.raw().post("/api/cotacoes/batch", json={"tickers": ["PETR4"]}).status_code == 401

    def test_cotacoes_atualizar_401(self, client):
        assert client.raw().post("/api/cotacoes/atualizar", json={}).status_code == 401


class TestAuthBoundaryDashboard:
    def test_dashboard_kpis_401(self, client):
        assert client.raw().get("/api/dashboard/kpis").status_code == 401

    def test_dashboard_resumo_401(self, client):
        assert client.raw().get("/api/dashboard/resumo").status_code == 401


class TestAuthBoundaryNotificacoes:
    def test_notificacoes_list_401(self, client):
        assert client.raw().get("/api/notificacoes").status_code == 401

    def test_notificacoes_contagem_401(self, client):
        assert client.raw().get("/api/notificacoes/contagem").status_code == 401

    def test_notificacoes_ler_401(self, client):
        assert client.raw().patch("/api/notificacoes/fake-id/ler", json={}).status_code == 401

    def test_notificacoes_ler_todas_401(self, client):
        assert client.raw().post("/api/notificacoes/ler-todas", json={}).status_code == 401


class TestAuthBoundaryTeam:
    def test_team_list_401(self, client):
        assert client.raw().get("/api/team").status_code == 401

    def test_team_invite_401(self, client):
        assert client.raw().post("/api/team/invite", json={}).status_code == 401

    def test_team_invitations_list_401(self, client):
        assert client.raw().get("/api/team/invitations").status_code == 401

    def test_team_cancel_invitation_401(self, client):
        assert client.raw().delete("/api/team/invitations/fake-id").status_code == 401

    def test_team_remove_member_401(self, client):
        assert client.raw().delete("/api/team/fake-id").status_code == 401
