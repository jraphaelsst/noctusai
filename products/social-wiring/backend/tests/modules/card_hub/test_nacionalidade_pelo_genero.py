"""The nacionalidade follows the person's gênero (item 4).

The extractor's canonical gentílico is masculine ("brasileiro"); a woman's
record must read "brasileira" — auto-applied, suggested and confirmed alike.
Unknown gênero stays neutral and the suggestion asks for it.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from tests.modules.card_hub.test_identidade_extracao import ORG_UUID, _cliente, _documento, _setup


def _leitura(conf=ExtractionConfidence.ALTA, value="brasileiro") -> IdentityFields:
    return IdentityFields(
        nacionalidade=value, nacionalidade_confianca=conf,
        nacionalidade_rotulo="NACIONALIDADE", source=TextSource.TEXT_LAYER,
    )


class TestPuro:
    @pytest.mark.parametrize("valor,genero,esperado", [
        ("brasileiro", "Feminino", "brasileira"),
        ("brasileira", "Masculino", "brasileiro"),
        ("brasileiro", "Masculino", "brasileiro"),
        ("italiano", "Feminino", "italiana"),
        ("brasileiro", None, "brasileiro"),         # unknown gênero -> neutral
        ("Brasileiro(a)", "Feminino", "Brasileiro(a)"),  # free text untouched
    ])
    def test_inflects_only_when_the_gender_is_known(self, valor, genero, esperado):
        assert svc.nacionalidade_pelo_genero(valor, genero) == esperado


class TestEscrita:
    @pytest.mark.asyncio
    async def test_auto_apply_writes_the_feminine_for_a_woman(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="cnh", cliente={"genero": "Feminino"})
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        assert _cliente(scoped, cid)["nacionalidade"] == "brasileira"
        # the document keeps what it read, untouched
        assert _documento(scoped, did)["extracao_nacionalidade"] == "brasileiro"

    @pytest.mark.asyncio
    async def test_a_man_keeps_the_masculine(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="cnh", cliente={"genero": "Masculino"})
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        assert _cliente(scoped, cid)["nacionalidade"] == "brasileiro"


class TestSugestaoEConfirmacao:
    @pytest.mark.asyncio
    async def test_suggestion_and_confirmation_are_inflected(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"genero": "Feminino", "nacionalidade_origem": "manual", "nacionalidade": None},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        assert not _cliente(scoped, cid).get("nacionalidade")  # human-cleared: only offered
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))["nacionalidade"]
        assert sug["valor"] == "brasileira" and sug["aviso"] is None
        svc.confirmar_sugestao(
            scoped, ORG_UUID, UUID(cid), UUID(did), item_key="nacionalidade", user_id=uuid4()
        )
        assert _cliente(scoped, cid)["nacionalidade"] == "brasileira"

    @pytest.mark.asyncio
    async def test_unknown_gender_stays_neutral_and_asks(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"genero": None, "nacionalidade_origem": "manual", "nacionalidade": None},
        )
        await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(_leitura()),
        )
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))["nacionalidade"]
        assert sug["valor"] == "brasileiro" and sug["aviso"] == "genero_desconhecido"
