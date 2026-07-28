"""
Tests for the Processos de Venda router — /api/processos-venda

The post-proposal execution board. A processo is spawned by the accept-proposal
seam (see `test_negociacoes_venda_router.TestAceitarProposta`), never created
directly — this router deliberately exposes no bare create endpoint.
"""
import pytest

# Stages are DB rows since migration 042, so tests seed them like any other
# table. `slug` still carries the old vocabulary — the defaults 042 installs are
# exactly the enum values it replaced — but the CARDS reference stage IDs, which
# is what makes a rename safe.
PROC_STAGES = [
    {"id": f"ps{i}", "org_id": "org-1", "pipeline": "processos_venda", "slug": slug,
     "label": label, "cor": "secondary", "posicao": i,
     "papel": "final" if slug == "nota_fiscal" else None, "ativo": True}
    for i, (slug, label) in enumerate([
        ("elaboracao_contrato", "Elaboração do Contrato"),
        ("analise_partes", "Análise das Partes"),
        ("revisao_contrato", "Revisão do Contrato"),
        ("assinatura", "Assinatura"),
        ("financiamento_escritura", "Financiamento & Escritura"),
        ("finalizacao", "Finalização"),
        ("entrega_chaves", "Entrega das Chaves"),
        ("nota_fiscal", "Nota Fiscal"),
    ])
]
STAGE_ID = {s["slug"]: s["id"] for s in PROC_STAGES}

# A stage belonging to the OTHER board — used to prove the pipelines stay
# isolated now that both read from one table.
FUNIL_STAGE = {"id": "fs2", "org_id": "org-1", "pipeline": "funil", "slug": "proposta",
               "label": "Proposta", "cor": "primary", "posicao": 2,
               "papel": "proposta_aceite", "ativo": True}


@pytest.fixture(autouse=True)
def _seed_stages(client):
    client._mock_supabase.set_table_data("pipeline_stages", PROC_STAGES + [FUNIL_STAGE])
    client._mock_supabase.set_table_data("pipeline_movimentos", [])
    return client


def _processo(pid="p1", etapa="elaboracao_contrato", valor=0, pos=0, arquivado=False, **over):
    row = {
        "id": pid,
        "cliente_id": "cli-1",
        "negociacao_venda_id": f"n-{pid}",
        "corretor_id": "user-1",
        "etapa": etapa,
        "etapa_id": STAGE_ID[etapa],
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
        """Every CONFIGURED stage is emitted — a board that drops empty
        columns is unusable. The count is no longer fixed at 8; it is whatever
        the org has configured, which here is the 8 seeded defaults."""
        client._mock_supabase.set_table_data("processos_venda", [
            _processo("p1", etapa="assinatura"),
        ])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        # Columns are keyed by stage ID, and carry their definition so the UI
        # needs no second lookup to render a label or colour.
        assert [c["etapa"] for c in colunas] == [s["id"] for s in PROC_STAGES]
        assert [c["stage"]["slug"] for c in colunas] == [s["slug"] for s in PROC_STAGES]
        assert colunas[0]["stage"]["label"] == "Elaboração do Contrato"

    def test_groups_and_totals(self, client):
        client._mock_supabase.set_table_data("processos_venda", [
            _processo("p1", etapa="assinatura", valor=100000, pos=0),
            _processo("p2", etapa="assinatura", valor=50000, pos=1),
            _processo("p3", etapa="nota_fiscal", valor=25000),
        ])
        resp = client.get("/api/processos-venda")
        assert resp.status_code == 200
        colunas = {c["stage"]["slug"]: c for c in resp.json()["data"]}
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
                           json={"para_etapa_id": STAGE_ID["revisao_contrato"]})
        assert resp.status_code == 200

    def test_move_writes_history(self, client):
        """THE regression guard for the defect that motivated the extraction.

        This board shipped with no audit trail at all because its `mover-etapa`
        was a fork of the Funil's that had lost the history write. It now shares
        one implementation, so the row is written here for the same reason it is
        written there.
        """
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa_id": STAGE_ID["revisao_contrato"]})
        assert resp.status_code == 200
        rows = client._mock_supabase.table("pipeline_movimentos").inserted_payloads
        assert len(rows) == 1
        assert rows[0]["pipeline"] == "processos_venda"
        assert rows[0]["entidade_id"] == "p1"
        assert rows[0]["de_etapa_id"] == STAGE_ID["elaboracao_contrato"]
        assert rows[0]["para_etapa_id"] == STAGE_ID["revisao_contrato"]

    def test_move_rejects_funil_stage(self, client):
        """The two boards stay isolated even though both read one stage table —
        a Funil stage id must not be a legal destination here."""
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa_id": FUNIL_STAGE["id"]})
        assert resp.status_code == 404

    def test_move_rejects_unknown_stage(self, client):
        client._mock_supabase.set_table_data("processos_venda", _processo("p1"))
        resp = client.post("/api/processos-venda/p1/mover-etapa",
                           json={"para_etapa_id": "nao-existe"})
        assert resp.status_code == 404


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
        ("post", "/api/processos-venda/p1/mover-etapa", {"para_etapa_id": "ps3"}),
        ("get", "/api/processos-venda/etapas", None),
        ("post", "/api/processos-venda/etapas", {"label": "Nova"}),
        ("patch", "/api/processos-venda/etapas/ps1", {"label": "Nova"}),
        ("delete", "/api/processos-venda/etapas/ps1", None),
        ("post", "/api/processos-venda/etapas/reordenar", {"ordem": ["ps1"]}),
        ("post", "/api/processos-venda/p1/arquivar", None),
    ])
    def test_requires_auth(self, client, method, path, payload):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        fn = getattr(tc, method)
        resp = fn(path, json=payload) if payload is not None else fn(path)
        assert resp.status_code == 401
