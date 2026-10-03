"""A CPF whose mod-11 check digits fail is NOT READ (P4/871, 2026-10-01).

An `rg` reading at `baixa` once wrote a check-digit-failing CPF onto
`clientes.cpf`; a wrong CPF in a signed contract is worse than a gap.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.card_hub import ficha_cadastral_service as ficha_svc
from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from tests.modules.card_hub.test_identidade_extracao import (
    ORG_UUID,
    _cliente,
    _documento,
    _setup,
)

CPF_VALIDO = "529.982.247-25"
CPF_INVALIDO = "529.982.247-26"


def _rg(cpf: str) -> IdentityFields:
    return IdentityFields(
        cpf=cpf,
        cpf_confianca=ExtractionConfidence.BAIXA,
        cpf_rotulo="CPF",
        source=TextSource.OCR,
    )


class TestCpfInvalidoNaoEGravado:
    @pytest.mark.asyncio
    async def test_invalid_check_digits_from_an_rg_is_not_written(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="rg")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_rg(CPF_INVALIDO)),
        )
        assert out["aplicado_ao_cliente"].get("cpf") is False
        c = _cliente(scoped, cid)
        assert not c.get("cpf")
        assert not c.get("cpf_origem")
        assert _documento(scoped, did).get("extracao_aviso") == "cpf_invalido"

    @pytest.mark.asyncio
    async def test_valid_check_digits_is_still_written(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="rg")
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_rg(CPF_VALIDO)),
        )
        assert out["aplicado_ao_cliente"]["cpf"] is True
        c = _cliente(scoped, cid)
        assert c["cpf"] == CPF_VALIDO
        assert c["cpf_origem"] == "rg"

    @pytest.mark.asyncio
    async def test_the_write_chokepoint_refuses_it_for_any_source(self, client, scoped):
        """Direct call — ficha/crednet/certidão all funnel through here."""
        cid, _did, _storage = await _setup(scoped, tipo="rg")
        avisos: list[str] = []
        aplicados, _ = svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral",
            {"cpf": (CPF_INVALIDO, "alta", "CPF", True)},
            avisos_cpf_invalido=avisos,
        )
        assert aplicados["cpf"] is False
        assert avisos == ["cpf"]
        assert not _cliente(scoped, cid).get("cpf")


def test_an_invalid_cpf_is_never_a_holder_matching_key():
    mapa = ficha_svc.mapa_cpf([
        {"id": "a", "cpf": CPF_INVALIDO},
        {"id": "b", "cpf": CPF_VALIDO},
    ])
    assert list(mapa) == ["52998224725"]
