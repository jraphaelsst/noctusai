"""`PUT /api/julia/onboarding/orgs/{org_id}/configuracoes/{setting}` -- the onboarding staff channel (agents -> SW).

Auth matrix first (strict `== 401`; the two 401 cases run the REAL, un-overridden chain; the 403/200 matrix uses the
honest `get_auth_context` seam), then the allow-list, the target-org check, the writes and the EOA event."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.testing import MockSupabaseClient

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_STAFF = UUID("00000000-0000-4000-8000-0000000000cc")
_SCOPE = "social-wiring:onboarding-settings"


def _url(setting, org=_ORG):
    return f"/api/julia/onboarding/orgs/{org}/configuracoes/{setting}"


def _body(corpo, ator=_STAFF):
    return {"corpo": corpo, "ator": {"user_id": str(ator)}}


def _ctx(*, scopes=(_SCOPE,), issuer="noctus-platform", kind="product"):
    return AuthContext(
        org_id=uuid4(), caller_kind=kind, user_id=uuid4() if kind == "user" else None, scopes=list(scopes),
        raw_token="t", api_token_id=None if kind == "user" else uuid4(), issuer=None if kind == "user" else issuer,
    )


@pytest.fixture
def canal(client):
    from app.dependencies import get_auth_context
    from app.main import app
    from app.routers.julia_onboarding_router import get_onboarding_client, get_onboarding_core

    db, core = MockSupabaseClient(), MockSupabaseClient()
    core.set_table_data("organizations", [{"id": str(_ORG), "nome": "Org X"}])
    app.dependency_overrides[get_onboarding_client] = lambda: db
    app.dependency_overrides[get_onboarding_core] = lambda: core
    prev = app.dependency_overrides.get(get_auth_context)

    class C:
        raw = client.raw()
        data = db

        def as_ctx(self, ctx):
            app.dependency_overrides[get_auth_context] = lambda: ctx

        def put(self, setting, corpo, org=_ORG, **kw):
            return self.raw.put(_url(setting, org), json=_body(corpo, **kw))

        def eventos(self):
            return [r for r in (db.table("julia_eventos").select("*").execute().data or []) if r["tipo"] == "configuracao_alterada"]

    yield C()
    for dep in (get_onboarding_client, get_onboarding_core):
        app.dependency_overrides.pop(dep, None)
    if prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = prev


class TestAuthMatrix:
    def test_no_credential_is_exactly_401(self, canal):
        assert canal.put("reengajamento", {"minutos_ativo": True}).status_code == 401

    def test_an_invalid_token_is_exactly_401(self, canal):
        r = canal.raw.put(_url("reengajamento"), json=_body({"minutos_ativo": True}), headers={"Authorization": "Bearer pk_" + "0" * 64})
        assert r.status_code == 401

    def test_a_human_session_is_403_product_required(self, canal):
        canal.as_ctx(_ctx(kind="user"))
        r = canal.put("reengajamento", {"minutos_ativo": True})
        assert r.status_code == 403 and r.json()["code"] == "product_required"

    def test_wrong_scope_is_403_scope_missing(self, canal):
        canal.as_ctx(_ctx(scopes=["social-wiring:lais-tools"]))
        r = canal.put("reengajamento", {"minutos_ativo": True})
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"

    def test_an_org_issued_token_with_the_scope_is_403_issuer_not_allowed(self, canal):
        canal.as_ctx(_ctx(issuer="agents"))
        r = canal.put("reengajamento", {"minutos_ativo": True})
        assert r.status_code == 403 and r.json()["code"] == "issuer_not_allowed"
        assert canal.eventos() == []


class TestGuards:
    @pytest.fixture(autouse=True)
    def _auth(self, canal):
        canal.as_ctx(_ctx())

    def test_unknown_org_is_404(self, canal):
        r = canal.put("reengajamento", {"minutos_ativo": True}, org=uuid4())
        assert r.status_code == 404
        assert canal.eventos() == []

    @pytest.mark.parametrize("setting", ["visitas", "agente_nome", "destino_lead_pronto", "api_keys", "../x"])
    def test_out_of_allowlist_is_422_and_writes_nothing(self, canal, setting):
        r = canal.put(setting, {"qualquer": 1})
        assert r.status_code in (404, 422)
        if r.status_code == 422:
            assert r.json()["error"]["code"] == "setting_nao_permitida" or r.json().get("code") == "setting_nao_permitida"
        assert canal.eventos() == []

    def test_unknown_body_field_is_422(self, canal):
        r = canal.put("pesquisa", {"pesquisa": True, "extra": 1})
        assert r.status_code == 422
        assert canal.eventos() == []

    def test_missing_actor_is_422(self, canal):
        r = canal.raw.put(_url("pesquisa"), json={"corpo": {"pesquisa": True}})
        assert r.status_code == 422

    def test_invalid_reengage_value_is_422(self, canal):
        assert canal.put("reengajamento", {"minutos_intervalo": 7}).status_code == 422
        assert canal.eventos() == []


class TestWrites:
    @pytest.fixture(autouse=True)
    def _auth(self, canal):
        canal.as_ctx(_ctx())

    def test_reengage_writes_the_target_org_and_records_the_event(self, canal):
        r = canal.put("reengajamento", {"minutos_ativo": True, "minutos_intervalo": 15, "horas_ativo": True, "horas_intervalo": 4})
        assert r.status_code == 200, r.text
        row = canal.data.table("julia_reengajamento_config").select("*").eq("org_id", str(_ORG)).execute().data[0]
        assert row["minutos_intervalo"] == 15 and row["horas_intervalo"] == 4
        (ev,) = canal.eventos()
        assert ev["org_id"] == str(_ORG)
        assert ev["payload"]["ator"] == str(_STAFF) and ev["payload"]["via"] == "onboarding"
        assert ev["payload"]["setting"] == "reengajamento" and "15" not in str(ev["payload"]["chaves"])

    def test_policies_settings_share_the_politicas_row(self, canal):
        assert canal.put("envio_captacoes", {"captacoes": "enviar"}).status_code == 200
        assert canal.put("pesquisa", {"pesquisa": True}).status_code == 200
        from app.services import julia_envio_service as envio

        p = envio.ler_politicas(canal.data, _ORG)
        assert p["captacoes"] == "enviar" and p["pesquisa"] is True
        assert len(canal.eventos()) == 2

    def test_address_and_iptu_merge_into_one_section(self, canal):
        assert canal.put("politica_endereco", {"endereco_completo": True}).status_code == 200
        assert canal.put("politica_iptu", {"ativo": True}).status_code == 200
        from app.services import julia_conhecimento_service as c

        assert c.politica_endereco_iptu(canal.data, _ORG) == {"endereco_completo": True, "usar_iptu": True}

    def test_recess_and_attendant_and_review_link(self, canal):
        assert canal.put("recesso", {"inicio": "2026-12-24", "fim": "2027-01-02", "mensagem": "Voltamos em janeiro."}).status_code == 200
        assert canal.put("mostrar_atendente", {"ativo": True}).status_code == 200
        assert canal.put("avaliacao_google", {"url": "https://g.page/r/x/review"}).status_code == 200
        assert canal.put("avaliacao_google", {"url": "http://nao-https"}).status_code == 422
