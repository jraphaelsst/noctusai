"""Tests for `checkout_router` — contract §Checkout. PUBLIC, no auth
header needed (`client.raw()`), org via `seed_public_license`.
"""
from tests.conftest import ORG_UUID, seed_public_license

PLANO_1 = "11111111-1111-1111-1111-111111111111"


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_1, "org_id": ORG_UUID, "nome": "Círculo", "descricao": None,
        "preco_centavos": 9900, "ciclo": "mensal",
        "entitlements": {"feed": True, "forum": True, "chat": True, "eventos": True,
                         "conteudo_ids": [], "grupos_whatsapp": [], "conteudo_todos": False},
        "ativo": True, "ordem": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _gateway_ref_row(gateway: str, **over) -> dict:
    base = {
        "id": f"ref-{gateway}", "org_id": ORG_UUID, "plano_id": PLANO_1, "gateway": gateway,
        "ref_externo": "price_123" if gateway == "stripe" else "asaas-plan-1",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _payload(**over) -> dict:
    base = {
        "plano_id": PLANO_1, "metodo": "pix", "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "cpf": "12345678901", "turnstile_token": "tok",
    }
    base.update(over)
    return base


def _seed(client, *, ref_rows=None):
    seed_public_license(client)
    client.mock_supabase.set_table_data("planos", [_plano_row()])
    client.mock_supabase.set_table_data(
        "plano_gateway_refs",
        ref_rows if ref_rows is not None else [_gateway_ref_row("stripe"), _gateway_ref_row("asaas")],
    )


class TestCheckoutPublic:
    def test_no_auth_header_required(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json=_payload())
        assert resp.status_code == 201

    def test_pix_checkout_201_shape(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json=_payload(metodo="pix"))
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {"checkout_url", "assinatura_id", "membro_id", "pix_qr", "status"}
        assert body["checkout_url"]
        assert body["pix_qr"]["payload"]
        assert body["pix_qr"]["imagem_base64"]

    def test_cartao_with_cpf_422(self, client):
        _seed(client)
        resp = client.raw().post(
            "/api/checkout",
            json=_payload(metodo="cartao", cpf="12345678901"),
        )
        assert resp.status_code == 422

    def test_pix_without_cpf_422(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json=_payload(metodo="pix", cpf=None))
        assert resp.status_code == 422

    def test_plano_not_found_404(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json=_payload(plano_id="99999999-9999-9999-9999-999999999999"))
        assert resp.status_code == 404

    def test_missing_gateway_ref_409(self, client):
        _seed(client, ref_rows=[_gateway_ref_row("stripe")])
        resp = client.raw().post("/api/checkout", json=_payload(metodo="pix"))
        assert resp.status_code == 409

    def test_missing_turnstile_token_403(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json=_payload(turnstile_token=None))
        assert resp.status_code == 403
        assert "Verificação de segurança" in resp.json()["detail"]
