"""The real extractor — the two-rung ladder, then the pure parser.

WHY THIS COMPOSES `integrations.media` RATHER THAN RE-DOING IT
-------------------------------------------------------------
`media` already owns "bytes → text": PDF text layer via PyMuPDF with a
pdfminer fallback, and rasterize→vision (with refusal-retry) for scanned
documents. Re-implementing that here would fork a validated seam — which
is exactly what `products/erp-imobiliario/.../matricula_service.py` did,
and why it pays for a vision call on every page of PDFs that carry a
perfectly good text layer.

So this module owns only what `media` does not: **turning a document's
text into typed identity fields.**

THE LADDER LIVES IN `ladder.py`
-------------------------------
Choosing the cheapest rung (PDF text layer → rasterize→vision) used to be
this class's private `_to_text`. It moved to `DocumentTextLadder` the moment
a second extractor needed it — see that module's header. This class now
composes one and keeps only the identity-specific half.

Which rung answered is still recorded on the result, because it is the best
available predictor of transcription error and the thing an auditor needs
to see later.

🔴 RESIDUAL RISK, STATED PLAINLY
--------------------------------
The plausibility gate in `birthdate` catches gross OCR damage (a year of
1830, a date in 2027). It does NOT catch a confusion between two
*plausible* years — `1980` misread as `1930` passes every check this
module can make. That risk is inherent to reading a photographed
document, and it is why the consumer contract requires storing
`source` + `matched_label` as provenance: the value stays attributable and
correctable rather than becoming an anonymous fact in a column.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.civil_status import (
    find_data_casamento,
    find_data_emissao,
    find_estado_civil,
    find_regime_bens,
)
from noctusai_lib.integrations.documents.cpf import find_cpf, find_cpf_conflitos
from noctusai_lib.integrations.documents.gender import find_gender
from noctusai_lib.integrations.documents.fake import classify_kind
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.name import find_name, find_name_conflitos
from noctusai_lib.integrations.documents.rg import find_rg, find_rg_orgao
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

logger = logging.getLogger(__name__)


class LadderIdentityExtractor:
    """Text-layer-first, vision-second identity extractor.

    Construct via `make_identity_extractor(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        document_prompt: Optional[str] = None,
        resolver=None,
        max_pages: int | None = -1,
        provider: Optional[str] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=document_prompt,
            resolver=resolver,
            max_pages=max_pages,
            provider=provider,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> IdentityFields:
        kind = classify_kind(mimetype, filename)
        if not content:
            return IdentityFields(
                kind=kind,
                error="empty_document",
                error_message="no bytes to read",
            )

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return IdentityFields(kind=kind, source=source, error=err[0], error_message=err[1])
        if not text.strip():
            # Legible pipeline, nothing readable in it. Not an error —
            # a caller must be able to tell this apart from a crash,
            # because retrying it is pointless.
            return IdentityFields(kind=kind, source=source)

        data, data_conf, data_label = find_birthdate(text)
        nome, nome_conf, nome_label = find_name(text)
        nome_conf = self._temper_name_confidence(nome_conf, source)
        # Gender is NOT tempered by source, unlike the name. Its alphabet has
        # two elements and its parser refuses every unlabelled single letter,
        # so an OCR pass cannot turn "Masculino" into a different VALID value —
        # it can only turn it into nothing. The name's risk is a plausible
        # misreading; this field has no plausible misreadings to make.
        genero, genero_conf, genero_label = find_gender(text)

        # CPF is NOT tempered by source either, and for a reason the other
        # fields cannot claim: it verifies its own two check digits. An OCR
        # digit confusion (0/O, 5/S, 8/B) breaks the mod-11 arithmetic, so a
        # vision pass that misreads a CPF produces a value the parser has
        # already demoted to `baixa` on its own. Tempering here would demote
        # the reads that survived that gate — which are precisely the ones
        # worth trusting.
        cpf, cpf_conf, cpf_label = find_cpf(text)

        # The RG has NO check digit anywhere in Brazil, so it gets the name's
        # treatment: a vision-read RG is a suggestion. It has no structural
        # self-evidence to fall back on, which makes it the weakest of the
        # five — see `rg.py`.
        rg, rg_conf, rg_label = find_rg(text)
        rg_conf = self._temper_name_confidence(rg_conf, source)
        rg_orgao, rg_orgao_conf = find_rg_orgao(text, rg)
        rg_orgao_conf = self._temper_name_confidence(rg_orgao_conf, source)
        if not rg:
            # 🔴 AN ISSUING BODY WITH NO RG NUMBER BESIDE IT IDENTIFIES
            # NOTHING. `find_rg_orgao` finds its match by SHAPE alone (an
            # acronym bound to a UF), independently of whether `find_rg`
            # found anything at all — so on a document that carries no RG
            # (a certidão de casamento, say), an unrelated place name in an
            # `ACRONYM/UF` shape ("Comarca de Cotia/SP") can still match and
            # get returned as a fabricated issuer. `rg_orgao` TRAVELS WITH
            # `rg` (see `types.IdentityFields.rg_orgao`'s own comment) — this
            # is that rule enforced at the point the two are combined, not
            # merely documented as a persistence-time convention a consumer
            # might forget to check.
            rg_orgao, rg_orgao_conf = None, ExtractionConfidence.NENHUMA.value

        # Estado civil / regime de bens are NOT tempered by source, for the
        # same reason `genero` is not: both parsers require an explicit
        # label, an AVERBAÇÃO event keyword, or the regime-de-bens phrase
        # itself (structural evidence, like the CPF check digit) — none of
        # which an OCR misread can turn into a DIFFERENT valid vocabulary
        # token. It can only turn a real reading into nothing.
        estado_civil, estado_civil_conf, estado_civil_label = find_estado_civil(text)
        regime_bens, regime_bens_conf, regime_bens_label = find_regime_bens(text)

        # `data_casamento` / `data_emissao` (contract F6, migration 117) — NOT
        # tempered by source, same reasoning `data_nascimento` above already
        # settles for a date: the plausibility gate plus the explicit-label
        # requirement (or, for `data_emissao`'s fallback, the finder's own
        # `baixa` typing of a position-based guess) already carries the
        # tempering a date needs; a second demotion here would double-count
        # it. Run unconditionally, exactly like every other field here — this
        # extractor is document-type-agnostic, and a document that carries
        # neither pattern simply returns `nenhuma`.
        data_casamento, data_casamento_conf, data_casamento_label = (
            find_data_casamento(text)
        )
        data_emissao, data_emissao_conf, data_emissao_label = find_data_emissao(text)

        # 🔴 NAMED REFUSAL — SEE THE MODULE DOCSTRING FOR WHY THIS EXISTS
        # -------------------------------------------------------------------
        # A certidão de casamento names TWO people with equal prominence
        # (`NOMES`, both spouses' CPFs), and `nome`/`cpf` above are each
        # single columns — `find_name`/`find_cpf` correctly decline to guess
        # which spouse belongs there, but that decline is INDISTINGUISHABLE
        # from "the document simply does not carry a name/CPF" once it lands
        # in `nome=None`/`cpf=None`. `find_name_conflitos`/`find_cpf_conflitos`
        # answer the question those two functions cannot: WHY was it absent.
        #
        # No disambiguation hint is implemented here (an `expected_nome` the
        # caller already knows the cliente_id for would be the better fix —
        # see the module docstring) because wiring one up requires the
        # PRODUCT-side caller to supply it, which is out of this module's
        # scope; a hint parameter with nothing that ever passes it would be
        # a scaffolded half-feature. Filed as
        # `NOC-REMEDIATE[identity-extractor-disambiguation-hint]` — 2026-09-21.
        multiplos_titulares: list[str] = []
        if nome is None:
            conflito_nome = find_name_conflitos(text)
            if conflito_nome:
                multiplos_titulares.append(f"nome ({len(conflito_nome)} titulares)")
        if cpf is None:
            conflito_cpf = find_cpf_conflitos(text)
            if conflito_cpf:
                multiplos_titulares.append(f"cpf ({len(conflito_cpf)} titulares)")

        erro: Optional[str] = None
        erro_mensagem: Optional[str] = None
        if multiplos_titulares:
            erro = "titulares_multiplos"
            erro_mensagem = (
                "documento nomeia mais de um titular com igual proeminencia "
                "para: " + ", ".join(multiplos_titulares) + " — nao gravado "
                "sem escolha explicita de qual titular"
            )

        return IdentityFields(
            kind=kind,
            error=erro,
            error_message=erro_mensagem,
            data_nascimento=data,
            data_nascimento_confianca=ExtractionConfidence(data_conf),
            data_nascimento_rotulo=data_label,
            nome=nome,
            nome_confianca=ExtractionConfidence(nome_conf),
            nome_rotulo=nome_label,
            genero=genero,
            genero_confianca=ExtractionConfidence(genero_conf),
            genero_rotulo=genero_label,
            cpf=cpf,
            cpf_confianca=ExtractionConfidence(cpf_conf),
            cpf_rotulo=cpf_label,
            rg=rg,
            rg_confianca=ExtractionConfidence(rg_conf),
            rg_rotulo=rg_label,
            rg_orgao=rg_orgao,
            rg_orgao_confianca=ExtractionConfidence(rg_orgao_conf),
            estado_civil=estado_civil,
            estado_civil_confianca=ExtractionConfidence(estado_civil_conf),
            estado_civil_rotulo=estado_civil_label,
            regime_bens=regime_bens,
            regime_bens_confianca=ExtractionConfidence(regime_bens_conf),
            regime_bens_rotulo=regime_bens_label,
            data_casamento=data_casamento,
            data_casamento_confianca=ExtractionConfidence(data_casamento_conf),
            data_casamento_rotulo=data_casamento_label,
            data_emissao=data_emissao,
            data_emissao_confianca=ExtractionConfidence(data_emissao_conf),
            data_emissao_rotulo=data_emissao_label,
            source=source,
        )

    @staticmethod
    def _temper_name_confidence(confidence: str, source: TextSource) -> str:
        """A value read off a vision pass is a suggestion, never a fact.

        🔴 THE NAME IS NO LONGER ITS ONLY CALLER — it now also guards `rg`
        and `rg_orgao`. The method keeps its original name deliberately:
        it is referenced from `matricula_extractor.py` and from
        social-wiring's `identidade_extracao_service.py`, so renaming it
        would ripple across a documented seam to buy nothing but a tidier
        word. What generalised is the RULE, stated below; `nome` is simply
        the field that discovered it.

        The rule: **a field with no structural self-evidence may not be
        written unattended off a transcription.** `nome` qualifies because
        free text has no checkable shape. `rg` qualifies for a stronger
        reason — there is no national RG format and no check digit
        anywhere in Brazil, so a misread RG is indistinguishable from a
        real one. `cpf` does NOT qualify and is deliberately not passed
        through here: its check digits fail under OCR damage, so its own
        parser has already demoted a mangled read.

        🔴 THIS IS THE GATE ON AN OVERWRITE, WHICH IS WHY IT IS STRICTER
        THAN THE BIRTHDATE'S.

        The birthdate is only ever written into an empty column, so its
        worst case is a wrong value where there was none. The name
        deliberately REPLACES whatever is already on the record — the
        official document is meant to win — so its worst case is
        destroying a correct, human-entered name.

        A PDF text layer is an exact transcription: those characters ARE
        the document's characters, and `alta` survives. A vision pass over
        a photographed card is a transcription by a model, and a
        transcription error produces a name that is well-formed, plausible
        and wrong — invisible to every structural check `name` can make.
        So it degrades to `baixa`, which routes it into the existing
        confirm/discard surface. The document still wins; a human just
        spends one click agreeing that the model read it correctly.
        """
        if confidence == "alta" and source is not TextSource.TEXT_LAYER:
            return "baixa"
        return confidence


__all__ = ["LadderIdentityExtractor"]
