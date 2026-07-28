"""
Tests for the Negociações de Venda router — /api/negociacoes-venda

Covers the deal entity's CRUD, the stage-move + history write, and the
accept-proposal seam that hands a deal over to Processos de Venda.

NOT `/api/negociacoes` — that is the permuta router (`test_negociacoes_router`).
"""
import pytest


def _negociacao(nid="n1", etapa="proposta", status="aberta", **over):
    row = {
        "id": nid,
        "cliente_id": "cli-1",
        "corretor_id": "user-1",
        "titulo": "Apartamento Centro",
        "etapa": etapa,
        "status": status,
        "valor_estimado": 250000,
        "probabilidade": 60,
        "kanban_pos": 0,
        "arquivado": False,
        "closed_at": None,
    }
    row.update(over)
    return row


class TestListarNegociacoes:
    def test_list(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1"), _negociacao("n2"),
        ])
        resp = client.get("/api/negociacoes-venda")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_dto_strips_unknown_columns(self, client):
        """The DTO whitelist is a real boundary, not documentation."""
        client._mock_supabase.set_table_data("negociacoes_venda", [
            _negociacao("n1", segredo_interno="não deve vazar"),
        ])
        resp = client.get("/api/negociacoes-venda")
        assert resp.status_code == 200
        assert "segredo_interno" not in resp.json()["data"][0]


class TestCriarNegociacao:
    def test_create_defaults_corretor_to_creator(self, client):
        """Not to the agency — an agency-owned deal is invisible to its creator
        under `auth.uid() = corretor_id` RLS."""
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("new-n"))
        resp = client.post("/api/negociacoes-venda", json={"cliente_id": "cli-1"})
        assert resp.status_code == 200

    def test_create_rejects_invalid_etapa(self, client):
        resp = client.post("/api/negociacoes-venda", json={
            "cliente_id": "cli-1", "etapa": "etapa-que-nao-existe",
        })
        assert resp.status_code == 400

    def test_create_rejects_unknown_field(self, client):
        """StrictHttpModel must refuse silently-dropped fields."""
        resp = client.post("/api/negociacoes-venda", json={
            "cliente_id": "cli-1", "campo_inventado": "x",
        })
        assert resp.status_code == 422


class TestMoverEtapa:
    def test_move_writes_history(self, client):
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("n1", etapa="qualificacao"))
        client._mock_supabase.set_table_data("funil_movimentos", [])
        resp = client.post("/api/negociacoes-venda/n1/mover-etapa",
                           json={"para_etapa": "visitas"})
        assert resp.status_code == 200

    def test_move_rejects_invalid_etapa(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", _negociacao("n1"))
        resp = client.post("/api/negociacoes-venda/n1/mover-etapa",
                           json={"para_etapa": "nao-existe"})
        assert resp.status_code == 400

    def test_move_refuses_closed_deal(self, client):
        """A closed deal is off the board; moving it would resurrect it into a
        stage while its status still says closed."""
        client._mock_supabase.set_table_data(
            "negociacoes_venda",
            _negociacao("n1", status="aceita", closed_at="2026-07-27T00:00:00Z"))
        resp = client.post("/api/negociacoes-venda/n1/mover-etapa",
                           json={"para_etapa": "visitas"})
        assert resp.status_code == 409


class TestAceitarProposta:
    def test_accept_from_proposta_spawns_processo(self, client):
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("n1", etapa="proposta"))
        client._mock_supabase.set_table_data("processos_venda", [])
        resp = client.post("/api/negociacoes-venda/n1/aceitar-proposta")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["already_accepted"] is False
        assert body["processo"] is not None

    def test_accept_refused_outside_proposta_stage(self, client):
        """Accepting is what ENDS the negotiation — it cannot fire from a stage
        where no proposal is on the table (user correction: the seam is the
        `proposta` column, not `fechado`)."""
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("n1", etapa="qualificacao"))
        client._mock_supabase.set_table_data("processos_venda", [])
        resp = client.post("/api/negociacoes-venda/n1/aceitar-proposta")
        assert resp.status_code == 409

    def test_accept_refused_from_fechado(self, client):
        """`fechado` is a Funil-INTERNAL terminal column, explicitly NOT the
        acceptance trigger."""
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("n1", etapa="fechado"))
        client._mock_supabase.set_table_data("processos_venda", [])
        resp = client.post("/api/negociacoes-venda/n1/aceitar-proposta")
        assert resp.status_code == 409

    def test_second_accept_is_idempotent(self, client):
        """A double-clicked button must yield ONE processo, and the second call
        must succeed (the caller asked for this deal to be in execution, and it
        is) rather than erroring."""
        client._mock_supabase.set_table_data(
            "negociacoes_venda", _negociacao("n1", etapa="proposta"))
        client._mock_supabase.set_table_data("processos_venda", [{
            "id": "p1", "cliente_id": "cli-1", "negociacao_venda_id": "n1",
            "corretor_id": "user-1", "etapa": "elaboracao_contrato",
            "valor": 250000, "kanban_pos": 0, "arquivado": False,
        }])
        resp = client.post("/api/negociacoes-venda/n1/aceitar-proposta")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["already_accepted"] is True
        assert body["processo"]["id"] == "p1"


class TestPerderNegociacao:
    def test_perder(self, client):
        client._mock_supabase.set_table_data("negociacoes_venda", _negociacao("n1"))
        resp = client.post("/api/negociacoes-venda/n1/perder", json={"motivo": "preço"})
        assert resp.status_code == 200

    def test_perder_refuses_closed(self, client):
        client._mock_supabase.set_table_data(
            "negociacoes_venda",
            _negociacao("n1", status="perdida", closed_at="2026-07-27T00:00:00Z"))
        resp = client.post("/api/negociacoes-venda/n1/perder", json={})
        assert resp.status_code == 409


class TestNoAuth:
    """Every route must refuse an unauthenticated caller with 401.

    Asserted as strict `== 401` (never `in (401, 404)`): the non-401 branch
    goes green on a route that does not exist at all, or one that validates
    its body before authenticating — both false greens.
    """

    @pytest.mark.parametrize("method,path,payload", [
        ("get", "/api/negociacoes-venda", None),
        ("post", "/api/negociacoes-venda", {"cliente_id": "cli-1"}),
        ("get", "/api/negociacoes-venda/n1", None),
        ("patch", "/api/negociacoes-venda/n1", {"titulo": "x"}),
        ("post", "/api/negociacoes-venda/n1/mover-etapa", {"para_etapa": "visitas"}),
        ("post", "/api/negociacoes-venda/n1/aceitar-proposta", None),
        ("post", "/api/negociacoes-venda/n1/perder", {}),
        ("delete", "/api/negociacoes-venda/n1", None),
    ])
    def test_requires_auth(self, client, method, path, payload):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        fn = getattr(tc, method)
        resp = fn(path, json=payload) if payload is not None else fn(path)
        assert resp.status_code == 401
