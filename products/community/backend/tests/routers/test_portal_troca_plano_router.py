"""`POST /api/portal/assinatura` — troca de plano (projects/ninho-vazio/
CONTRACT.md §Member portal).

The bug this closes: a self-registered member is `ativo` on the free plan,
and the anonymous `POST /api/checkout` answers any `ativo` email with
`verifique_seu_email` and no gateway call (amendment A2) — so a member could
never upgrade. The member route binds to the CALLER's own membro row and
opens the gateway subscription; A2 keeps holding for the anonymous route.

No key resolves in the test env, so the shared checkout path uses the
seed's `FakeHostedCheckout` (same posture as `test_checkout_router.py`).
"""
from tests.conftest import ORG_UUID, TEST_USER_ID, seed_community_role, seed_public_license

URL = "/api/portal/assinatura"

MEMBRO_1 = "11111111-1111-1111-1111-111111111111"
OUTRO_MEMBRO = "55555555-5555-5555-5555-555555555555"
GRATUITO = "20000000-0000-0000-0000-000000000000"
OUVINTE = "21111111-1111-1111-1111-111111111111"
PREMIUM = "22222222-2222-2222-2222-222222222222"
INATIVO = "23333333-3333-3333-3333-333333333333"
CPF = "123.456.789-01"


