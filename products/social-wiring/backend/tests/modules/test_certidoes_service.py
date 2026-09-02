"""Certidões Negativas — service-layer tests.

Ports the coverage of
`products/erp-imobiliario/backend/tests/services/test_certidoes_service.py` and
adds the cases this port's own divergences created: the storage seam (keys, not
public URLs), the delete path that replaced ERP's raw-supabase workaround, and
the org scoping migration 091 introduced.

`MockSupabaseClient` (not a hand-rolled chain stub) because it validates column
names against the migration-derived schema — so a typo'd column in a query
under test fails here rather than in production — and because it propagates
writes into subsequent reads, which is what the status-recalculation and
recovery tests actually assert on.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import service
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    PARAM_BUILDERS,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    _build_params_cnd_federal,
    _build_params_simples,
    _build_params_tjsp,
    _build_params_trf3,
    _build_params_trf3_sp,
    _build_params_trt2_digital,
    _build_params_trt2_fisico,
    config_for,
    get_certidoes_tipos,
)

#: The module's single credential-resolution point. Substituting HERE (not
#: `noctusai_lib`'s `resolve_credential`) is the point of
#: `credentials.resolve_key`: the store behind it moved to the product-local
#: encrypted one and these tests did not have to follow it into two tiers.
_CRED = "app.modules.certidoes.credentials.resolve_api_key"
_REGISTRY_RESOLVE = "app.modules.certidoes.registry.resolve_key"

ORG = "11111111-1111-4111-8111-111111111111"
OTHER_ORG = "22222222-2222-4222-8222-222222222222"

CONSULTA_CPF = {
    "id": "consulta-001",
    "org_id": ORG,
    "tipo_documento": "cpf",
    "documento": "12345678901",
    "nome": "João da Silva",
    "data_nascimento": "1990-01-15",
    "genero": "M",
    "rg": "123456789",
    "nome_mae": "Maria da Silva",
    "nome_pai": "José da Silva",
}

CONSULTA_CNPJ = {
    "id": "consulta-002",
    "org_id": ORG,
    "tipo_documento": "cnpj",
    "documento": "12345678000190",
    "nome": "Empresa XPTO",
    "data_nascimento": None,
    "genero": None,
    "rg": None,
    "nome_mae": None,
    "nome_pai": None,
}

CONSULTA_MINIMAL = {
    "id": "consulta-003",
    "org_id": ORG,
    "tipo_documento": "cpf",
    "documento": "99988877766",
    "nome": "Teste",
}


def _db(**tables) -> MockSupabaseClient:
    """A `social_wiring`-scoped mock client seeded per table."""
    client = MockSupabaseClient(schema="social_wiring")
    for name, rows in tables.items():
        client.set_table_data(name, rows)
    return client


def _resultado(**overrides) -> dict:
    row = {
        "id": "resultado-001",
        "consulta_id": "consulta-001",
        "org_id": ORG,
        "tipo": "cnd_federal",
        "nome_display": "CND Federal (Receita)",
        "ordem": 1,
        "status": "pendente",
        "analise_ia": None,
        "arquivo_url": None,
        "arquivo_nome": None,
        "api_response": None,
        "erro_mensagem": None,
        "api_requested_at": None,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _consulta_row(**overrides) -> dict:
    row = {
        **CONSULTA_CPF,
        "created_by": "user-1",
        "status": "pendente",
        "total_certidoes": 10,
        "concluidas": 0,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# CERTIDOES_CONFIG — the contract with ten third-party endpoints
# ---------------------------------------------------------------------------


class TestCertidoesConfig:
    def test_tem_10_tipos(self):
        assert len(CERTIDOES_CONFIG) == 10

    def test_ordens_sequenciais(self):
        assert [c["ordem"] for c in CERTIDOES_CONFIG] == list(range(1, 11))

    def test_todos_tem_campos_obrigatorios(self):
        for config in CERTIDOES_CONFIG:
            for field in (
                "tipo", "nome", "endpoint", "ordem", "params_fn", "response_format"
            ):
                assert field in config, f"{config.get('tipo')} missing {field}"

    def test_params_fn_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["params_fn"] in PARAM_BUILDERS

    def test_response_format_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["response_format"] in ("pdf", "html")

    def test_tipos_e_ordem_identicos_ao_erp(self):
        """🔴 The whole registry, pinned.

        A dropped or reordered certificate type is a certificate a user
        silently stops receiving — no error, no failed row, just one fewer item
        on a checklist nobody re-counts. The per-field tests above would all
        still pass with the TJSP entry deleted. This one would not.
        """
        assert [(c["tipo"], c["ordem"]) for c in CERTIDOES_CONFIG] == [
            ("cnd_federal", 1),
            ("trf3_sp", 2),
            ("trf3", 3),
            ("trt2_digital", 4),
            ("trt2_fisico", 5),
            ("cnd_trabalhista_tst", 6),
            ("tjsp", 7),
            ("cenprot", 8),
            ("cnd_fazenda_sp", 9),
            ("divida_ativa_sp", 10),
        ]

    def test_endpoints_identicos_ao_erp(self):
        assert {c["tipo"]: c["endpoint"] for c in CERTIDOES_CONFIG} == {
            "cnd_federal": "receita-federal/pgfn",
            "trf3_sp": "tribunal/trf3/certidao-distr",
            "trf3": "tribunal/trf3/certidao-distr",
            "trt2_digital": "tribunal/trt2/ceat-digital",
            "trt2_fisico": "tribunal/trt2/ceat",
            "cnd_trabalhista_tst": "tst/cndt",
            "tjsp": "tribunal/tjsp/pedido-certidao",
            "cenprot": "cenprot-sp/protestos",
            "cnd_fazenda_sp": "sefaz/sp/certidao-debitos",
            "divida_ativa_sp": "pge/sp/cndt",
        }

    def test_config_for_desconhecido_retorna_none(self):
        assert config_for("nao_existe") is None
        assert config_for(TJSP_TIPO)["ordem"] == 7


class TestGetCertidoesTipos:
    def test_retorna_lista(self):
        assert len(get_certidoes_tipos()) == 10

    def test_cada_item_tem_tipo_nome_ordem(self):
        for item in get_certidoes_tipos():
            assert set(item) == {"tipo", "nome", "ordem"}

    def test_nao_expoe_campos_internos(self):
        """The endpoint path and the builder name are ours, not the browser's."""
        for item in get_certidoes_tipos():
            assert "endpoint" not in item
            assert "params_fn" not in item


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class TestCheckRequiredCredentials:
    def test_sem_infosimples_retorna_mensagem(self):
        with patch(_CRED, return_value=None):
            missing = service.check_required_credentials(ORG)
        assert len(missing) == 1
        assert "InfoSimples" in missing[0]

    def test_com_infosimples_retorna_vazio(self):
        with patch(_CRED, return_value="tok-123"):
            assert service.check_required_credentials(ORG) == []

    def test_resolve_passa_pelo_seam_do_modulo(self):
        """Every key in this module goes through `credentials.resolve_key`,
        which now resolves through the product's own encrypted key store.

        A call site that had reached for `resolve_credential` directly would
        still be reading the platform chain ONLY — skipping the encrypted rows
        the operator writes in Settings → Chaves de API — and nothing would say
        so: the platform tier still answers for a pre-existing key, so the miss
        would surface only for an org that had re-entered its token in the new
        UI. This asserts the routing, not just the return value.
        """
        with patch(_CRED, return_value="tok") as m:
            service.check_required_credentials(ORG)
        m.assert_called_once_with("infosimples_token", ORG)

    def test_credenciais_resolvem_pelo_key_store_do_produto(self):
        """The import is the contract: `credentials.resolve_key` delegates to
        `api_keys_store.resolve_api_key` (local encrypted tier → platform
        chain), not to `resolve_credential` (platform chain only)."""
        from app.modules.certidoes import credentials
        from app.services.api_keys_store import resolve_api_key

        assert credentials.resolve_api_key is resolve_api_key
        # All three names this module needs are operator-settable in the UI.
        from app.services.api_keys_store import MANAGED_API_KEYS

        assert {
            credentials.INFOSIMPLES_TOKEN,
            credentials.INFOSIMPLES_EMAIL_ENVIO,
            credentials.OPENAI_API_KEY,
        } <= set(MANAGED_API_KEYS)


