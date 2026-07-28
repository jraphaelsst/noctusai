"""
Tests for the Processos de Venda router — /api/processos-venda

The post-proposal execution board. A processo is spawned by the accept-proposal
seam (see `test_negociacoes_venda_router.TestAceitarProposta`), never created
directly — this router deliberately exposes no bare create endpoint.
"""
import pytest


def _processo(pid="p1", etapa="elaboracao_contrato", valor=0, pos=0, arquivado=False, **over):
    row = {
        "id": pid,
        "cliente_id": "cli-1",
        "negociacao_venda_id": f"n-{pid}",
        "corretor_id": "user-1",
        "etapa": etapa,
        "valor": valor,
        "observacoes": None,
        "kanban_pos": pos,
        "arquivado": arquivado,
        "cliente": {"id": "cli-1", "nome": "João", "email": None, "telefone": None},
        "corretor": {"id": "user-1", "nome": "Corretor", "email": None},
        "negociacao": {
            "id": f"n-{pid}", "titulo": "Apartamento Centro",
            "valor_estimado": valor, "closed_at": None,
        },
    }
    row.update(over)
    return row


class TestBoard:
    def test_returns_all_eight_stages(self, client):
        """The 8 stages are fixed and always emitted — a board that drops empty
        columns is unusable."""
        client._mock_supabase.set_table_data("processos_venda", [
            _processo("p1", etapa="assinatura"),
        ])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert [c["etapa"] for c in colunas] == [
            "elaboracao_contrato",
            "analise_partes",
            "revisao_contrato",
            "assinatura",
            "financiamento_escritura",
            "finalizacao",
            "entrega_chaves",
            "nota_fiscal",
        ]

    def test_groups_and_totals(self, client):
        client._mock_supabase.set_table_data("processos_venda", [
            _processo("p1", etapa="assinatura", valor=100000, pos=0),
            _processo("p2", etapa="assinatura", valor=50000, pos=1),
            _processo("p3", etapa="nota_fiscal", valor=25000),
        ])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        colunas = {c["etapa"]: c for c in resp.json()["data"]}
        assert colunas["assinatura"]["total"] == 2
        assert colunas["assinatura"]["valorTotal"] == 150000
        assert colunas["nota_fiscal"]["total"] == 1

    def test_empty_board_is_not_an_error(self, client):
        client._mock_supabase.set_table_data("processos_venda", [])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        assert all(c["total"] == 0 for c in resp.json()["data"])

    def test_dto_strips_unknown_columns(self, client):
        client._mock_supabase.set_table_data("processos_venda", [
            _processo("p1", coluna_interna="não deve vazar"),
        ])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        cards = [c for col in resp.json()["data"] for c in col["cards"]]
        assert cards and "coluna_interna" not in cards[0]


class TestNoCreateEndpoint:
    def test_post_root_is_not_routable(self, client):
        """A processo without the deal it came from has no provenance, so there
        is deliberately no bare create."""
        resp = client.post("/api/processos-venda", json={"cliente_id": "cli-1"})
        assert resp.status_code == 405


class TestMoverEtapa:
    def test_move(self, client):
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa": "revisao_contrato"})
        assert resp.status_code == 200

    def test_move_rejects_funil_stage(self, client):
        """The two boards have DIFFERENT vocabularies — a Funil stage must not
        be accepted here just because it is a valid stage somewhere."""
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa": "proposta"})
        assert resp.status_code == 400

    def test_move_rejects_invalid_etapa(self, client):
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa": "nao-existe"})
        assert resp.status_code == 400


class TestArquivar:
    def test_archive_toggle(self, client):
        """`nota_fiscal` is terminal, so archiving is the only way the last
        column stays finite."""
        client._mock_supabase.set_table_data(
            "processos_venda", _processo("p1", etapa="nota_fiscal"))
        resp = client.post("/api/processos-venda/p1/arquivar")
        assert resp.status_code == 200


class TestUpdate:
    def test_patch_rejects_unknown_field(self, client):
        resp = client.patch("/api/processos-venda/p1", json={"campo_inventado": "x"})
        assert resp.status_code == 422

    def test_patch_empty_body_rejected(self, client):
        resp = client.patch("/api/processos-venda/p1", json={})
        assert resp.status_code == 400


class TestNoAuth:
    """Strict `== 401` — see the note in test_negociacoes_venda_router."""

    @pytest.mark.parametrize("method,path,payload", [
        ("get", "/api/processos-venda", None),
        ("get", "/api/processos-venda/lista", None),
        ("get", "/api/processos-venda/p1", None),
        ("patch", "/api/processos-venda/p1", {"valor": 1}),
        ("post", "/api/processos-venda/p1/mover-etapa", {"para_etapa": "assinatura"}),
        ("post", "/api/processos-venda/p1/arquivar", None),
    ])
    def test_requires_auth(self, client, method, path, payload):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        fn = getattr(tc, method)
        resp = fn(path, json=payload) if payload is not None else fn(path)
        assert resp.status_code == 401
