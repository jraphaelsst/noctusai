"""Routers of slice BE-B — projects/ninho-vazio/CONTRACT.md §Billing — slice
BE-B: `/api/cobranca/*`, `POST /api/planos/padrao`, and the Assinaturas
list's new fields + `carencia`/`expirada` filters.
"""
from tests.conftest import ORG_UUID, seed_community_role

MEMBRO_1 = "11111111-1111-1111-1111-111111111111"
PLANO_1 = "22222222-2222-2222-2222-222222222222"
SUB_1 = "33333333-3333-3333-3333-333333333333"
SUB_2 = "44444444-4444-4444-4444-444444444444"


def _assinatura(id_, estado, **over) -> dict:
    base = {
        "id": id_, "org_id": ORG_UUID, "membro_id": MEMBRO_1, "plano_id": PLANO_1,
        "gateway": "asaas", "assinatura_externa_id": None, "cliente_externo_id": None,
        "estado": estado, "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": None, "ativa_em": None, "cancelada_em": None,
        "inadimplente_desde": None, "carencia_ate": None, "pago_ate": None,
        "proxima_cobranca": None, "expirada_em": None, "cancelamento_solicitado_por": None,
        "cancelamento_motivo": None, "gateway_cancelamento_pendente": False,
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestAuthBoundary:
    def test_get_configuracoes_401(self, client):
        assert client.raw().get("/api/cobranca/configuracoes").status_code == 401

    def test_put_configuracoes_401(self, client):
        resp = client.raw().put(
            "/api/cobranca/configuracoes", json={"dias_carencia": 5, "automacoes_ativas": True},
        )
        assert resp.status_code == 401

    def test_executar_rotina_401(self, client):
        assert client.raw().post("/api/cobranca/executar-rotina").status_code == 401

    def test_planos_padrao_401(self, client):
        assert client.raw().post("/api/planos/padrao").status_code == 401


class TestConfiguracoes:
    def test_moderador_reads_defaults_created_on_first_read(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("configuracoes_cobranca", [])
        resp = client.get("/api/cobranca/configuracoes")
        assert resp.status_code == 200
        assert resp.json() == {"dias_carencia": 5, "automacoes_ativas": True}

    def test_moderador_cannot_write(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.put(
            "/api/cobranca/configuracoes", json={"dias_carencia": 3, "automacoes_ativas": True},
        )
        assert resp.status_code == 403

    def test_membro_is_refused(self, client):
        seed_community_role(client, org_role="membro")
        assert client.get("/api/cobranca/configuracoes").status_code == 403

    def test_admin_saves(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("configuracoes_cobranca", [])
        resp = client.put(
            "/api/cobranca/configuracoes", json={"dias_carencia": 10, "automacoes_ativas": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"dias_carencia": 10, "automacoes_ativas": False}

    def test_out_of_range_and_extra_fields_422(self, client):
        seed_community_role(client, org_role="admin")
        too_long = client.put(
            "/api/cobranca/configuracoes", json={"dias_carencia": 61, "automacoes_ativas": True},
        )
        assert too_long.status_code == 422
        extra = client.put(
            "/api/cobranca/configuracoes",
            json={"dias_carencia": 5, "automacoes_ativas": True, "x": 1},
        )
        assert extra.status_code == 422


class TestExecutarRotina:
    def test_moderador_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.post("/api/cobranca/executar-rotina").status_code == 403

    def test_admin_gets_the_report_shape(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("configuracoes_cobranca", [
            {"org_id": ORG_UUID, "dias_carencia": 5, "automacoes_ativas": False},
        ])
        resp = client.post("/api/cobranca/executar-rotina")
        assert resp.status_code == 200
        relatorios = resp.json()["relatorios"]
        assert [r["nome"] for r in relatorios] == [
            "cancelamentos_pendentes_gateway", "carencia_expirada", "fim_do_periodo_pago",
        ]
        assert relatorios[0] == {
            "nome": "cancelamentos_pendentes_gateway", "pulado": True,
            "examinadas": 0, "alteradas": [], "erros": [],
        }


class TestPlanosPadrao:
    def test_creates_missing_tiers_then_is_idempotent(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("planos", [{
            "id": PLANO_1, "org_id": ORG_UUID, "nome": "Gratuito", "descricao": None,
            "preco_centavos": 0, "ciclo": "mensal", "entitlements": {}, "ativo": True,
            "ordem": 0, "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        resp = client.post("/api/planos/padrao")
        assert resp.status_code == 200
        assert resp.json() == {"criados": ["Ouvinte", "Premium"], "existentes": ["Gratuito"]}

        planos = {
            p["nome"]: p
            for p in client.mock_supabase.table("planos").select("*").execute().data
        }
        assert planos["Ouvinte"]["preco_centavos"] == 700
        assert planos["Ouvinte"]["entitlements"]["grupoterapia"] == "ouvir"
        assert planos["Ouvinte"]["ordem"] == 1
        assert planos["Premium"]["preco_centavos"] == 2700
        assert planos["Premium"]["entitlements"]["grupoterapia"] == "falar"
        assert planos["Premium"]["ciclo"] == "mensal"

        again = client.post("/api/planos/padrao")
        assert again.json() == {"criados": [], "existentes": ["Gratuito", "Ouvinte", "Premium"]}

    def test_moderador_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.post("/api/planos/padrao").status_code == 403


class TestAssinaturasListBilling:
    def _seed(self, client):
        client.mock_supabase.set_table_data("assinaturas", [
            _assinatura(
                SUB_1, "carencia", inadimplente_desde="2026-10-01T00:00:00+00:00",
                carencia_ate="2026-10-06T00:00:00+00:00", pago_ate="2026-10-01T03:00:00+00:00",
                proxima_cobranca="2026-10-01",
            ),
            _assinatura(SUB_2, "expirada", expirada_em="2026-10-07T00:00:00+00:00"),
        ])
        client.mock_supabase.set_table_data("membros", [])
        client.mock_supabase.set_table_data("planos", [])

    def test_carencia_filter_and_new_fields(self, client):
        seed_community_role(client, org_role="admin")
        self._seed(client)
        resp = client.get("/api/assinaturas", params={"estado": "carencia"})
        assert resp.status_code == 200
        (item,) = resp.json()["items"]
        assert item["id"] == SUB_1
        assert item["carencia_ate"].startswith("2026-10-06")
        assert item["inadimplente_desde"].startswith("2026-10-01")
        assert item["proxima_cobranca"] == "2026-10-01"
        for key in ("pago_ate", "expirada_em", "cancelamento_solicitado_por", "cancelamento_motivo"):
            assert key in item

    def test_expirada_filter(self, client):
        seed_community_role(client, org_role="admin")
        self._seed(client)
        resp = client.get("/api/assinaturas", params={"estado": "expirada"})
        assert [i["id"] for i in resp.json()["items"]] == [SUB_2]

    def test_unknown_estado_422(self, client):
        seed_community_role(client, org_role="admin")
        self._seed(client)
        assert client.get("/api/assinaturas", params={"estado": "sumida"}).status_code == 422