# ---------------------------------------------------------------------------
# Parameter builders — the exact per-endpoint parameter sets
# ---------------------------------------------------------------------------


class TestBuildParamsCndFederal:
    def test_cpf_com_birthdate(self):
        params = _build_params_cnd_federal(CONSULTA_CPF, "tok")
        assert params["cpf"] == "12345678901"
        assert params["birthdate"] == "1990-01-15"
        assert params["preferencia_emissao"] == "2via"
        assert params["token"] == "tok"

    def test_cnpj(self):
        params = _build_params_cnd_federal(CONSULTA_CNPJ, "tok")
        assert params["cnpj"] == "12345678000190"
        assert "cpf" not in params

    def test_sem_data_nascimento(self):
        params = _build_params_cnd_federal(CONSULTA_MINIMAL, "tok")
        assert "birthdate" not in params


class TestBuildParamsTrf3:
    def test_inclui_tipo_abrangencia_tipo_documento(self):
        params = _build_params_trf3(CONSULTA_CPF, "tok")
        assert params["tipo"] == "1"
        assert params["abrangencia"] == "1"
        assert params["tipo_documento"] == "1"

    def test_cnpj_tipo_documento_2(self):
        assert _build_params_trf3(CONSULTA_CNPJ, "tok")["tipo_documento"] == "2"

    def test_usa_nome_social(self):
        assert _build_params_trf3(CONSULTA_CPF, "tok")["nome_social"] == "João da Silva"


class TestBuildParamsTrf3Sp:
    def test_tipo_2_abrangencia_1(self):
        params = _build_params_trf3_sp(CONSULTA_CPF, "tok")
        assert params["tipo"] == "2"
        assert params["abrangencia"] == "1"

    def test_cpf_tipo_documento_1(self):
        assert _build_params_trf3_sp(CONSULTA_CPF, "tok")["tipo_documento"] == "1"

    def test_cnpj_tipo_documento_2(self):
        assert _build_params_trf3_sp(CONSULTA_CNPJ, "tok")["tipo_documento"] == "2"

    def test_mesmo_endpoint_do_regional_difere_so_no_tipo(self):
        """The two TRF3 entries share an endpoint — `tipo` is the whole
        difference, which is why dropping one looks harmless and is not."""
        sp = _build_params_trf3_sp(CONSULTA_CPF, "tok")
        regional = _build_params_trf3(CONSULTA_CPF, "tok")
        assert sp["tipo"] != regional["tipo"]
        assert {k: v for k, v in sp.items() if k != "tipo"} == {
            k: v for k, v in regional.items() if k != "tipo"
        }


class TestBuildParamsTrt2Digital:
    def test_cpf_simples(self):
        params = _build_params_trt2_digital(CONSULTA_CPF, "tok")
        assert params == {"token": "tok", "cpf": "12345678901"}

    def test_cnpj_usa_cnpj_raiz(self):
        params = _build_params_trt2_digital(CONSULTA_CNPJ, "tok")
        assert params == {"token": "tok", "cnpj_raiz": "12345678000190"}


class TestBuildParamsTrt2Fisico:
    def test_inclui_nome(self):
        params = _build_params_trt2_fisico(CONSULTA_CPF, "tok")
        assert params["nome"] == "João da Silva"
        assert params["cpf"] == "12345678901"


class TestBuildParamsSimples:
    def test_apenas_token_e_doc(self):
        assert _build_params_simples(CONSULTA_CPF, "tok") == {
            "token": "tok", "cpf": "12345678901"
        }


