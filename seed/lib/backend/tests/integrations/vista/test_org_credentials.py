"""Per-org Vista credentials: the `CredentialStore`-backed resolver, the adapter-for-org factory, the SSRF guard and the
live connection check (julia-v3, 2026-11-03). Fake store; MockTransport for the wire; synthetic key."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from noctusai_lib.integrations.credential_resolvers import VISTA_PROVIDER, VistaCredentialResolver
from noctusai_lib.integrations.vista import VistaConfigError, VistaRESTAdapter, get_vista_adapter_for_org
from noctusai_lib.integrations.vista.client import VistaClient, VistaPermissionDenied
from noctusai_lib.integrations.vista.credentials import (
    VistaBaseUrlInvalida, chave_final, validar_base_url, verificar_conexao,
)
from noctusai_lib.security.token_store import FakeCredentialStore

ORG = "00000000-0000-4000-8000-0000000000aa"
OUTRA = "00000000-0000-4000-8000-0000000000bb"
KEY = "feedfacefeedfacefeedfacefeed644c"
URL = "https://acme-rest.vistahost.com.br"


def _store(**bundle):
    s = FakeCredentialStore()
    s.put(ORG, VISTA_PROVIDER, {"base_url": URL, "api_key": KEY, **bundle})
    return s


class TestResolver:
    def test_returns_the_orgs_url_and_key(self):
        assert VistaCredentialResolver(_store()).get(ORG) == (URL, KEY)

    def test_the_provider_key_is_vista(self):
        assert VISTA_PROVIDER == "vista"

    @pytest.mark.parametrize("org", [OUTRA, "", None])
    def test_an_org_without_a_record_is_refused_not_null(self, org):
        with pytest.raises(VistaConfigError, match="Vista não configurada para esta empresa"):
            VistaCredentialResolver(_store()).get(org)

    @pytest.mark.parametrize("bundle", [{"api_key": ""}, {"base_url": " "}])
    def test_an_incomplete_bundle_is_refused(self, bundle):
        with pytest.raises(VistaConfigError):
            VistaCredentialResolver(_store(**bundle)).get(ORG)

    def test_extra_bundle_keys_are_ignored(self):
        assert VistaCredentialResolver(_store(chave_final="644c", verificado_em="x")).get(ORG) == (URL, KEY)

    def test_adapter_for_org_is_the_real_adapter_with_that_orgs_credentials(self):
        a = get_vista_adapter_for_org(VistaCredentialResolver(_store()), ORG)
        assert isinstance(a, VistaRESTAdapter) and a._base_url == URL and a._api_key == KEY
        with pytest.raises(VistaConfigError):
            get_vista_adapter_for_org(VistaCredentialResolver(_store()), OUTRA)


class TestBaseUrlGuard:
    @pytest.mark.parametrize("ok,esperado", [
        ("https://acme-rest.vistahost.com.br", URL), ("https://acme-rest.vistahost.com.br/", URL),
        ("  HTTPS://Acme-Rest.VistaHost.com.br  ", URL),
    ])
    def test_accepts_a_vista_tenant_origin(self, ok, esperado):
        assert validar_base_url(ok) == esperado

    @pytest.mark.parametrize("ruim", [
        "", "http://acme-rest.vistahost.com.br", "https://evil.example.com", "https://vistahost.com.br",
        "https://acme-rest.vistahost.com.br.evil.com", "https://evil.com/acme-rest.vistahost.com.br",
        "https://user:pw@acme-rest.vistahost.com.br", "https://acme-rest.vistahost.com.br:8443",
        "https://acme-rest.vistahost.com.br/imoveis", "https://acme-rest.vistahost.com.br?x=1",
        "https://127.0.0.1", "https://localhost", "https://169.254.169.254", "ftp://acme-rest.vistahost.com.br",
        "https://acme_rest.vistahost.com.br", "https://a.b.vistahost.com.br",
    ])
    def test_refuses_everything_else(self, ruim):
        with pytest.raises(VistaBaseUrlInvalida):
            validar_base_url(ruim)

    def test_chave_final_is_the_last_four_only(self):
        assert chave_final(KEY) == "644c" and chave_final("ab") == "ab" and chave_final("") == ""


def _client(handler):
    return VistaClient(URL, KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class TestVerificarConexao:
    def test_ok_asks_one_broker_and_sends_the_key_only_as_the_query_param(self):
        seen = []

        def handler(req):
            seen.append(req)
            return httpx.Response(200, json={"items": [{"Codigo": "1", "Nome": "B"}], "meta": {"totalItems": 1}})

        asyncio.run(verificar_conexao(URL, KEY, client=_client(handler)))
        assert len(seen) == 1 and seen[0].url.path == "/corretores/listar" and seen[0].url.params["limit"] == "1"

    def test_a_rejected_key_raises_without_echoing_it(self):
        def handler(req):
            return httpx.Response(401, json={"status": 401, "message": f'Permissão Negada: "{KEY}" Método: corretores/listar'})

        with pytest.raises(VistaPermissionDenied) as exc:
            asyncio.run(verificar_conexao(URL, KEY, client=_client(handler)))
        assert KEY not in str(exc.value) and KEY not in repr(exc.value.__dict__)
