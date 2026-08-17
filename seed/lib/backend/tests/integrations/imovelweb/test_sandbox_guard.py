"""`emit_event` fabricates lead events. Against production those would be
indistinguishable from real customers, so the host check is a refusal —
not a warning, and not a substring heuristic."""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.imovelweb.endpoints import (
    IMOVELWEB_PROD_AR,
    IMOVELWEB_PROD_BR,
    IMOVELWEB_PROD_RELA,
    IMOVELWEB_SANDBOX_BR,
    is_sandbox_host,
)
from noctusai_lib.integrations.imovelweb.errors import ImovelWebConfigError
from noctusai_lib.integrations.imovelweb.factory import make_imovelweb_client


class TestIsSandboxHost:
    def test_recognises_the_real_sandbox(self):
        assert is_sandbox_host(IMOVELWEB_SANDBOX_BR) is True

    def test_tolerates_a_trailing_slash(self):
        assert is_sandbox_host(IMOVELWEB_SANDBOX_BR + "/") is True

    @pytest.mark.parametrize(
        "host", [IMOVELWEB_PROD_BR, IMOVELWEB_PROD_AR, IMOVELWEB_PROD_RELA]
    )
    def test_rejects_every_production_host(self, host):
        assert is_sandbox_host(host) is False

    @pytest.mark.parametrize("host", [None, "", "not a url"])
    def test_rejects_junk(self, host):
        assert is_sandbox_host(host) is False

    def test_is_an_allowlist_not_a_substring_match(self):
        # A naive `"sandbox" in url` check would accept every one of
        # these, and a false positive fires synthetic leads at a live CRM.
        for impostor in (
            "https://api-br-open.navent.com/?sandbox=true",
            "https://sandbox.attacker.example.com",
            "https://api-br-sandbox-open.navent.com.attacker.example.com",
            "https://api-br-open.navent.com#api-br-sandbox-open.navent.com",
        ):
            assert is_sandbox_host(impostor) is False, impostor


class TestEmitEventGuard:
    @pytest.mark.asyncio
    async def test_fake_allows_it_on_the_sandbox(self):
        client = make_imovelweb_client(use_fake=True, fake_base_url=IMOVELWEB_SANDBOX_BR)
        result = await client.emit_event({"tipoDeEvento": "CONTACTO"})
        assert result["status"] == "emitted"
        assert client.emitted == [{"tipoDeEvento": "CONTACTO"}]

    @pytest.mark.asyncio
    async def test_fake_refuses_on_production(self):
        client = make_imovelweb_client(use_fake=True, fake_base_url=IMOVELWEB_PROD_BR)
        with pytest.raises(ImovelWebConfigError, match="non-sandbox host"):
            await client.emit_event({})
        assert client.emitted == []

    @pytest.mark.asyncio
    async def test_real_refuses_on_production_before_any_request(self):
        # No http_client is supplied: reaching the network at all would
        # raise something else, so this proves the guard fires first.
        client = make_imovelweb_client(
            client_id="a", client_secret="b", region="br", sandbox=False
        )
        with pytest.raises(ImovelWebConfigError, match="non-sandbox host"):
            await client.emit_event({})

    @pytest.mark.asyncio
    async def test_the_refusal_explains_why(self):
        client = make_imovelweb_client(use_fake=True, fake_base_url=IMOVELWEB_PROD_BR)
        with pytest.raises(ImovelWebConfigError) as exc:
            await client.emit_event({})
        assert "indistinguishable from real customers" in str(exc.value)
