"""`GET /api/vitrine/exclusivos` -- key-authenticated (`noc_` token, scope vitrine:exclusivos:read), org-bound, opt-in, public fields only."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.testing import MockSupabaseClient

from app.services.vitrine_exclusivos_service import CAMPOS_SAIDA, normalize

URL = "/api/vitrine/exclusivos"
ORG = "fd169d29-4d0a-4b04-9a5e-25e69407614d"
OTHER = "11111111-1111-1111-1111-111111111111"
SCOPE = "vitrine:exclusivos:read"
SECRET = "SEGREDO-INTERNO"
SITE = "https://oneconsultoriaimobiliaria.com.br"


def _row(codigo, org=ORG, **over):
    row = {
        "org_id": org, "codigo": codigo, "titulo": " Casa linda ", "categoria": "Casa em Condomínio", "status": "Venda",
        "cidade": "Itu", "bairro": "Cidade Nova", "uf": "SP", "valor_venda": 1_500_000, "valor_locacao": None,
        "valor_condominio": 900, "dormitorios": 4, "suites": 2, "vagas": 3, "area_privativa": 320.0, "area_total": 500.0,
        "foto_destaque": "https://img/x.jpg", "data_cadastro": "2026-10-01", "descricao_web": "Linda.Casa  com\nquintal",
        "exibir_no_site": True, "exclusivo": True, "vista_raw": {"Exclusivo": "Sim", "Proprietario": SECRET},
        # planted: must never appear in the output
        "corretores": [{"nome": SECRET}], "observacoes": SECRET, "chave": SECRET, "numero": "123", "logradouro": SECRET,
    }
    row.update(over)
    return row


class _Flat:
    """The mock keeps tables on the schema-less client; the service asks for `.schema("social_wiring").table(...)`."""

    def __init__(self, db):
        self._db = db

    def schema(self, _name):
        return self._db


def _ctx(scopes=(SCOPE,), org=ORG):
    return AuthContext(org_id=UUID(org), caller_kind="product", user_id=None, scopes=list(scopes), raw_token="t",
                       api_token_id=uuid4(), issuer="core")


@pytest.fixture
def cena(client):
    from app.dependencies import get_auth_context
    from app.main import app
    from app.routers.vitrine_exclusivos_router import get_vitrine_service
    from app.services.vitrine_exclusivos_service import VitrineExclusivosService

    db = MockSupabaseClient()
    db.set_table_data("vitrine_exclusivos_orgs", [{"org_id": ORG, "site_url": SITE, "ativo": True}])
    db.set_table_data("imoveis", [
        _row("CA1", data_cadastro="2026-09-01"),
        _row("CA2", data_cadastro="2026-10-05"),
        _row("NAO", exclusivo=False, vista_raw={"Exclusivo": "Nao"}),
        _row("HID", exibir_no_site=False),
        _row("VEN", status="Vendido"),
        _row("REM"),
        _row("OUT", org=OTHER),
    ])
    db.set_table_data("imovel_registry", [
        {"org_id": ORG, "codigo_canonical": "REM", "ativo_no_vista": False, "delistado_em": "2026-10-20T00:00:00+00:00"},
        {"org_id": ORG, "codigo_canonical": "CA1", "ativo_no_vista": True, "delistado_em": None},
    ])
    db.set_table_data("imoveis_sync_execucoes", [
        {"org_id": ORG, "status": "ok", "finalizado_em": "2026-11-09T06:00:00+00:00"},
        {"org_id": ORG, "status": "falhou", "finalizado_em": "2026-11-09T09:00:00+00:00"},
    ])
    app.dependency_overrides[get_vitrine_service] = lambda: VitrineExclusivosService(_Flat(db))
    prev = app.dependency_overrides.get(get_auth_context)

    class T:
        raw = client.raw()
        dbm = db

        def as_ctx(self, ctx):
            app.dependency_overrides[get_auth_context] = lambda: ctx

        def get(self):
            return self.raw.get(URL)

    yield T()
    app.dependency_overrides.pop(get_vitrine_service, None)
    if prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = prev


class TestAuth:
    def test_no_key_is_strictly_401(self, cena):
        assert cena.get().status_code == 401

    def test_a_wrong_key_is_strictly_401(self, cena):
        r = cena.raw.get(URL, headers={"Authorization": "Bearer noc_" + "0" * 64})
        assert r.status_code == 401

    def test_a_key_with_another_scope_is_403_scope_missing(self, cena):
        cena.as_ctx(_ctx(scopes=["social-wiring:one-chat:read"]))
        r = cena.get()
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"

    def test_a_human_session_is_403_product_required(self, cena):
        cena.as_ctx(AuthContext(org_id=UUID(ORG), caller_kind="user", user_id=uuid4(), scopes=[], raw_token="s", api_token_id=None))
        r = cena.get()
        assert r.status_code == 403 and r.json()["code"] == "product_required"

    def test_the_scope_is_offered_to_the_mint_ui(self):
        import app.routers.vitrine_exclusivos_router  # noqa: F401
        from noctusai_lib.api.auth.session import TOKEN_SCOPES
        assert SCOPE in TOKEN_SCOPES


class TestFeed:
    def test_only_the_orgs_listed_exclusives_newest_first(self, cena):
        cena.as_ctx(_ctx())
        r = cena.get()
        assert r.status_code == 200
        # excluded: not exclusive (NAO), hidden (HID), sold (VEN), removed in the registry (REM), other org (OUT)
        assert [i["codigo"] for i in r.json()["imoveis"]] == ["CA2", "CA1"]

    def test_atualizado_em_is_the_last_successful_sync(self, cena):
        cena.as_ctx(_ctx())
        assert cena.get().json()["atualizado_em"] == "2026-11-09T06:00:00+00:00"

    def test_response_shape_and_no_internal_field_leaks(self, cena):
        cena.as_ctx(_ctx())
        r = cena.get()
        assert set(r.json()) == {"atualizado_em", "imoveis"}
        for card in r.json()["imoveis"]:
            assert set(card) == CAMPOS_SAIDA
        assert SECRET not in r.text
        assert r.headers["cache-control"] == "private, max-age=300"

    def test_card_values(self, cena):
        cena.as_ctx(_ctx())
        card = cena.get().json()["imoveis"][0]
        assert card["titulo"] == "Casa linda" and card["condominio"] == 900.0 and card["area"] == 320.0
        assert card["descricao"] == "Linda. Casa com quintal"
        assert card["url"] == f"{SITE}/imovel/casa-em-condominio-cidade-nova-itu-sp-4-quartos-320m2-CA2"

    def test_an_org_that_has_not_opted_in_is_404(self, cena):
        cena.dbm.set_table_data("vitrine_exclusivos_orgs", [])
        cena.as_ctx(_ctx())
        assert cena.get().status_code == 404

    def test_an_inactive_opt_in_is_404(self, cena):
        cena.dbm.set_table_data("vitrine_exclusivos_orgs", [{"org_id": ORG, "site_url": SITE, "ativo": False}])
        cena.as_ctx(_ctx())
        assert cena.get().status_code == 404

    def test_the_key_binds_the_org(self, cena):
        cena.as_ctx(_ctx(org=OTHER))  # a key of another org is not opted in: nothing of ORG leaks
        assert cena.get().status_code == 404


class TestNormalize:
    def test_long_description_is_trimmed_to_240_on_a_word(self):
        out = normalize(_row("X", descricao_web="palavra " * 100), SITE)
        assert len(out["descricao"]) <= 241 and out["descricao"].endswith("…")

    def test_area_falls_back_to_total_and_missing_numbers_are_zero(self):
        out = normalize(_row("X", area_privativa=None, valor_venda=None, dormitorios=None), SITE)
        assert out["area"] == 500.0 and out["valor_venda"] == 0.0 and out["dormitorios"] == 0