class TestBuildParamsTjsp:
    def test_inclui_modelo(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            assert _build_params_tjsp(CONSULTA_CPF, "tok")["modelo"] == "4"

    def test_cpf_usa_nome_completo(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["nome_completo"] == "João da Silva"
        assert "razao_social" not in params

    def test_cnpj_usa_razao_social(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CNPJ, "tok")
        assert params["razao_social"] == "Empresa XPTO"
        assert "nome_completo" not in params

    def test_inclui_email_envio_quando_configurado(self):
        with patch(_REGISTRY_RESOLVE, return_value="fila@noctus.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["email_envio"] == "fila@noctus.com"

    def test_omite_email_envio_quando_nao_configurado(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            assert "email_envio" not in _build_params_tjsp(CONSULTA_CPF, "tok")

    def test_inclui_campos_opcionais_quando_presentes(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["rg"] == "123456789"
        assert params["genero"] == "M"
        assert params["nome_mae"] == "Maria da Silva"
        assert params["nome_pai"] == "José da Silva"

    def test_omite_campos_opcionais_quando_ausentes(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_MINIMAL, "tok")
        for field in ("rg", "genero", "nome_mae", "nome_pai", "birthdate"):
            assert field not in params

    def test_email_resolve_pelo_seam_do_modulo(self):
        with patch(_CRED, return_value="fila@noctus.com") as m:
            _build_params_tjsp(CONSULTA_CPF, "tok")
        m.assert_called_once_with("infosimples_email_envio", ORG)


# ---------------------------------------------------------------------------
# _fetch_certidao
# ---------------------------------------------------------------------------


def _http(response_payloads):
    """An httpx client stub whose GET returns each payload in turn."""
    client = MagicMock()
    responses = []
    for payload in response_payloads:
        resp = MagicMock()
        resp.json.return_value = payload
        responses.append(resp)
    client.get = AsyncMock(side_effect=responses)
    return client


CONFIG_FEDERAL = config_for("cnd_federal")


class TestFetchCertidao:
    @pytest.mark.asyncio
    async def test_sucesso_le_site_receipt(self):
        client = _http([{
            "code": 200,
            "data": [{"site_receipt": "https://x/recibo.pdf", "situacao": "Regular"}],
        }])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is True
        assert result["file_url"] == "https://x/recibo.pdf"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_cenprot_le_site_receipts_da_raiz(self):
        """CENPROT puts the file URL at the ROOT, not inside data[0]."""
        client = _http([{
            "code": 200,
            "data": [{"protestos": []}],
            "site_receipts": ["https://x/cenprot.html"],
        }])
        result = await service._fetch_certidao(
            config_for("cenprot"), CONSULTA_CPF, "tok", client
        )
        assert result["file_url"] == "https://x/cenprot.html"

    @pytest.mark.asyncio
    async def test_612_e_sucesso_nada_consta(self):
        """612 is 'no data at source' — for a certidão that IS the good news."""
        client = _http([{"code": 612, "errors": ["Nada consta"]}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is True
        assert result["nada_consta"] == "Nada consta"
        assert result["file_url"] is None

    @pytest.mark.asyncio
    async def test_612_sem_errors_usa_default(self):
        client = _http([{"code": 612}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["nada_consta"] == "Nada consta"

    @pytest.mark.asyncio
    async def test_erro_4xx_nao_retenta(self):
        client = _http([{"code": 400, "errors": ["CPF inválido"]}] * 3)
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is False
        assert "CPF inválido" in result["error"]
        assert client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_erro_5xx_retenta_ate_max(self):
        client = _http([{"code": 500, "message": "boom"}] * service.MAX_RETRIES)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await service._fetch_certidao(
                CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
            )
        assert result["success"] is False
        assert client.get.await_count == service.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_erro_especifico_e_generico_combinados(self):
        client = _http([{"code": 400, "errors": ["Sem RG"], "message": "params"}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["error"] == "Sem RG (params)"

    @pytest.mark.asyncio
    async def test_excecao_de_rede_vira_erro_reportado(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await service._fetch_certidao(
                CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
            )
        assert result["success"] is False
        assert "down" in result["error"]
        assert result["raw_response"] is None


# ---------------------------------------------------------------------------
# _download_file / _convert_html_to_pdf
# ---------------------------------------------------------------------------


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_200_retorna_bytes_e_content_type(self):
        resp = MagicMock(status_code=200, content=b"%PDF-1.4 x")
        resp.headers = {"content-type": "application/pdf"}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await service._download_file("https://x/f.pdf", client) == (
            b"%PDF-1.4 x", "application/pdf"
        )

    @pytest.mark.asyncio
    async def test_404_retorna_none(self):
        resp = MagicMock(status_code=404, content=b"")
        resp.headers = {}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await service._download_file("https://x/f.pdf", client) is None

    @pytest.mark.asyncio
    async def test_excecao_retorna_none(self):
        client = MagicMock(get=AsyncMock(side_effect=httpx.ReadTimeout("t")))
        assert await service._download_file("https://x/f.pdf", client) is None


class TestConvertHtmlToPdf:
    def test_converte_html_simples(self):
        pdf = service._convert_html_to_pdf(b"<html><body><p>oi</p></body></html>")
        assert pdf is not None
        assert pdf[:5] == b"%PDF-"

    def test_html_vazio_ainda_produz_pdf(self):
        pdf = service._convert_html_to_pdf(b"")
        assert pdf is None or pdf[:5] == b"%PDF-"

    def test_html_invalido_nao_crasheia(self):
        assert service._convert_html_to_pdf(b"<<<>>> nao e html") is not None


# ---------------------------------------------------------------------------
# AI analysis
# ---------------------------------------------------------------------------


class TestAnalyzeWithAi:
    @pytest.mark.asyncio
    async def test_sem_chave_retorna_marcador_em_portugues(self):
        """Not None: an empty column reads as a broken feature. The marker says
        WHICH setting is missing, in the language the operator reads."""
        with patch(_CRED, return_value=None):
            out = await service._analyze_with_ai("texto", ORG)
        assert "Análise IA não disponível" in out
        assert "OpenAI API Key" in out

    @pytest.mark.asyncio
    async def test_com_chave_chama_seed_chat_completion(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value="Tudo regular."),
        ) as chat:
            out = await service._analyze_with_ai("texto", ORG)
        assert out == "Tudo regular."
        kwargs = chat.await_args.kwargs
        assert kwargs["org_id"] == ORG
        assert kwargs["model"] == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_falha_do_provedor_vira_marcador_nao_excecao(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(side_effect=RuntimeError("429")),
        ):
            out = await service._analyze_with_ai("texto", ORG)
        assert "Erro na análise IA" in out


# ---------------------------------------------------------------------------
# Storage — the one real rewrite from the ERP
# ---------------------------------------------------------------------------


class TestStorageKey:
    def test_org_id_e_o_primeiro_segmento(self):
        """🔴 The bucket's object-RLS policies match on the FIRST path segment.
        A key shaped any other way is readable across orgs."""
        key = service.storage_key(ORG, "consulta-001", "tjsp")
        assert key.startswith(f"{ORG}/certidoes/consulta-001/tjsp_")
        assert key.endswith(".pdf")

    def test_sufixo_aleatorio_nao_sobrescreve_reemissao(self):
        a = service.storage_key(ORG, "c1", "tjsp")
        b = service.storage_key(ORG, "c1", "tjsp")
        assert a != b

    def test_is_storage_key_distingue_url_de_chave(self):
        assert service.is_storage_key(f"{ORG}/certidoes/c1/tjsp_ab.pdf") is True
        assert service.is_storage_key("https://infosimples/x.pdf") is False
        assert service.is_storage_key(None) is False
        assert service.is_storage_key("") is False


class TestPersistPdf:
    @pytest.mark.asyncio
    async def test_grava_no_bucket_e_devolve_a_chave(self):
        storage = FakeStorageBackend()
        key = await service._persist_pdf(
            b"%PDF-1.4", storage, ORG, "consulta-001", "cnd_federal"
        )
        assert key is not None
        blob = await storage.get(bucket=service.BUCKET, key=key)
        assert blob is not None and blob.data == b"%PDF-1.4"

    @pytest.mark.asyncio
    async def test_sem_org_id_nao_grava_e_devolve_none(self):
        storage = FakeStorageBackend()
        assert await service._persist_pdf(
            b"%PDF-", storage, None, "consulta-001", "tjsp"
        ) is None
        assert await storage.list_keys(bucket=service.BUCKET) == []

    @pytest.mark.asyncio
    async def test_falha_do_backend_devolve_none_sem_propagar(self):
        """A storage outage must not lose the certidão: the caller keeps the
        upstream URL, so the file is still reachable."""
        storage = MagicMock()
        storage.put = AsyncMock(side_effect=RuntimeError("bucket down"))
        assert await service._persist_pdf(
            b"%PDF-", storage, ORG, "c1", "tjsp"
        ) is None


class TestReadCertidaoBytes:
    @pytest.mark.asyncio
    async def test_chave_le_pelo_seam_sem_http(self):
        storage = FakeStorageBackend()
        key = f"{ORG}/certidoes/c1/tjsp_ab.pdf"
        await storage.put(bucket=service.BUCKET, key=key, data=b"%PDF-x")
        http = MagicMock(get=AsyncMock(side_effect=AssertionError("must not HTTP")))
        assert await service.read_certidao_bytes(key, storage, http) == b"%PDF-x"

    @pytest.mark.asyncio
    async def test_url_externa_cai_no_proxy_http(self):
        resp = MagicMock(status_code=200, content=b"%PDF-remote")
        resp.headers = {"content-type": "application/pdf"}
        http = MagicMock(get=AsyncMock(return_value=resp))
        out = await service.read_certidao_bytes(
            "https://infosimples/x.pdf", FakeStorageBackend(), http
        )
        assert out == b"%PDF-remote"

    @pytest.mark.asyncio
    async def test_chave_ausente_devolve_none(self):
        http = MagicMock(get=AsyncMock())
        assert await service.read_certidao_bytes(
            f"{ORG}/certidoes/c1/sumiu.pdf", FakeStorageBackend(), http
        ) is None


class TestDeleteStorageFiles:
    @pytest.mark.asyncio
    async def test_apaga_de_verdade_pelo_seam(self):
        """ERP bypassed its own StorageService here because that service fell
        back to a silent dry-run. The seam deletes; nothing to work around."""
        storage = FakeStorageBackend()
        key = f"{ORG}/certidoes/c1/tjsp_ab.pdf"
        await storage.put(bucket=service.BUCKET, key=key, data=b"x")
        deleted = await service.delete_storage_files([{"arquivo_url": key}], storage)
        assert deleted == 1
        assert await storage.exists(bucket=service.BUCKET, key=key) is False

    @pytest.mark.asyncio
    async def test_ignora_urls_externas(self):
        storage = FakeStorageBackend()
        assert await service.delete_storage_files(
            [{"arquivo_url": "https://infosimples/x.pdf"}, {"arquivo_url": None}],
            storage,
        ) == 0

    @pytest.mark.asyncio
    async def test_falha_em_um_arquivo_nao_impede_os_outros(self):
        storage = MagicMock()
        storage.delete = AsyncMock(side_effect=[RuntimeError("nope"), True])
        deleted = await service.delete_storage_files(
            [{"arquivo_url": "a/certidoes/c/1.pdf"}, {"arquivo_url": "a/certidoes/c/2.pdf"}],
            storage,
        )
        assert deleted == 1


# ---------------------------------------------------------------------------
# _process_single_certidao
# ---------------------------------------------------------------------------


class _FakeHttp:
    """An `httpx.AsyncClient` stand-in answering BOTH calls the pipeline makes.

    🔴 THIS REPLACED A `patch.object(service, "_fetch_certidao", ...)`.

    Both the InfoSimples API call and the file download that follows it go
    through the SAME client, so a double has to route on the URL. Doing that
    rather than swapping our own `_fetch_certidao` out means the real retry
    ladder, the 612 / "nada consta" branch, the CENPROT `site_receipts`
    fallback and the error-extraction precedence all actually RUN — which is
    the behaviour the ERP port had to preserve exactly, and which a stubbed
    `_fetch_certidao` asserted nothing about.

    `httpx` is the external boundary here; it is the only thing being faked.
    """

    def __init__(
        self,
        api_payload: dict,
        *,
        file_body: bytes = b"%PDF-1.4 real",
        file_content_type: str = "application/pdf",
        file_status: int = 200,
    ):
        self.api_payload = api_payload
        self.file_body = file_body
        self.file_content_type = file_content_type
        self.file_status = file_status
        self.api_calls: list[dict] = []
        self.downloaded: list[str] = []

    async def get(self, url, **kwargs):
        if url.startswith(service.INFOSIMPLES_BASE_URL):
            self.api_calls.append(kwargs.get("params") or {})
            resp = MagicMock()
            resp.json.return_value = self.api_payload
            return resp
        self.downloaded.append(url)
        resp = MagicMock(status_code=self.file_status, content=self.file_body)
        resp.headers = {"content-type": self.file_content_type}
        return resp


def _api_ok(file_url="https://x/f.pdf", data=None) -> dict:
    """A real InfoSimples 200 envelope, as the API returns it."""
    return {
        "code": 200,
        "data": data or [{"site_receipt": file_url, "situacao": "Regular"}],
    }


class _Recorder:
    """An awaitable stand-in for `_process_single_certidao`, recording what the
    fan-out decided to run.

    Injected through `processar_consulta(process_one=...)` rather than patched
    over the module attribute: what these tests assert is the DISPATCH decision
    (which resultados run now, which are queued, which are skipped), and that is
    exactly what stays observable when the collaborator is a parameter.
    """

    def __init__(self):
        self.calls: list[tuple] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def resultado_ids(self) -> list[str]:
        return [c[4] for c in self.calls]

    async def __call__(self, *args, **kwargs):
        self.calls.append(args)


class _SyncRecorder:
    """`_Recorder`'s synchronous twin — `schedule_tjsp_for_org` is a plain
    function, and awaiting a recorder that is not awaitable would be a
    different bug than the one under test."""

    def __init__(self):
        self.calls: list[tuple] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    def __call__(self, *args, **kwargs):
        self.calls.append(args)


async def _noop_analyze(text, org_id=None):
    """The `analyze=` DI seam's stand-in. The AI call is a separate concern
    with its own tests (`TestAnalyzeWithAi`); here it must simply not fire."""
    return "ok"


class TestProcessSingleCertidao:
    @pytest.mark.asyncio
    async def test_pdf_vai_para_o_bucket_e_arquivo_url_guarda_a_chave(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, storage, analyze=_noop_analyze,
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert service.is_storage_key(row["arquivo_url"])
        assert row["arquivo_url"].startswith(f"{ORG}/certidoes/consulta-001/")
        assert row["arquivo_nome"] == "cnd_federal.pdf"
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        assert blob.data == b"%PDF-1.4 real"
        # The REAL param builder ran, against the real endpoint URL.
        assert http.api_calls[0]["cpf"] == "12345678901"
        assert http.downloaded == ["https://x/f.pdf"]

    @pytest.mark.asyncio
    async def test_html_e_convertido_antes_de_gravar(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-html")],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            _api_ok(),
            file_body=b"<html><body>oi</body></html>",
            file_content_type="text/html",
        )

        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-html", http, storage, analyze=_noop_analyze,
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-html"
        ).execute().data[0]
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        assert blob.data[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_cenprot_le_o_site_receipts_da_raiz(self):
        """CENPROT puts the file URL at the ROOT, not in `data[0]`. Reachable
        now that the real `_fetch_certidao` runs in this path."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-cenprot")],
        )
        http = _FakeHttp(
            {
                "code": 200,
                "data": [{"protestos": []}],
                "site_receipts": ["https://x/cenprot.html"],
            },
            file_body=b"<html>ok</html>",
            file_content_type="text/html",
        )
        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-cenprot", http, FakeStorageBackend(), analyze=_noop_analyze,
        )
        assert http.downloaded == ["https://x/cenprot.html"]

    @pytest.mark.asyncio
    async def test_content_type_desconhecido_mantem_a_url_de_origem(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            _api_ok(), file_body=b"\x89PNG\r\n", file_content_type="image/png"
        )

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, storage, analyze=_noop_analyze,
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["arquivo_url"] == "https://x/f.pdf"
        assert await storage.list_keys(bucket=service.BUCKET) == []

    @pytest.mark.asyncio
    async def test_nada_consta_e_sucesso_sem_arquivo(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp({"code": 612, "errors": ["Nada consta"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(), analyze=_noop_analyze,
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["analise_ia"] == "Nada consta"
        assert row["arquivo_url"] is None
        assert http.downloaded == []

    @pytest.mark.asyncio
    async def test_falha_grava_erro_e_mensagem(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp({"code": 400, "errors": ["CPF inválido"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(), analyze=_noop_analyze,
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["erro_mensagem"] == "CPF inválido"

    @pytest.mark.asyncio
    async def test_api_requested_at_e_gravado_antes_da_chamada(self):
        """🔴 The TJSP cooldown reads this column and nothing else. If it were
        only written on success, a failed request — which still consumed the
        30-minute window at TJSP — would look like no request at all."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo=TJSP_TIPO)],
        )
        with patch(_REGISTRY_RESOLVE, return_value=None):
            await service._process_single_certidao(
                config_for(TJSP_TIPO), _consulta_row(), "tok", db,
                "resultado-001", _FakeHttp({"code": 400, "errors": ["x"]}),
                FakeStorageBackend(), analyze=_noop_analyze,
            )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["api_requested_at"] is not None


# ---------------------------------------------------------------------------
# _atualizar_status_consulta
# ---------------------------------------------------------------------------


def _status_db(statuses: list[str]) -> MockSupabaseClient:
    return _db(
        certidao_consultas=[_consulta_row()],
        certidao_resultados=[
            _resultado(id=f"r{i}", status=s, ordem=i + 1)
            for i, s in enumerate(statuses)
        ],
    )


class TestAtualizarStatusConsulta:
    def _consulta(self, db):
        return db.table("certidao_consultas").select("*").eq(
            "id", "consulta-001"
        ).execute().data[0]

    def test_todos_sucesso_vira_concluida(self):
        db = _status_db(["sucesso", "sucesso"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        row = self._consulta(db)
        assert row["status"] == "concluida"
        assert row["concluidas"] == 2

    def test_todos_erro_vira_erro(self):
        db = _status_db(["erro", "erro"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["status"] == "erro"

    def test_um_na_fila_mantem_processando(self):
        db = _status_db(["sucesso", "na_fila"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["status"] == "processando"

    def test_misto_sucesso_e_erro_vira_concluida(self):
        """One failure does not make the consulta a failure — nine certidões
        that DID come back are still nine certidões."""
        db = _status_db(["sucesso", "erro"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        row = self._consulta(db)
        assert row["status"] == "concluida"
        assert row["concluidas"] == 1

    def test_conta_apenas_resultados_da_propria_org(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="mine", status="sucesso"),
                _resultado(id="theirs", status="sucesso", org_id=OTHER_ORG),
            ],
        )
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["concluidas"] == 1


# ---------------------------------------------------------------------------
# processar_consulta
# ---------------------------------------------------------------------------


class TestProcessarConsulta:
    @pytest.mark.asyncio
    async def test_sem_token_marca_tudo_erro_com_mensagem_acionavel(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r1"), _resultado(id="r2", ordem=2)],
        )
        with patch(_CRED, return_value=None):
            await service.processar_consulta("consulta-001", db, FakeStorageBackend())

        rows = db.table("certidao_resultados").select("*").execute().data
        assert all(r["status"] == "erro" for r in rows)
        assert "Token InfoSimples não configurado" in rows[0]["erro_mensagem"]
        consulta = db.table("certidao_consultas").select("*").execute().data[0]
        assert consulta["status"] == "erro"

    @pytest.mark.asyncio
    async def test_tjsp_em_cooldown_vai_para_na_fila_e_agenda(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, ordem=7,
                           api_requested_at=recent),
            ],
        )
        scheduled: list[tuple] = []
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(),
                schedule_tjsp=lambda *a: scheduled.append(a),
            )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "na_fila"
        assert len(scheduled) == 1 and scheduled[0][0] == ORG

    @pytest.mark.asyncio
    async def test_tjsp_sem_historico_roda_imediatamente(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r-tjsp", tipo=TJSP_TIPO, ordem=7)],
        )
        processed = _Recorder()
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(), process_one=processed,
            )
        assert processed.count == 1

    @pytest.mark.asyncio
    async def test_tipo_fora_do_registro_e_pulado_com_log_nao_derruba_o_resto(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-ok"),
                _resultado(id="r-orfao", tipo="tipo_removido", ordem=99),
            ],
        )
        processed = _Recorder()
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(), process_one=processed,
            )
        assert processed.count == 1
        # The orphan tipo is skipped, not crashed on — and the real one ran.
        assert processed.resultado_ids == ["r-ok"]

    @pytest.mark.asyncio
    async def test_consulta_inexistente_nao_estoura(self):
        db = _db(certidao_consultas=[], certidao_resultados=[])
        await service.processar_consulta("nao-existe", db, FakeStorageBackend())


# ---------------------------------------------------------------------------
# TJSP cooldown
# ---------------------------------------------------------------------------


class TestTjspCooldown:
    def test_sem_requests_anteriores_retorna_none(self):
        db = _db(certidao_resultados=[])
        assert service._get_tjsp_last_request_at(ORG, db) is None

    def test_le_o_api_requested_at_mais_recente(self):
        ts = "2026-03-05T10:00:00+00:00"
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) == datetime.fromisoformat(ts)

    def test_timestamp_ilegivel_e_pulado_e_nao_estoura(self):
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at="lixo",
                       created_at="2026-03-05T12:00:00+00:00"),
            _resultado(id="r2", tipo=TJSP_TIPO,
                       api_requested_at="2026-03-05T10:00:00+00:00",
                       created_at="2026-03-05T09:00:00+00:00"),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) is not None

    def test_sobrevive_ao_reset_de_status_no_reprocessamento(self):
        """🔴 The whole reason this column exists. A resultado reset from
        `erro` to `na_fila` still consumed TJSP's 30-minute window."""
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, status="na_fila",
                       api_requested_at=ts),
        ])
        remaining = service._get_tjsp_remaining_cooldown(ORG, db)
        assert remaining > 0

    def test_cooldown_expirado_retorna_zero(self):
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        assert service._get_tjsp_remaining_cooldown(ORG, db) == 0.0

    def test_cooldown_de_outra_org_nao_conta(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, org_id=OTHER_ORG,
                       api_requested_at=ts),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) is None

    def test_status_para_o_frontend_sem_historico(self):
        assert service.tjsp_cooldown_status(ORG, _db(certidao_resultados=[])) == {
            "ativo": False
        }

    def test_status_para_o_frontend_em_cooldown(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        out = service.tjsp_cooldown_status(ORG, db)
        assert out["ativo"] is True
        assert 0 < out["segundos_restantes"] <= TJSP_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# TJSP scheduler
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tjsp_tasks():
    service._tjsp_scheduled_tasks.clear()
    yield
    service._tjsp_scheduled_tasks.clear()


class TestScheduleTjspForOrg:
    @pytest.mark.asyncio
    async def test_sem_itens_na_fila_nao_agenda(self):
        db = _db(certidao_resultados=[])
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend())
        assert ORG not in service._tjsp_scheduled_tasks

    @pytest.mark.asyncio
    async def test_cria_task_para_item_na_fila(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        delayed = _Recorder()
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend(), delayed=delayed)
        task = service._tjsp_scheduled_tasks.get(ORG)
        assert task is not None
        await asyncio.sleep(0)
        # It scheduled the QUEUED item, with the cooldown delay it computed.
        assert delayed.count == 1
        assert delayed.calls[0][1]["id"] == "r-tjsp"
        task.cancel()

    @pytest.mark.asyncio
    async def test_idempotente_enquanto_a_task_esta_em_voo(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])

        async def _never():
            await asyncio.sleep(3600)

        in_flight = asyncio.get_running_loop().create_task(_never())
        service._tjsp_scheduled_tasks[ORG] = in_flight
        delayed = _Recorder()
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend(), delayed=delayed)
        assert service._tjsp_scheduled_tasks[ORG] is in_flight
        assert delayed.count == 0, "a second task was scheduled for the same org"
        in_flight.cancel()

    @pytest.mark.asyncio
    async def test_agenda_uma_task_por_org(self):
        db = _db(certidao_resultados=[
            _resultado(id="a", tipo=TJSP_TIPO, status="na_fila"),
            _resultado(id="b", tipo=TJSP_TIPO, status="na_fila",
                       org_id=OTHER_ORG, consulta_id="consulta-002"),
        ])
        scheduled: list[str] = []
        service.schedule_all_pending_tjsp(
            db, FakeStorageBackend(),
            schedule_one=lambda oid, *_a, **_k: scheduled.append(oid),
        )
        assert set(scheduled) == {ORG, OTHER_ORG}

    @pytest.mark.asyncio
    async def test_sem_fila_nenhuma_task(self):
        scheduled: list[str] = []
        service.schedule_all_pending_tjsp(
            _db(certidao_resultados=[]), FakeStorageBackend(),
            schedule_one=lambda oid, *_a, **_k: scheduled.append(oid),
        )
        assert scheduled == []
        assert service._tjsp_scheduled_tasks == {}


class TestDelayedTjspProcess:
    @pytest.mark.asyncio
    async def test_item_que_saiu_da_fila_e_ignorado(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="sucesso"),
        ])
        # `reschedule` is SYNC (`schedule_tjsp_for_org` is a plain function);
        # handing it an async recorder produced a never-awaited-coroutine
        # warning rather than a failure — a quiet way to test the wrong shape.
        proc, resched = _Recorder(), _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=proc, reschedule=resched,
        )
        assert proc.count == 0
        # It DOES still chain: the item left the queue, it was not a failure.
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_item_na_fila_e_processado_e_encadeia_o_proximo(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        proc, resched = _Recorder(), _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=proc, reschedule=resched,
        )
        assert proc.count == 1
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_falha_marca_erro_e_ainda_encadeia(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
            ],
        )
        async def _boom(*_a, **_k):
            raise RuntimeError("boom")

        resched = _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=_boom, reschedule=resched,
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "boom" in row["erro_mensagem"]
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_cancelamento_nao_reagenda(self):
        """A cancelled task means the process is going away. Rescheduling here
        would race the new process's own recovery."""
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        resched = _SyncRecorder()
        # `asyncio.sleep` is stdlib — an EXTERNAL boundary, the one kind of
        # patch the rule allows (seam 3).
        with patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with pytest.raises(asyncio.CancelledError):
                await service._delayed_tjsp_process(
                    10, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
                    ORG, db, FakeStorageBackend(), reschedule=resched,
                )
        assert resched.count == 0


