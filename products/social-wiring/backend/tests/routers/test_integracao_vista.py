"""`/api/integracoes/vista` (julia-v3): the org's own Vista credential -- admin-only, write-only key, SSRF-guarded base URL,
live-checked before it is stored, redacted everywhere -- and every Vista site in the product refusing an org that has no
record (no `.env` fallback). Fake store + a Fake verifier through the routes' own DI seams; synthetic key."""
from __future__ import annotations

import logging

import pytest
from noctusai_lib.integrations.credential_resolvers import VISTA_PROVIDER
from noctusai_lib.integrations.vista import VistaConfigError, VistaError, VistaPermissionDenied
from noctusai_lib.security.token_store import FakeCredentialStore

from app.services import vista_credenciais
from tests.routers.test_julia_equipe_protecao import admin, member, override_settings_factory  # noqa: F401
from tests.support.julia_world import ORG_ID

URL = "/api/integracoes/vista"
BASE = "https://acme-rest.vistahost.com.br"
KEY = "feedfacefeedfacefeedfacefeed644c"


class _Verificador:
    def __init__(self):
        self.chamadas: list[tuple[str, str]] = []
        self.erro: Exception | None = None

    async def __call__(self, base_url, api_key):
        self.chamadas.append((base_url, api_key))
        if self.erro is not None:
            raise self.erro


@pytest.fixture
def cena(admin):  # noqa: F811
    yield from _montar(admin)


@pytest.fixture
def cena_membro(member):  # noqa: F811
    yield from _montar(member)


def _montar(scene):
    from app.main import app
    from app.routers.integracao_vista_router import get_vista_core, get_vista_store, get_vista_verificador

    store, verificador = FakeCredentialStore(), _Verificador()
    ov = {get_vista_core: lambda: scene.w.root, get_vista_store: lambda: store, get_vista_verificador: lambda: verificador}
    app.dependency_overrides.update(ov)
    scene.store, scene.verificador = store, verificador
    vista_credenciais.configure_store(lambda: store)
    yield scene
    vista_credenciais.configure_store(None)
    for k in ov:
        app.dependency_overrides.pop(k, None)


class TestAuth:
    @pytest.mark.parametrize("method,sufixo", [("get", ""), ("put", ""), ("post", "/testar"), ("delete", "")])
    def test_no_session_is_strictly_401(self, cena, method, sufixo):
        assert getattr(cena.tc, method)(URL + sufixo).status_code == 401

    @pytest.mark.parametrize("method,sufixo,corpo", [
        ("get", "", None), ("put", "", {"base_url": BASE, "api_key": KEY}), ("post", "/testar", {}), ("delete", "", None),
    ])
    def test_a_member_is_403_and_nothing_is_written(self, cena_membro, method, sufixo, corpo):
        assert cena_membro.req(method, URL + sufixo, corpo).status_code == 403
        assert cena_membro.store.list_providers(ORG_ID) == [] and cena_membro.verificador.chamadas == []


class TestFluxo:
    def test_unconfigured_then_save_then_read_never_returns_the_key(self, cena):
        assert cena.req("get", URL).json()["data"] == {"configurado": False, "base_url": None, "chave_final": None, "verificado_em": None}
        r = cena.req("put", URL, {"base_url": BASE + "/", "api_key": KEY})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["configurado"] is True and d["base_url"] == BASE and d["chave_final"] == "644c" and d["verificado_em"]
        assert KEY not in r.text and KEY not in cena.req("get", URL).text
        assert cena.verificador.chamadas == [(BASE, KEY)]
        stored = cena.store.get(ORG_ID, VISTA_PROVIDER)
        assert stored.tokens["api_key"] == KEY and stored.tokens["base_url"] == BASE

    def test_replacing_the_key_overwrites_in_place(self, cena):
        cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
        cena.req("put", URL, {"base_url": BASE, "api_key": "0" * 28 + "abcd"})
        assert cena.store.list_providers(ORG_ID) == [VISTA_PROVIDER]
        assert cena.req("get", URL).json()["data"]["chave_final"] == "abcd"

    def test_delete_removes_the_record_and_is_idempotent(self, cena):
        cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
        for _ in range(2):
            r = cena.req("delete", URL)
            assert r.status_code == 200 and r.json()["data"]["configurado"] is False
        assert cena.store.list_providers(ORG_ID) == []

    def test_testar_checks_the_stored_credential(self, cena):
        assert cena.req("post", URL + "/testar", {}).json()["data"]["ok"] is False  # nothing stored
        cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
        cena.verificador.chamadas.clear()
        d = cena.req("post", URL + "/testar", {}).json()["data"]
        assert d["ok"] is True and cena.verificador.chamadas == [(BASE, KEY)]
        cena.verificador.erro = VistaPermissionDenied(401, f'Permissão Negada: "{KEY}"', "corretores/listar")
        r = cena.req("post", URL + "/testar", {})
        assert r.json()["data"]["ok"] is False and KEY not in r.text


