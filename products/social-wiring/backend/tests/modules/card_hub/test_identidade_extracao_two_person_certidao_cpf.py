"""🔴 THE BUG THIS FILE CLOSES — real, measured (live prod test, 2026-09-30)

A CNJ text-layer certidão de casamento names two co-equal holders. When the
seed extractor's own titular-hint attribution (`documents.real.
_conjuge_do_titular`) does not resolve which of the two is THIS card's
person — no `ConjugeLido` in `fields.conjuges` comes back marked
`.titular=True` — the flat, whole-document `fields.cpf` has no notion of
which spouse it belongs to. Before this fix, `_valores_lidos` fed that flat
CPF into `aplicar_campos_ao_cliente` unconditionally, at ANY confidence
(D1's own "any read fills an empty field" rule), and it landed on the
titular's `clientes.cpf` — in production, the OTHER spouse's CPF, on a card
that had none yet.

The fix: `identidade_extracao_service._processar` now withholds `cpf`
entirely (never applies it, never even records it on the document's own
`extracao_cpf` audit column) whenever the document is a two-person type
(`divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS`) and no spouse was
attributed as the titular — the same "never guessed" posture the seed
extractor already takes for an unresolved `titulares_multiplos` name.

Invented names/CPFs below (both real, check-digit-valid CPFs, so the
"different fact" comparison is genuinely exercised) — never real people's
data.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import ExtractionConfidence, FakeIdentityExtractor, IdentityFields, TextSource
from noctusai_lib.integrations.documents.conjuges import ConjugeLido

from tests.modules.card_hub.test_identidade_extracao import ORG_UUID, _cliente, _documento, _setup

RICARDO_CPF = "111.444.777-35"
FLAVIA_CPF = "529.982.247-25"


class TestUnattributedFlatCpfOnTwoPersonCertidao:
    @pytest.mark.asyncio
    async def test_titular_with_no_cpf_on_file_stays_empty_when_neither_spouse_is_attributed(
        self, client, scoped,
    ):
        """Neither `ConjugeLido` is marked `.titular` — the extractor's own
        hint attribution did not resolve who this card is. The flat `cpf`
        below is deliberately the SPOUSE'S, not this card's own — exactly
        the wrong-person value production wrote before this fix — and it
        must never reach `clientes.cpf`."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "FLAVIA REGINA TAVARES", "cpf": None},
        )
        resultado = IdentityFields(
            estado_civil="casado",
            estado_civil_confianca=ExtractionConfidence.ALTA,
            cpf=RICARDO_CPF,
            cpf_confianca=ExtractionConfidence.BAIXA,
            source=TextSource.TEXT_LAYER,
            aviso="titulares_multiplos",
            aviso_mensagem="cpf (2 titulares)",
            conjuges=(
                ConjugeLido(nome="RICARDO AUGUSTO TAVARES", cpf=RICARDO_CPF, titular=False),
                ConjugeLido(nome="FLAVIA REGINA TAVARES", cpf=FLAVIA_CPF, titular=False),
            ),
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(resultado),
        )
        assert out["status"] != "erro"
        assert out["aplicado_ao_cliente"]["cpf"] is False

        c = _cliente(scoped, cid)
        assert c.get("cpf") is None
        # Never even landed on the document's own audit column — an
        # unattributed reading is withheld, not merely un-applied.
        d = _documento(scoped, did)
        assert d.get("extracao_cpf") is None
        # The couple-level fact on the SAME document still applies — this
        # guard is scoped to `cpf` alone.
        assert c.get("estado_civil") == "casado"

    @pytest.mark.asyncio
    async def test_the_attributed_spouses_own_cpf_still_applies_normally(
        self, client, scoped,
    ):
        """Positive control: when the extractor DID mark a spouse as the
        titular (attribution succeeded), that spouse's own CPF is applied
        exactly as before this fix — the guard only withholds the
        UNATTRIBUTED case."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "RICARDO AUGUSTO TAVARES", "cpf": None},
        )
        resultado = IdentityFields(
            estado_civil="casado",
            estado_civil_confianca=ExtractionConfidence.ALTA,
            cpf=RICARDO_CPF,
            cpf_confianca=ExtractionConfidence.ALTA,
            source=TextSource.TEXT_LAYER,
            conjuges=(
                ConjugeLido(nome="RICARDO AUGUSTO TAVARES", cpf=RICARDO_CPF, titular=True),
                ConjugeLido(nome="FLAVIA REGINA TAVARES", cpf=FLAVIA_CPF, titular=False),
            ),
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(resultado),
        )
        assert out["aplicado_ao_cliente"]["cpf"] is True
        assert _cliente(scoped, cid)["cpf"] == RICARDO_CPF

    @pytest.mark.asyncio
    async def test_a_single_holder_document_is_unaffected(self, client, scoped):
        """No `conjuges` at all (an RG, or any single-holder document) never
        trips this guard — `_valores_lidos`' flat `cpf` is the only holder's
        by construction."""
        cid, did, storage = await _setup(scoped, tipo="rg", cliente={"nome": "ANA TESTE", "cpf": None})
        resultado = IdentityFields(
            cpf=RICARDO_CPF,
            cpf_confianca=ExtractionConfidence.ALTA,
            source=TextSource.TEXT_LAYER,
        )
        out = await svc.extrair_identidade(
            scoped, storage, ORG_UUID, UUID(cid), UUID(did),
            extractor=FakeIdentityExtractor(resultado),
        )
        assert out["aplicado_ao_cliente"]["cpf"] is True
        assert _cliente(scoped, cid)["cpf"] == RICARDO_CPF
