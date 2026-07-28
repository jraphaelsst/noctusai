"""
Tests for Funil (pipeline/kanban) router — /api/funil

RESHAPED 2026-07-27 (roadmap P1.5.4): the board's cards are NEGOCIAÇÕES, not
clientes, so these fixtures seed `negociacoes_venda` with a nested `cliente`
join object rather than seeding `clientes` directly. The contract changed by
design — a cliente can hold several concurrent deals and the old
`clientes.etapa_atual` grouping could never show the second one.

NOTE (inherited 2026-05-20, still true): the router filters `arquivado=False`
and `status='aberta'` by default, and the mock predicate evaluator compares
`row.get(col) == value`, so a row missing either field is filtered out
(None != False). Fixtures must set both explicitly.
"""
import pytest


def _negociacao(
    nid, cliente_nome, etapa="qualificacao", valor=0, pos=0,
    status="aberta", arquivado=False, origem=None, titulo=None,
):
    """Build a negociação row in the shape `NEGOCIACAO_SELECT` returns."""
    return {
        "id": nid,
        "cliente_id": f"cli-{nid}",
        "corretor_id": "user-1",
        "titulo": titulo,
        "etapa": etapa,
        "status": status,
        "valor_estimado": valor,
        "probabilidade": 10,
        "kanban_pos": pos,
        "arquivado": arquivado,
        "closed_at": None,
        "cliente": {
            "id": f"cli-{nid}", "nome": cliente_nome,
            "email": None, "telefone": None, "origem": origem,
        },
        "corretor": {"id": "user-1", "nome": "Corretor", "email": None},
    }


class TestGetFunil:
    def test_get_funil(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "João", etapa="qualificacao", valor=100000),
            _negociacao("n2", "Maria", etapa="proposta", valor=200000),
        ])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert len(colunas) == 5  # 5 etapas
        etapas = [c["etapa"] for c in colunas]
        assert "qualificacao" in etapas
        assert "proposta" in etapas

    def test_funil_empty(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert all(c["total"] == 0 for c in colunas)

    def test_every_stage_emitted_even_when_empty(self, client):
        """A kanban that drops empty columns is unusable — pin all 5 always."""
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "Só um", etapa="visitas"),
        ])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert [c["etapa"] for c in colunas] == [
            "qualificacao", "visitas", "proposta", "negociacao", "fechado",
        ]


class TestFunilGrouping:
    def test_funil_grouping_correct(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "A", etapa="qualificacao", valor=50000, pos=0),
            _negociacao("n2", "B", etapa="qualificacao", valor=100000, pos=1),
        ])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        qualificacao = next(c for c in colunas if c["etapa"] == "qualificacao")
        assert qualificacao["total"] == 2
        assert qualificacao["valorTotal"] == 150000

    def test_one_cliente_two_deals_two_columns(self, client):
        """THE acceptance test for Phase 1.5.

        One cliente, two concurrent deals at different stages, must render as
        TWO cards in TWO columns. This is precisely what the old
        clientes.etapa_atual shape could not represent.
        """
        shared = {
            "id": "cli-shared", "nome": "Cliente Multi",
            "email": None, "telefone": None, "origem": None,
        }
        rows = [
            _negociacao("n1", "Cliente Multi", etapa="qualificacao", valor=10000),
            _negociacao("n2", "Cliente Multi", etapa="proposta", valor=20000),
        ]
        for r in rows:
            r["cliente_id"] = "cli-shared"
            r["cliente"] = shared
        client._mock_supabase.set_table_data("negociacoes_venda", rows)

        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = {c["etapa"]: c for c in resp.json()["data"]}
        assert colunas["qualificacao"]["total"] == 1
        assert colunas["proposta"]["total"] == 1
        assert colunas["qualificacao"]["cards"][0]["cliente_id"] == "cli-shared"
        assert colunas["proposta"]["cards"][0]["cliente_id"] == "cli-shared"


class TestFunilSearch:
    def test_funil_search_filters(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "João Silva"),
            _negociacao("n2", "Maria Santos"),
        ])
        resp = client.get("/api/funil?busca=joão")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        total_cards = sum(c["total"] for c in colunas)
        assert total_cards == 1

    def test_search_matches_deal_title_not_only_cliente(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "João Silva", titulo="Apartamento Centro"),
            _negociacao("n2", "Maria Santos", titulo="Casa Praia"),
        ])
        resp = client.get("/api/funil?busca=praia")
        assert resp.status_code == 200
        total_cards = sum(c["total"] for c in resp.json()["data"])
        assert total_cards == 1


class TestFunilOrigemFilter:
    def test_origem_filters_on_nested_cliente(self, client):
        """`origem` lives on the CLIENTE, so it filters the nested join."""
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", "A", origem="website"),
            _negociacao("n2", "B", origem="indicacao"),
        ])
        resp = client.get("/api/funil?origem=website")
        assert resp.status_code == 200
        total_cards = sum(c["total"] for c in resp.json()["data"])
        assert total_cards == 1