def _plano(id_, nome, preco, ordem, nivel, ativo=True) -> dict:
    return {
        "id": id_, "org_id": ORG_UUID, "nome": nome, "descricao": None,
        "preco_centavos": preco, "ciclo": "mensal",
        "entitlements": {"grupoterapia": nivel}, "ativo": ativo, "ordem": ordem,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _ref(plano_id) -> dict:
    return {
        "id": f"ref-{plano_id[:4]}", "org_id": ORG_UUID, "plano_id": plano_id,
        "gateway": "asaas", "ref_externo": "asaas-plan",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _membro(id_=MEMBRO_1, user_id=TEST_USER_ID, email="ana@x.com", plano_id=GRATUITO) -> dict:
    return {
        "id": id_, "org_id": ORG_UUID, "nome": "Ana", "email": email, "telefone": None,
        "status": "ativo", "plano_id": plano_id, "origem": "cadastro", "tags": [],
        "user_id": user_id, "observacoes": None, "entrou_em": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _assinatura(id_, plano_id, estado, membro_id=MEMBRO_1) -> dict:
    return {
        "id": id_, "org_id": ORG_UUID, "membro_id": membro_id, "plano_id": plano_id,
        "gateway": "asaas", "assinatura_externa_id": "sub_x", "cliente_externo_id": None,
        "estado": estado, "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": None, "ativa_em": None, "cancelada_em": None,
        "gateway_cancelamento_pendente": False,
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }


def _seed(client, *, assinaturas=None, role="membro"):
    seed_community_role(client, org_role=role)
    seed_public_license(client)
    client.mock_supabase.set_table_data("planos", [
        _plano(GRATUITO, "Gratuito", 0, 0, "nenhum"),
        _plano(OUVINTE, "Ouvinte", 700, 1, "ouvir"),
        _plano(PREMIUM, "Premium", 2700, 2, "falar"),
        _plano(INATIVO, "Antigo", 5000, 3, "falar", ativo=False),
    ])
    client.mock_supabase.set_table_data(
        "plano_gateway_refs", [_ref(OUVINTE), _ref(PREMIUM), _ref(INATIVO)],
    )
    client.mock_supabase.set_table_data(
        "membros", [_membro(), _membro(OUTRO_MEMBRO, None, "bia@x.com")],
    )
    client.mock_supabase.set_table_data("assinaturas", assinaturas or [])
    client.mock_supabase.set_table_data("pagamentos", [])
    client.mock_supabase.set_table_data("membro_eventos", [])


def _body(**over) -> dict:
    base = {"plano_id": PREMIUM, "metodo": "pix", "cpf_cnpj": CPF}
    base.update(over)
    return base


def _rows(client, table) -> list[dict]:
    return client.mock_supabase.table(table).select("*").execute().data or []


class TestAuthBoundary:
    def test_no_auth_401(self, client):
        assert client.raw().post(URL, json=_body()).status_code == 401

    def test_staff_403(self, client):
        _seed(client, role="admin")
        assert client.post(URL, json=_body()).status_code == 403


class TestTrocaDePlano:
    def test_ativo_free_member_upgrades_through_the_gateway(self, client):
        """The bug: this exact member got `verifique_seu_email` before."""
        _seed(client)
        resp = client.post(URL, json=_body())
        assert resp.status_code == 201
        body = resp.json()
        assert set(body) == {"checkout_url", "assinatura_id", "membro_id", "pix_qr", "status"}
        assert body["status"] is None
        assert body["membro_id"] == MEMBRO_1
        assert body["checkout_url"]
        assert body["pix_qr"]["payload"] and body["pix_qr"]["imagem_base64"]

        [sub] = _rows(client, "assinaturas")
        assert sub["id"] == body["assinatura_id"]
        assert sub["membro_id"] == MEMBRO_1
        assert sub["plano_id"] == PREMIUM
        assert sub["estado"] == "iniciada" and sub["gateway"] == "asaas"
        assert sub["assinatura_externa_id"]  # a real gateway object exists
        # the member's plan only moves when the charge is paid (webhook)
        membro = [m for m in _rows(client, "membros") if m["id"] == MEMBRO_1][0]
        assert membro["plano_id"] == GRATUITO
        [evento] = _rows(client, "membro_eventos")
        assert evento["tipo"] == "assinatura"
        assert evento["descricao"] == "Troca de plano iniciada"
        assert evento["membro_id"] == MEMBRO_1
        assert evento["dados"]["plano_id"] == PREMIUM
        assert evento["dados"]["plano_anterior_id"] == GRATUITO
        # CPF/CNPJ goes to the gateway only (product decision P1)
        for table in ("assinaturas", "pagamentos", "membro_eventos", "membros"):
            assert "12345678901" not in str(_rows(client, table))

    def test_boleto_with_cnpj(self, client):
        _seed(client)
        resp = client.post(URL, json=_body(metodo="boleto", cpf_cnpj="12.345.678/0001-90"))
        assert resp.status_code == 201
        assert _rows(client, "assinaturas")[0]["metodo"] == "boleto"

    def test_body_can_never_target_another_member(self, client):
        _seed(client)
        for extra in ({"membro_id": OUTRO_MEMBRO}, {"email": "bia@x.com"}):
            assert client.post(URL, json={**_body(), **extra}).status_code == 422
        assert _rows(client, "assinaturas") == []

    def test_second_call_reuses_the_open_subscription(self, client):
        """Amendment A10 reuse (the stored charge handed back is covered in
        `tests/services/test_checkout_service.py`)."""
        _seed(client)
        first = client.post(URL, json=_body()).json()
        second = client.post(URL, json=_body())
        assert second.status_code == 201
        body = second.json()
        assert body["status"] == "checkout_em_andamento"
        assert body["assinatura_id"] == first["assinatura_id"]
        assert len(_rows(client, "assinaturas")) == 1
        assert len(_rows(client, "membro_eventos")) == 1


class TestTrocaDePlanoErros:
    def test_free_plan_409(self, client):
        _seed(client)
        resp = client.post(URL, json=_body(plano_id=GRATUITO))
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Este plano é gratuito."

    def test_already_on_this_plan_409(self, client):
        for estado in ("ativa", "carencia", "inadimplente"):
            _seed(client, assinaturas=[_assinatura("a0000000-0000-0000-0000-000000000000", PREMIUM, estado)])
            resp = client.post(URL, json=_body())
            assert resp.status_code == 409, estado
            assert resp.json()["detail"] == "Você já tem este plano."

    def test_another_members_subscription_does_not_block(self, client):
        _seed(client, assinaturas=[
            _assinatura("a0000000-0000-0000-0000-000000000000", PREMIUM, "ativa", OUTRO_MEMBRO),
        ])
        assert client.post(URL, json=_body()).status_code == 201

    def test_ended_subscription_on_the_same_plan_does_not_block(self, client):
        _seed(client, assinaturas=[
            _assinatura("a0000000-0000-0000-0000-000000000000", PREMIUM, "expirada"),
        ])
        assert client.post(URL, json=_body()).status_code == 201

    def test_inactive_or_unknown_plan_404(self, client):
        _seed(client)
        assert client.post(URL, json=_body(plano_id=INATIVO)).status_code == 404
        assert client.post(
            URL, json=_body(plano_id="99999999-9999-9999-9999-999999999999"),
        ).status_code == 404

    def test_bad_cpf_cnpj_and_card_method_422(self, client):
        _seed(client)
        assert client.post(URL, json=_body(cpf_cnpj="123")).status_code == 422
        assert client.post(URL, json=_body(cpf_cnpj="1234567890123")).status_code == 422
        assert client.post(URL, json=_body(metodo="cartao")).status_code == 422


class TestAnonymousCheckoutKeepsAmendmentA2:
    def test_public_checkout_for_an_ativo_email_still_never_calls_the_gateway(self, client):
        _seed(client)
        resp = client.raw().post("/api/checkout", json={
            "plano_id": PREMIUM, "metodo": "pix", "nome": "Ana", "email": "ana@x.com",
            "telefone": "+5511999999999", "cpf": "12345678901", "turnstile_token": "tok",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "verifique_seu_email"
        assert body["checkout_url"] is None and body["pix_qr"] is None
        [sub] = _rows(client, "assinaturas")
        assert sub["assinatura_externa_id"] is None  # no gateway object