class TestValidacao:
    @pytest.mark.parametrize("base", [
        "http://acme-rest.vistahost.com.br", "https://evil.example.com", "https://169.254.169.254", "https://localhost",
        "https://acme-rest.vistahost.com.br.evil.com", "https://acme-rest.vistahost.com.br:8443", "https://acme-rest.vistahost.com.br/x",
        "https://user@acme-rest.vistahost.com.br",
    ])
    def test_ssrf_guard_refuses_other_hosts_before_any_call(self, cena, base):
        r = cena.req("put", URL, {"base_url": base, "api_key": KEY})
        assert r.status_code == 422 and r.json()["error"]["code"] == "vista_url_invalida"
        assert cena.verificador.chamadas == [] and cena.store.list_providers(ORG_ID) == []

    @pytest.mark.parametrize("corpo", [{}, {"base_url": BASE}, {"api_key": KEY}, {"base_url": BASE, "api_key": "curta"},
                                       {"base_url": BASE, "api_key": KEY, "org_id": "x"}])
    def test_body_validation(self, cena, corpo):
        assert cena.req("put", URL, corpo).status_code == 422

    def test_a_rejected_key_is_not_stored_and_is_never_echoed(self, cena, caplog):
        cena.verificador.erro = VistaPermissionDenied(401, f'Permissão Negada: "{KEY}" Método: corretores/listar', "corretores/listar")
        with caplog.at_level(logging.DEBUG):
            r = cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
        assert r.status_code == 422 and r.json()["error"]["code"] == "vista_chave_recusada"
        assert KEY not in r.text and KEY not in caplog.text
        assert cena.store.list_providers(ORG_ID) == []

    def test_an_unreachable_vista_is_503_redacted_and_not_stored(self, cena, caplog):
        cena.verificador.erro = VistaError(f"boom https://x?key={KEY}")
        with caplog.at_level(logging.DEBUG):
            r = cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
        assert r.status_code == 503 and r.json()["error"]["code"] == "vista_indisponivel"
        assert KEY not in r.text and KEY not in caplog.text and cena.store.list_providers(ORG_ID) == []

    def test_the_audit_line_names_the_actor_and_the_last_four_only(self, cena, caplog):
        with caplog.at_level(logging.INFO):
            cena.req("put", URL, {"base_url": BASE, "api_key": KEY})
            cena.req("delete", URL)
        linhas = [r.getMessage() for r in caplog.records if "audit: vista_credencial" in r.getMessage()]
        assert len(linhas) == 2 and all("chave_final=644c" in x and "ator=" in x and KEY not in x for x in linhas)


class TestSemFallbackNoEnv:
    """Every Vista site refuses an org with no record. The environment has no key to fall back to."""

    def test_the_resolver_path_refuses(self):
        vista_credenciais.configure_store(lambda: FakeCredentialStore())
        try:
            with pytest.raises(VistaConfigError, match="Vista não configurada para esta empresa"):
                vista_credenciais.adapter_da_org(ORG_ID)
            assert vista_credenciais.adapter_ou_none(ORG_ID) is None
            with pytest.raises(Exception) as exc:
                vista_credenciais.adapter_ou_503(ORG_ID)
            assert exc.value.status_code == 503 and "Vista não configurada para esta empresa" in exc.value.detail
        finally:
            vista_credenciais.configure_store(None)

    def test_one_orgs_record_is_not_anothers(self):
        store = FakeCredentialStore()
        vista_credenciais.salvar(ORG_ID, BASE, KEY, "u", store)
        assert vista_credenciais.adapter_da_org(ORG_ID, store)._api_key == KEY
        with pytest.raises(VistaConfigError):
            vista_credenciais.adapter_da_org("00000000-0000-4000-8000-0000000000ff", store)

    def test_the_settings_no_longer_carry_a_vista_key(self):
        from app.config import SocialWiringSettings

        campos = set(SocialWiringSettings.model_fields)
        assert not campos & {"crm_api_key", "crm_base_url", "vista_api_key", "vista_base_url"}

    def test_the_sync_endpoint_is_503_without_a_record(self, cena):
        r = cena.req("post", "/api/imoveis/sync")
        assert r.status_code == 503 and "Vista não configurada para esta empresa" in r.text

    def test_the_status_probe_reports_not_configured(self, cena):
        d = cena.req("get", "/api/settings/vista/status").json()
        assert d["configured"] is False and "Vista não configurada" in d["error"]

    def test_no_product_module_builds_a_vista_adapter_by_hand(self):
        """Structural: the only `VistaRESTAdapter(` construction under app/ is none -- all go through the resolver."""
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "app"
        achados = [str(p.relative_to(raiz)) for p in raiz.rglob("*.py")
                   if re.search(r"VistaRESTAdapter\(", p.read_text(encoding="utf-8")) and "VistaRESTAdapter(base_url" in p.read_text(encoding="utf-8")]
        assert achados == []
