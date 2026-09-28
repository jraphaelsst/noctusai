"""`POST /api/portal/assinatura/cancelar` — projects/ninho-vazio/CONTRACT.md
§Member portal (owned by slice BE-B).

Router-level tests cover rows with no gateway subscription (nothing to call
remotely); the strict-gateway failure path (502, local row untouched) is
covered at the service level with the DI factory, below, so no test here can
ever reach a real gateway with an ambient key.
"""
import asyncio

from noctusai_lib.testing import MockSupabaseClient

from app.services.assinaturas_service import (
    AssinaturasService,
    AssinaturasServiceError,
    CancelamentoGatewayFalhou,
)
from app.services.ciclo_assinatura import GatewayNaoConfigurado
from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role

MEMBRO_1 = "11111111-1111-1111-1111-111111111111"
OUTRO_MEMBRO = "55555555-5555-5555-5555-555555555555"
PLANO_1 = "22222222-2222-2222-2222-222222222222"
SUB_1 = "33333333-3333-3333-3333-333333333333"
SUB_OUTRA = "44444444-4444-4444-4444-444444444444"

URL = "/api/portal/assinatura/cancelar"


def _membro(id_=MEMBRO_1, user_id=TEST_USER_ID) -> dict:
    return {
        "id": id_, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com", "telefone": None,
        "status": "ativo", "plano_id": PLANO_1, "origem": "cadastro", "tags": [],
        "user_id": user_id, "observacoes": None, "entrou_em": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _assinatura(id_=SUB_1, membro_id=MEMBRO_1, estado="ativa", **over) -> dict:
    base = {
        "id": id_, "org_id": ORG_UUID, "membro_id": membro_id, "plano_id": PLANO_1,
        "gateway": "asaas", "assinatura_externa_id": None, "cliente_externo_id": None,
        "estado": estado, "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": None, "ativa_em": "2026-09-01T00:00:00+00:00", "cancelada_em": None,
        "inadimplente_desde": None, "carencia_ate": None,
        "pago_ate": "2026-11-05T03:00:00+00:00", "proxima_cobranca": "2026-11-05",
        "expirada_em": None, "cancelamento_solicitado_por": None, "cancelamento_motivo": None,
        "gateway_cancelamento_pendente": False,
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _seed_membro(client, assinaturas):
    seed_community_role(client, org_role="membro")
    client.mock_supabase.set_table_data("membros", [_membro(), _membro(OUTRO_MEMBRO, None)])
    client.mock_supabase.set_table_data("assinaturas", assinaturas)
    client.mock_supabase.set_table_data("planos", [])
    client.mock_supabase.set_table_data("membro_eventos", [])


class TestAuthBoundary:
    def test_no_auth_401(self, client):
        assert client.raw().post(URL, json={"motivo": None}).status_code == 401

    def test_staff_403(self, client):
        seed_community_role(client, org_role="admin")
        assert client.post(URL, json={"motivo": None}).status_code == 403


class TestCancel:
    def test_member_cancels_own_subscription(self, client):
        _seed_membro(client, [_assinatura(), _assinatura(SUB_OUTRA, OUTRO_MEMBRO)])
        resp = client.post(URL, json={"motivo": "Vou dar uma pausa"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "id", "estado", "metodo", "proxima_cobranca", "pago_ate", "carencia_ate",
            "cancelada_em", "gateway",
        }
        assert body["id"] == SUB_1
        assert body["estado"] == "cancelada"
        assert body["cancelada_em"] is not None

        rows = {
            r["id"]: r for r in client.mock_supabase.table("assinaturas").select("*").execute().data
        }
        assert rows[SUB_1]["cancelamento_solicitado_por"] == "membro"
        assert rows[SUB_1]["cancelamento_motivo"] == "Vou dar uma pausa"
        assert rows[SUB_OUTRA]["estado"] == "ativa"  # never another member's row
        # keeps the plan until pago_ate
        membro = client.mock_supabase.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "ativo" and membro["plano_id"] == PLANO_1
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert [e["tipo"] for e in eventos] == ["assinatura"]

    def test_no_current_paid_subscription_404(self, client):
        _seed_membro(client, [_assinatura(estado="expirada"), _assinatura(SUB_OUTRA, OUTRO_MEMBRO)])
        resp = client.post(URL, json={"motivo": None})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Você não tem assinatura ativa."

    def test_grace_subscription_can_be_cancelled(self, client):
        _seed_membro(client, [_assinatura(estado="carencia")])
        resp = client.post(URL, json={})
        assert resp.status_code == 200
        assert resp.json()["estado"] == "cancelada"

    def test_motivo_too_long_and_extra_fields_422(self, client):
        _seed_membro(client, [_assinatura()])
        assert client.post(URL, json={"motivo": "x" * 501}).status_code == 422
        assert client.post(URL, json={"motivo": None, "assinatura_id": SUB_OUTRA}).status_code == 422


class TestStrictGatewayAtServiceLevel:
    def test_missing_key_refuses_and_leaves_the_row_untouched(self):
        client = MockSupabaseClient(schema="community")
        client.set_table_data("assinaturas", [_assinatura(assinatura_externa_id="sub_asaas_1")])
        client.set_table_data("membro_eventos", [])

        def _sem_chave(_gateway):
            raise GatewayNaoConfigurado("Chave do Asaas não configurada.")

        service = AssinaturasService(client, org_id=ORG_UUID, gateway_factory=_sem_chave)
        try:
            asyncio.run(service.cancelar(assinatura_id=SUB_1, motivo=None, solicitado_por="membro"))
            assert False, "expected CancelamentoGatewayFalhou"
        except CancelamentoGatewayFalhou as exc:
            assert exc.status_code == 502
        row = client.table("assinaturas").select("*").eq("id", SUB_1).maybe_single().execute().data
        assert row["estado"] == "ativa"
        assert client.table("membro_eventos").select("*").execute().data == []

    def test_already_ended_subscription_409(self):
        client = MockSupabaseClient(schema="community")
        client.set_table_data("assinaturas", [_assinatura(estado="expirada")])
        service = AssinaturasService(client, org_id=ORG_UUID)
        try:
            asyncio.run(service.cancelar(assinatura_id=SUB_1, motivo="x"))
            assert False, "expected AssinaturasServiceError"
        except AssinaturasServiceError as exc:
            assert exc.status_code == 409
            assert not isinstance(exc, CancelamentoGatewayFalhou)