class TestProcessSingleTjspItem:
    @pytest.mark.asyncio
    async def test_consulta_ausente_marca_erro(self):
        db = _db(certidao_consultas=[], certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        await service._process_single_tjsp_item(
            {"id": "r-tjsp", "consulta_id": "sumiu", "org_id": ORG},
            db, FakeStorageBackend(),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["erro_mensagem"] == "Consulta não encontrada"

    @pytest.mark.asyncio
    async def test_sem_token_marca_erro(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
            ],
        )
        with patch(_CRED, return_value=None):
            await service._process_single_tjsp_item(
                {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
                db, FakeStorageBackend(),
            )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestRecoverStuckProcessando:
    def test_sem_itens_e_no_op(self):
        db = _db(certidao_resultados=[])
        service.recover_stuck_processando(db)

    def test_nao_tjsp_volta_para_pendente(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r1", status="processando")],
        )
        service.recover_stuck_processando(db)
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "pendente"

    def test_tjsp_volta_para_na_fila(self):
        """Not `pendente`: that would make the next run fire immediately, and a
        premature TJSP request RESETS their counter."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", tipo=TJSP_TIPO, status="processando"),
            ],
        )
        service.recover_stuck_processando(db)
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "na_fila"

    def test_mistura_de_tipos_e_recuperada_em_dois_lotes(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="processando"),
                _resultado(id="r2", tipo=TJSP_TIPO, status="processando", ordem=7),
            ],
        )
        service.recover_stuck_processando(db)
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert rows == {"r1": "pendente", "r2": "na_fila"}


class TestRecoverStaleProcessando:
    def test_item_recente_nao_e_tocado(self):
        """The 15-minute floor is what makes this safe to run at any moment —
        the slowest legitimate run is ~12 minutes."""
        recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando", api_requested_at=recent),
        ])
        assert service.recover_stale_processando(db) == 0
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "processando"

    def test_item_antigo_vira_erro_com_mensagem_acionavel(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="processando", api_requested_at=old),
            ],
        )
        assert service.recover_stale_processando(db) == 1
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "reprocessar" in row["erro_mensagem"]

    def test_sem_api_requested_at_nao_e_considerado_stale(self):
        """Those are waiting to START, not stuck mid-call. Resetting them here
        would fight `recover_stuck_processando` over the same rows."""
        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando", api_requested_at=None),
        ])
        assert service.recover_stale_processando(db) == 0


# ---------------------------------------------------------------------------
# cancelar_processamento
# ---------------------------------------------------------------------------


class TestCancelarProcessamento:
    def test_sem_itens_em_andamento_retorna_zero(self):
        db = _db(certidao_resultados=[_resultado(id="r1", status="sucesso")])
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 0
        }

    def test_cancela_pendente_processando_e_na_fila(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="pendente"),
                _resultado(id="r2", status="processando", ordem=2),
                _resultado(id="r3", status="na_fila", tipo=TJSP_TIPO, ordem=7),
                _resultado(id="r4", status="sucesso", ordem=4),
            ],
        )
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 3
        }
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert rows["r4"] == "sucesso"
        assert rows["r1"] == rows["r2"] == rows["r3"] == "erro"

    @pytest.mark.asyncio
    async def test_cancela_a_task_tjsp_agendada(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r3", status="na_fila", tipo=TJSP_TIPO, ordem=7),
            ],
        )

        async def _never():
            await asyncio.sleep(3600)

        task = asyncio.get_running_loop().create_task(_never())
        service._tjsp_scheduled_tasks[ORG] = task
        service.cancelar_processamento("consulta-001", ORG, db)
        await asyncio.sleep(0)
        assert task.cancelled() or task.cancelling()
        assert ORG not in service._tjsp_scheduled_tasks

    def test_nao_cancela_resultados_de_outra_org(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="mine", status="pendente"),
                _resultado(id="theirs", status="pendente", org_id=OTHER_ORG),
            ],
        )
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 1
        }


# ---------------------------------------------------------------------------
# status_counts_por_consulta — the row-cap fix
# ---------------------------------------------------------------------------


class TestStatusCountsPorConsulta:
    def test_conta_sucessos_e_erros_por_consulta(self):
        db = _db(certidao_resultados=[
            _resultado(id="a1", consulta_id="c1", status="sucesso"),
            _resultado(id="a2", consulta_id="c1", status="sucesso", ordem=2),
            _resultado(id="a3", consulta_id="c1", status="erro", ordem=3),
            _resultado(id="b1", consulta_id="c2", status="erro"),
            _resultado(id="p1", consulta_id="c1", status="pendente", ordem=4),
        ])
        sucessos, erros = service.status_counts_por_consulta(["c1", "c2"], ORG, db)
        assert sucessos == {"c1": 2}
        assert erros == {"c1": 1, "c2": 1}

    def test_ignora_resultados_de_outra_org(self):
        db = _db(certidao_resultados=[
            _resultado(id="mine", consulta_id="c1", status="sucesso"),
            _resultado(id="theirs", consulta_id="c1", status="sucesso",
                       org_id=OTHER_ORG, ordem=2),
        ])
        sucessos, _ = service.status_counts_por_consulta(["c1"], ORG, db)
        assert sucessos == {"c1": 1}

    def test_lista_vazia_nao_consulta_o_banco(self):
        db = _db(certidao_resultados=[_resultado(id="a1", status="sucesso")])
        assert service.status_counts_por_consulta([], ORG, db) == ({}, {})

    def test_pagina_alem_do_teto_de_1000_linhas_do_postgrest(self):
        """🔴 REGRESSION. A full page is 200 consultas, each fanning out to one
        resultado per registry type — 2 000 rows against PostgREST's 1 000-row
        cap, which it applies SILENTLY and reports as success.

        The un-paged version of this read did not fail; it returned
        `concluidas: 0` for the back half of the page, indistinguishable from a
        consulta that genuinely had not started. `MockSupabaseClient` enforces
        the same cap, which is what makes this assertable at all.
        """
        rows = []
        for c in range(200):
            for i in range(10):
                rows.append(_resultado(
                    id=f"r{c}-{i}", consulta_id=f"c{c}", status="sucesso", ordem=i + 1,
                ))
        assert len(rows) == 2000
        db = _db(certidao_resultados=rows)

        sucessos, _ = service.status_counts_por_consulta(
            [f"c{c}" for c in range(200)], ORG, db
        )
        # Every consulta must be counted, and counted fully — not just the
        # first 100 that fit under the cap.
        assert len(sucessos) == 200
        assert set(sucessos.values()) == {10}


# ---------------------------------------------------------------------------
# queued_tjsp_for_org
# ---------------------------------------------------------------------------


class TestQueuedTjspForOrg:
    def test_traz_so_na_fila_do_tipo_tjsp_e_da_propria_org(self):
        """The queue is per-ORG because the rate limit is: one InfoSimples
        email per org. Another org's queued item is not in this line.

        ⚠️ Deliberately asserts the SET, not the order. `MockSelectBuilder.order`
        validates the column name and returns `self` — it does not sort — so an
        `== ["a", "b"]` assertion here would be testing the fixture's insertion
        order dressed up as an ORDER BY. The real ordering is `created_at` and
        is what `idx_sw_certidao_resultados_fila_tjsp` (migration 091) indexes;
        proving it needs a live Postgres, not this double.
        """
        db = _db(certidao_resultados=[
            _resultado(id="b", tipo=TJSP_TIPO, status="na_fila",
                       created_at="2026-03-05T11:00:00+00:00"),
            _resultado(id="a", tipo=TJSP_TIPO, status="na_fila",
                       created_at="2026-03-05T10:00:00+00:00"),
            _resultado(id="outro", tipo=TJSP_TIPO, status="na_fila",
                       org_id=OTHER_ORG),
            _resultado(id="pronto", tipo=TJSP_TIPO, status="sucesso"),
            _resultado(id="nao_tjsp", status="na_fila"),
        ])
        assert {r["id"] for r in service.queued_tjsp_for_org(ORG, db)} == {"a", "b"}


# ---------------------------------------------------------------------------
# The stranded-work sweep (scheduler seam)
# ---------------------------------------------------------------------------


class TestScheduler:
    """The stranded-work sweep.

    🔴 THESE ASSERT BEHAVIOUR, NOT CALL-ROUTING. They used to patch
    `service.recover_stale_processando` / `recover_stuck_processando` and assert
    which one the sweep called — which is both a self-monkeypatch and a weaker
    claim: it proves a name was invoked, not that a live request survived. The
    `clients=` DI seam lets the REAL recovery run against a mock DB, so each
    test can assert the thing that actually matters — which rows moved.
    """

    def test_configure_registra_o_job_no_scheduler_do_seed(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        from app.modules.certidoes import scheduler

        scheduler.configure()
        assert any(
            job.id == scheduler.JOB_ID for job in seed_scheduler.scheduler.get_jobs()
        ) or scheduler.JOB_ID in {
            j.id for j in getattr(seed_scheduler.scheduler, "_pending_jobs", [])
        }

    @pytest.mark.asyncio
    async def test_sweep_nunca_levanta(self):
        """🔴 A scheduler job that throws is, in some runtimes, a job that stops
        being scheduled — which removes the safety net this IS."""
        from app.modules.certidoes import scheduler

        def _explode():
            raise RuntimeError("db gone")

        await scheduler.sweep_stranded(clients=_explode)

    @pytest.mark.asyncio
    async def test_sweep_sem_admin_client_e_no_op(self):
        """`_clients` answers `(None, None)` when there is no admin client; the
        sweep must return without touching anything."""
        from app.modules.certidoes import scheduler

        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando",
                       api_requested_at="2020-01-01T00:00:00+00:00"),
        ])
        await scheduler.sweep_stranded(clients=lambda: (None, None))
        # Ancient row, and still untouched — the sweep genuinely did nothing.
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "processando"

    @pytest.mark.asyncio
    async def test_sweep_nao_derruba_requisicao_viva(self):
        """🔴 THE reason the recurring job uses the STALE variant.

        A row that started 2 minutes ago belongs to a request that is very
        likely still in flight (the slowest legitimate run is ~12 min). The
        unconditional `recover_stuck_processando` would reset it out from under
        the live task; the stale variant, with its 15-minute floor, must not.
        """
        from app.modules.certidoes import scheduler

        fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="viva", status="processando", api_requested_at=fresh),
            ],
        )
        await scheduler.sweep_stranded(
            clients=lambda: (db, FakeStorageBackend())
        )
        assert db.table("certidao_resultados").select("*").eq(
            "id", "viva"
        ).execute().data[0]["status"] == "processando"

    @pytest.mark.asyncio
    async def test_sweep_recupera_o_que_encalhou_de_verdade(self):
        """The other half: a genuinely abandoned row DOES get recovered, so the
        test above cannot pass by the sweep simply doing nothing."""
        from app.modules.certidoes import scheduler

        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="encalhado", status="processando",
                           api_requested_at=old),
            ],
        )
        await scheduler.sweep_stranded(
            clients=lambda: (db, FakeStorageBackend())
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "encalhado"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "reprocessar" in row["erro_mensagem"]

    def test_startup_recovery_reseta_incondicionalmente(self):
        """At process start nothing of OURS is running, so the unconditional
        reset is correct there — and it is what makes a row abandoned by the
        PREVIOUS process recoverable immediately rather than in 15 minutes."""
        from app.modules.certidoes import scheduler

        fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="orfao", status="processando", api_requested_at=fresh),
                _resultado(id="orfao-tjsp", tipo=TJSP_TIPO, ordem=7,
                           status="processando", api_requested_at=fresh),
            ],
        )
        scheduler.run_startup_recovery(clients=lambda: (db, FakeStorageBackend()))
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        # Same 2-minute-old rows the sweep above deliberately leaves alone.
        assert rows == {"orfao": "pendente", "orfao-tjsp": "na_fila"}

    def test_startup_recovery_nao_e_fatal(self):
        """A lifespan hook is a SIDE EFFECT, never a precondition for serving.
        → KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md"""
        from app.modules.certidoes import scheduler

        def _explode():
            raise RuntimeError("x")

        scheduler.run_startup_recovery(clients=_explode)
