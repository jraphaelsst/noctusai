"""F82 (2026-10-24, prod): a CEP read off the WRONG block never moves a party.

A gas bill's reading carried the utility's own sender CEP (another city) next
to the customer's street; the CEP lookup then rewrote cidade/UF/bairro to the
utility's. The CEP is cross-checked against the street and the locality the
document printed beside the holder; a contradiction holds the reading back as
a suggestion. Every value below is a synthetic fixture.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from noctusai_lib.integrations.cep import CepEndereco, FakeCepLookupAdapter
from noctusai_lib.integrations.documents.address import EnderecoLido

from app.modules.card_hub import identidade_extracao_service as svc
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import (
    ORG_UUID,
    _cliente,
    _comprovante,
    _conflitos,
    _documento,
    _extrair,
    _setup,
)

CEP_TITULAR = "06700-100"
CEP_REMETENTE = "04100-200"


def _ceps() -> FakeCepLookupAdapter:
    return FakeCepLookupAdapter({
        CEP_TITULAR: CepEndereco(
            cep=CEP_TITULAR, cidade="Itapecerica", uf="SP",
            logradouro="Estrada Municipal Vale Dourado", bairro="Jardim Exemplo",
        ),
        CEP_REMETENTE: CepEndereco(
            cep=CEP_REMETENTE, cidade="São Paulo", uf="SP",
            logradouro="Rua Bom Retiro", bairro="Vila Exemplo",
        ),
        "06799-000": CepEndereco(cep="06799-000", cidade="Outra Cidade", uf="SP"),
    })


def _leitura(cep=CEP_TITULAR, cidade="ITAPECERICA", **extra) -> EnderecoLido:
    base = dict(
        cep=cep, logradouro="Estrada Municipal Vale Dourado", numero="512",
        complemento="APTO 33", bairro=None, cidade=cidade, uf="SP",
        titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
    )
    base.update(extra)
    return EnderecoLido(**base)


def _vazio_cliente(scoped) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Ana Paula Souza")])
    scoped.set_table_data("cliente_campo_conflitos", [])
    return cid


class TestCepCrossCheck:
    def test_the_holders_block_cep_applies_with_its_own_city(self, client, scoped):
        cid = _vazio_cliente(scoped)
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", _leitura().partes(),
            documento_id=uuid4(), cep_lookup=_ceps(),
        )
        row = _cliente(scoped, cid)
        assert aplicado and conflito is None
        assert (row["endereco_cidade"], row["endereco_uf"]) == ("Itapecerica", "SP")
        assert row["endereco_bairro"] == "Jardim Exemplo"

    def test_a_cep_naming_another_street_is_never_applied(self, client, scoped):
        """The triggering shape: the sender's CEP beside the customer's
        street (its own city even read consistently with that CEP)."""
        cid = _vazio_cliente(scoped)
        avisos: list[str] = []
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            _leitura(cep=CEP_REMETENTE, cidade="Vila Exemplo - São Paulo").partes(),
            documento_id=uuid4(), cep_lookup=_ceps(), avisos=avisos,
        )
        row = _cliente(scoped, cid)
        assert (aplicado, conflito) == (False, None)
        assert svc.AVISO_CEP_DIVERGE in avisos
        assert row.get("endereco_cidade") is None and row.get("endereco_bairro") is None

    def test_a_streetless_cep_of_another_city_is_never_applied(self, client, scoped):
        cid = _vazio_cliente(scoped)
        avisos: list[str] = []
        aplicado, _ = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            _leitura(cep="06799-000").partes(),
            documento_id=uuid4(), cep_lookup=_ceps(), avisos=avisos,
        )
        assert aplicado is False
        assert svc.AVISO_CEP_DIVERGE in avisos

    def test_a_cep_naming_the_printed_street_still_corrects_the_city(self, client, scoped):
        """F3 kept: the street confirms the CEP is this address's, so a
        misread city (a neighbourhood in the field) is corrected."""
        cid = _vazio_cliente(scoped)
        aplicado, _ = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            _leitura(cidade="JARDIM ERRADO", uf="RJ").partes(),
            documento_id=uuid4(), cep_lookup=_ceps(),
        )
        assert aplicado
        assert (_cliente(scoped, cid)["endereco_cidade"], _cliente(scoped, cid)["endereco_uf"]) == (
            "Itapecerica", "SP",
        )


class TestTheExtractionFlagsAndHoldsBack:
    @pytest.mark.asyncio
    async def test_document_is_flagged_baixa_and_offered_as_a_suggestion(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        await _extrair(
            scoped, storage, cid, did,
            _comprovante(_leitura(cep=CEP_REMETENTE, cidade="Vila Exemplo - São Paulo")),
            cep_lookup=_ceps(),
        )
        doc = _documento(scoped, did)
        assert svc.AVISO_CEP_DIVERGE in (doc.get("extracao_aviso") or "").split("+")
        assert doc["extracao_endereco_confianca"] == "baixa"
        assert _cliente(scoped, cid).get("endereco_logradouro") is None
        assert [c for c in _conflitos(scoped) if c["status"] == "pendente"] == []


class TestLerNovamente:
    """A re-read of the SAME still machine-pending document replaces the
    address a pre-fix read applied — unless a human confirmed it."""

    def _ja_aplicado_errado(self, scoped, did: str, **extra) -> str:
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep=CEP_REMETENTE, endereco_logradouro="Estrada Municipal Vale Dorado",
            endereco_numero="512", endereco_complemento="APTO 33",
            endereco_bairro="Vila Exemplo", endereco_bairro_origem="cep",
            endereco_cidade="São Paulo", endereco_uf="SP",
            endereco_origem="comprovante_endereco", endereco_documento_id=did,
            **extra,
        )])
        scoped.set_table_data("cliente_campo_conflitos", [])
        return cid

    def test_a_re_read_replaces_the_wrong_city(self, client, scoped):
        did = str(uuid4())
        cid = self._ja_aplicado_errado(scoped, did)
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", _leitura().partes(),
            documento_id=UUID(did), cep_lookup=_ceps(),
        )
        row = _cliente(scoped, cid)
        assert aplicado and conflito is None
        assert row["endereco_cep"] == CEP_TITULAR
        assert (row["endereco_cidade"], row["endereco_bairro"]) == ("Itapecerica", "Jardim Exemplo")

    def test_an_operator_confirmed_address_is_never_replaced(self, client, scoped):
        did = str(uuid4())
        cid = self._ja_aplicado_errado(
            scoped, did,
            endereco_confirmado_por=str(uuid4()),
            endereco_confirmado_em="2026-10-20T00:00:00+00:00",
        )
        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", _leitura().partes(),
            documento_id=UUID(did), cep_lookup=_ceps(),
        )
        assert _cliente(scoped, cid)["endereco_cidade"] == "São Paulo"


class TestARereadThatNoLongerSupportsTheAddressWithdrawsIt:
    """F82 round 2 (prod): the fixed reader's "Ler novamente" read nothing,
    and the wrong address a pre-fix read of THAT document applied stood."""

    def _aplicado_por(self, scoped, did: str, **extra) -> str:
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep=CEP_REMETENTE, endereco_logradouro="Estrada Municipal Vale Dourado",
            endereco_numero="512", endereco_bairro="Vila Exemplo", endereco_bairro_origem="cep",
            endereco_cidade="São Paulo", endereco_uf="SP",
            endereco_origem="comprovante_endereco", endereco_documento_id=did, **extra,
        )])
        return cid

    @pytest.mark.asyncio
    async def test_a_reread_with_no_address_clears_the_group_it_applied(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        cid = self._aplicado_por(scoped, did)
        await _extrair(scoped, storage, cid, did, _comprovante(None), cep_lookup=_ceps())
        row = _cliente(scoped, cid)
        for p in ("cep", "logradouro", "numero", "bairro", "cidade", "uf"):
            assert row.get(f"endereco_{p}") is None
        assert row.get("endereco_documento_id") is None
        assert row.get("endereco_bairro_origem") is None

    @pytest.mark.asyncio
    async def test_a_held_back_reread_clears_it_too(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        cid = self._aplicado_por(scoped, did)
        await _extrair(
            scoped, storage, cid, did,
            _comprovante(_leitura(cep=CEP_REMETENTE, cidade="Vila Exemplo - São Paulo")),
            cep_lookup=_ceps(),
        )
        assert _cliente(scoped, cid).get("endereco_cep") is None

    @pytest.mark.asyncio
    async def test_a_confirmed_group_is_never_withdrawn(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        cid = self._aplicado_por(
            scoped, did, endereco_confirmado_por=str(uuid4()),
            endereco_confirmado_em="2026-10-20T00:00:00+00:00",
        )
        await _extrair(scoped, storage, cid, did, _comprovante(None), cep_lookup=_ceps())
        assert _cliente(scoped, cid)["endereco_cep"] == CEP_REMETENTE

    @pytest.mark.asyncio
    async def test_another_documents_group_is_never_withdrawn(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        cid = self._aplicado_por(scoped, str(uuid4()))
        await _extrair(scoped, storage, cid, did, _comprovante(None), cep_lookup=_ceps())
        assert _cliente(scoped, cid)["endereco_cep"] == CEP_REMETENTE
