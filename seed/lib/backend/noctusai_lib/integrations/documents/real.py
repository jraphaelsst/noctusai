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
import re
from dataclasses import replace
from datetime import date
from typing import Any, Mapping, Optional

import noctusai_lib.integrations.documents.autoridade as autoridade
from noctusai_lib.integrations.documents.address import find_endereco
from noctusai_lib.integrations.documents.birthdate import MIN_AGE, find_birthdate
from noctusai_lib.integrations.documents.civil_status import (
    find_data_casamento,
    find_data_emissao,
    find_estado_civil,
    ROTULO_CASADO_POR_CERTIDAO,
    find_estado_civil_certidao_casamento,
    find_regime_bens,
)
from noctusai_lib.integrations.documents.conjuges import ConjugeLido, find_conjuges
from noctusai_lib.integrations.documents.cpf import (
    find_cpf,
    find_cpf_conflitos,
    only_digits,
)
from noctusai_lib.integrations.documents.filiacao import find_filiacao, find_naturalidade
from noctusai_lib.integrations.documents.gender import find_gender
from noctusai_lib.integrations.documents.fake import classify_kind
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder, LeituraTexto
from noctusai_lib.integrations.documents.legibilidade import (
    AVISO_LEITURA_COMPROMETIDA,
    avaliar_legibilidade,
)
from noctusai_lib.integrations.documents.misfile import (
    AVISO_TIPO_DOCUMENTO_DIVERGENTE,
    classificar_tipo_provavel,
    mensagem_tipo_divergente,
    tipo_civil_divergente,
)
from noctusai_lib.integrations.documents.providers import (
    DEFAULT_DOCUMENT_PROVIDER,
    ESCALATION_OCR_MODELS,
    OCR_MODELS,
)
import noctusai_lib.integrations.documents.confianca as confianca
import noctusai_lib.integrations.documents.releitura as releitura
import noctusai_lib.integrations.documents.roteamento as roteamento
from noctusai_lib.integrations.llm.usage import coletar_uso
from noctusai_lib.integrations.documents.ancora import ancora_falhou
from noctusai_lib.integrations.documents.transcription import (
    identity_document_render_dpi_policy,
    render_dpi_policy_for,
)
from noctusai_lib.integrations.documents.nacionalidade import find_nacionalidade
from noctusai_lib.integrations.documents.name import (
    chave_nome,
    find_name,
    find_name_conflitos,
    nomes_compativeis,
)
from noctusai_lib.integrations.documents.numeros_documento import (
    find_matricula_certidao,
    find_registro_cnh,
)
from noctusai_lib.integrations.documents.profession import (
    VOCABULARIO_INVALIDO,
    find_profissao,
    find_profissao_invalida,
)
from noctusai_lib.integrations.documents.rg import (
    find_caixa_identidade_cnh,
    find_rg,
    find_rg_orgao,
    find_rne,
    only_alnum,
)
from noctusai_lib.integrations.documents.types import (
    CAMPOS,
    ExtractionConfidence,
    IdentityDocumentKind,
    CustoLeitura,
    DesfechoCampo,
    IdentityFields,
    ResumoRoteamento,
    TextSource,
    TitularEsperado,
)

from noctusai_lib.primitives import identificador as _ident

logger = logging.getLogger(__name__)

#: `IdentityFields.aviso` code — `estado_civil='casado'` rests ONLY on the
#: document being a certidão de casamento (`ROTULO_CASADO_POR_CERTIDAO`), yet
#: the marriage itself was not read: fewer than two cônjuges, no data de
#: casamento, no regime. Real (F80, prod 2026-10-24): a birth certificate
#: filed as `certidao_casamento` read ONE person and nothing of a marriage,
#: and still produced `casado`/`alta`. Demoted to `baixa`; a consumer must
#: treat it as a suggestion for review, never apply it unattended.
AVISO_ESTADO_CIVIL_NAO_CORROBORADO = "estado_civil_nao_corroborado"

#: `legibilidade.avaliar_legibilidade`'s `tipo_documento` FALLBACK when a
#: caller passes none — `classify_kind`'s classification IS already one of
#: these three strings for the cases it can tell apart at all (a filename
#: guess, never certidão/comprovante — see that function's own docstring).
#: `UNKNOWN` deliberately has no entry: `.get(...)` then returns `None`,
#: which `avaliar_legibilidade` reads as "unclassified" and scopes to its
#: safe, restricted default rather than guessing "card".
_TIPO_DOCUMENTO_POR_KIND = {
    IdentityDocumentKind.RG: "rg",
    IdentityDocumentKind.CPF: "cpf",
    IdentityDocumentKind.CNH: "cnh",
}

#: The vision prompt for rung 2, when the caller names none. Every field
#: parser in this module is LABEL-ANCHORED (`_candidatos`'s same-line
#: `LABEL: value` match) — so the transcription this prompt produces is
#: parser input, not a human-facing description, and MUST preserve the
#: document's own labels next to their values rather than paraphrase them
#: into prose.
#:
#: 🔴 WITHOUT THIS, THE CALLER INHERITED A PROMPT BUILT FOR SOMETHING ELSE.
#: `DocumentTextLadder(document_prompt=None)` used to fall through to
#: `media`'s generic `_DEFAULT_DOCUMENT_PROMPT` — "classify the type, then
#: extract and LIST all fields" — tuned for the resolver's OTHER callers
#: (a contract, a spreadsheet, a scene photo), where a type-first summary is
#: the right answer. Measured against org 2026-09 production uploads: a
#: certidão de casamento read through that generic prompt came back as
#: flowing narrative prose — the document's own `NOME`/`CPF` labels never
#: survived — and every label-anchored parser found nothing, even though
#: the SAME fact was present as a substring somewhere in a sentence.
#: `transcription.OCR_PROMPT` already solved this for the matrícula/
#: certidão-estrutura pipeline ("extract the exact text... without
#: corrections"); this is that same verbatim, anti-helpful posture, worded
#: for a field-dense identity document instead of a full registry page
#: (which is why it is its own constant rather than a straight re-export —
#: matrícula's prompt also asks for `**bold**`/`<u>underline</u>` markup
#: irrelevant here).
#:
#: 🔴 A PROMPT CHANGE ALONE DID NOT RECOVER EVERY MEASURED FAILURE — an
#: official "CNH Digital" (Detran/Serpro) PDF still returned no
#: `nome`/`cpf` under this prompt at the resolver's default render DPI (the
#: card's data sits in a small embedded image on a page dominated by a
#: legal disclaimer). A higher render DPI recovered it in the same
#: measurement, and a NAIVE global DPI bump 413'd a 2-page document against
#: the Anthropic vision endpoint in the same pass.
#:
#: RESOLVED 2026-09-23 (was NOC-REMEDIATE[identity-vision-render-dpi]): the
#: `_ladder` below now threads `identity_document_render_dpi_policy()`
#: through `DocumentTextLadder` -> `get_media_resolver` ->
#: `RealMediaResolver` -> its `LadderDocumentTranscriber` — page-count-aware
#: (a 1-page document affords 400 DPI, a longer one steps back down to the
#: seed-wide canonical 200) AND byte-budget-aware (stepped down further,
#: per page, whenever the base64-encoded render would exceed Anthropic's
#: documented per-image ceiling — see
#: `transcription.identity_document_render_dpi_policy` for the full
#: reasoning and `llm.providers.anthropic_provider.MAX_IMAGE_BYTES` for the
#: measured limit).
_IDENTITY_DOCUMENT_PROMPT = (
    "Transcreva o texto deste documento de identidade (RG, CNH, CIN, "
    "certidão, comprovante) exatamente como aparece, sem corrigir, "
    "resumir, parafrasear ou omitir nenhum campo legível. Preserve cada "
    "rótulo impresso seguido do respectivo valor na MESMA linha, no "
    "formato 'RÓTULO: valor' — um campo por linha, na ordem em que "
    "aparecem no documento. Se um valor estiver ilegível, escreva o "
    "rótulo seguido de '(ilegível)' e continue com o restante. Não "
    "recuse e não descreva a aparência do documento — apenas transcreva "
    "o texto."
)


async def _ler(ladder, content, mimetype, filename, **kwargs) -> LeituraTexto:
    """`ladder.ler(...)` — the text plus its `avisos`. A `DocumentTextLadder`
    always has `ler`; an injected test double written against the older
    `to_text`-only shape is read through `to_text`, with no avisos (it has
    none to report)."""
    ler = getattr(ladder, "ler", None)
    if ler is not None:
        return await ler(content, mimetype, filename, **kwargs)
    text, source, err = await ladder.to_text(content, mimetype, filename, **kwargs)
    return LeituraTexto(text, source, err)


def _marcar_avisos_leitura(fields: IdentityFields, leitura: LeituraTexto) -> IdentityFields:
    """Carry the transcription's own `avisos` onto the read — today only
    `resolucao_reduzida` (`releitura.marcar_resolucao_reduzida`)."""
    from noctusai_lib.integrations.documents.vision_tiling import AVISO_RESOLUCAO_REDUZIDA

    if AVISO_RESOLUCAO_REDUZIDA in leitura.avisos:
        return releitura.marcar_resolucao_reduzida(fields)
    return fields


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
        ladder: Optional[DocumentTextLadder] = None,
        escalar_releitura: bool = False,
        escalation_ladder: Optional[DocumentTextLadder] = None,
        modo_medicao: bool = False,
    ) -> None:
        # `ladder` is a DI seam for tests that must drive BOTH rungs (the
        # text-layer-then-vision fallthrough) without a real PDF or model.
        # Every real caller omits it.
        #
        # `render_dpi_policy=identity_document_render_dpi_policy()` is the
        # fix this class needed (was
        # NOC-REMEDIATE[identity-vision-render-dpi] — see the prompt's own
        # comment above): the identity rung opts INTO the page-count +
        # byte-budget-aware render DPI by construction, no caller-side
        # change required. A test supplying its own `ladder=` bypasses this
        # entirely, same as every other identity-rung default.
        self._ladder = ladder or DocumentTextLadder(
            org_id=org_id,
            document_prompt=document_prompt or _IDENTITY_DOCUMENT_PROMPT,
            resolver=resolver,
            max_pages=max_pages,
            provider=provider,
            render_dpi_policy=identity_document_render_dpi_policy(),
        )
        # 🔴 RENDER POLICY BY DOCUMENT CLASS (2026-10-13,
        # `transcription.render_dpi_policy_for`): `self._ladder` above is the
        # CARD ladder (one native image per page); a declared full-page type
        # (a certidão, a comprovante) reads through a second ladder whose
        # policy bands a dense page at the model's native resolution — built
        # lazily, only when such a type is read. An injected `ladder=` (a
        # test) answers for every class, same as every other DI default.
        #
        # 🔴 AND BY ROUTED MODEL (owner direction 2026-10-13, `documents.
        # roteamento`): every other ladder is keyed by (model, full-page?) —
        # the routed primary or fallback model × the card/page render policy
        # — and built lazily by `_ladder_para`. `self._ladder` stays the card
        # ladder of the provider's default model (the routing table's global
        # default for Anthropic).
        self._ladder_injetada = ladder is not None
        self._resolver = resolver
        self._ladders: dict[tuple[str, bool], DocumentTextLadder] = {}
        # 🔴 MEASUREMENT MODE (owner direction 2026-10-13): the always-two-
        # reads agreement gate (`releitura.deve_escalar` + `mesclar` + a third
        # read) is for evaluation harnesses ONLY. Production (`False`) reads
        # once with the routed primary model and pays for ONE fallback read
        # only when the trust gate (`confianca`) finds a critical field
        # doubtful.
        self._modo_medicao = modo_medicao
        # Remembered so `_get_escalation_ladder` (built lazily, only when a
        # read actually triggers `releitura.deve_escalar`) can construct a
        # SECOND ladder on the same org/prompt/page-cap/vendor, differing
        # only in which model reads the vision rung.
        self._org_id = org_id
        self._document_prompt = document_prompt
        self._max_pages = max_pages
        self._provider = provider
        # 🔴 `False` HERE, `True` AT THE FACTORY — same Fake-by-default
        # posture every seed IO module takes (`factory.py`'s own module
        # docstring): a raw `LadderIdentityExtractor(...)` — every test in
        # this package constructs one directly — must never pay for a
        # surprise SECOND vision call it did not ask for. The owner
        # decision ("on by default for the identity family") is a
        # PRODUCTION policy, enforced at `make_identity_extractor`'s own
        # `escalar_releitura=True` default, which explicitly forwards it
        # here — see that factory's own docstring for the consume seam
        # (and its per-org off switch).
        self._escalar_releitura = escalar_releitura
        # `escalation_ladder` mirrors `ladder` above — a DI seam for a test
        # that must drive the SECOND (escalated) rung deterministically.
        # Every real caller omits it; built lazily, pinned to
        # `providers.ESCALATION_OCR_MODELS`, on first use.
        self._escalation_ladder_override = escalation_ladder
        # `ESCALATION_OCR_MODELS` and `OCR_MODELS` share the SAME key set
        # (every `documents.providers.DOCUMENT_PROVIDERS` vendor) — an
        # unrecognised `provider` string falls back to the seed-canonical
        # provider's escalation pin, the same safe-restricted-default
        # posture `legibilidade._classe_documento` uses for an
        # unclassifiable `tipo_documento`.
        self._escalation_model = ESCALATION_OCR_MODELS.get(
            provider or DEFAULT_DOCUMENT_PROVIDER, OCR_MODELS[DEFAULT_DOCUMENT_PROVIDER]
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
        titular: Optional[TitularEsperado] = None,
        tipo_documento: Optional[str] = None,
        confirmados: Optional[Mapping[str, Any]] = None,
    ) -> IdentityFields:
        """`confirmados` (optional): critical field -> the value already
        CONFIRMED on the cliente from ANOTHER document type — the trust gate's
        cross-document corroboration (`confianca.avaliar`)."""
        kind = classify_kind(mimetype, filename)
        primario, fallback = self._modelos(tipo_documento)
        custos: list[CustoLeitura] = []
        if not content:
            return IdentityFields(
                kind=kind,
                error="empty_document",
                error_message="no bytes to read",
            )

        ladder = self._ladder_para(tipo_documento, primario)
        with coletar_uso() as uso:
            leitura = await _ler(ladder, content, mimetype, filename)
        custos.append(_custo(primario, "primaria", uso))
        text, source, err = leitura.text, leitura.source, leitura.error
        if err is not None:
            return IdentityFields(kind=kind, source=source, error=err[0], error_message=err[1])
        if not text.strip():
            # Legible pipeline, nothing readable in it. Not an error —
            # a caller must be able to tell this apart from a crash,
            # because retrying it is pointless.
            return IdentityFields(kind=kind, source=source)

        # 🔴 THE DOCUMENT'S OWN KIND, NOT THE OPERATOR'S (F80, 2026-10-24).
        # A certidão de NASCIMENTO filed as `certidao_casamento` must be read
        # as what it is: the casamento rules infer `casado` from the kind
        # itself. Every downstream step (field authority, core-field
        # contract, trust gate) runs on the kind the content names; the DB
        # row's `tipo_documento` is still never touched here — the aviso
        # tells the operator to re-file it.
        tipo_declarado = tipo_documento
        tipo_lido = tipo_civil_divergente(tipo_documento, text)
        if tipo_lido is not None:
            tipo_documento = tipo_lido

        fields = _marcar_avisos_leitura(
            self._ler(text, source, kind, titular, tipo_documento), leitura
        )
        if source is TextSource.TEXT_LAYER and (
            not _achou_algo(fields)
            or releitura.campos_nucleo_faltando(fields, tipo_documento)
        ):
            # 🔴 A TEXT LAYER THAT YIELDS NOTHING FALLS THROUGH TO VISION.
            # `classify_pdf_text_layer` judges whether a text layer is
            # SUBSTANTIVE, not whether it holds the fields THIS extractor
            # reads — and it cannot, it is field-agnostic by design. Live,
            # 2026-09-22: three genuine RG PDFs carried a real, selectable text
            # layer (issuer header, QR payload, signature block) with none of
            # the identity fields in it, and ended `sem_dados` with
            # `fonte=texto` — a legible document reported as empty, never
            # retried, because "nothing found" is not an error. Only a vision
            # pass over the rendered page can read what the text layer
            # omitted, so this extractor — the one layer that knows what
            # "nothing found" means here — asks the ladder again, skipping
            # rung 1.
            #
            # 🔴 "FOUND SOMETHING" IS NOT "FOUND ENOUGH" (live prod,
            # 2026-09-30, comp2-rg-51). `_achou_algo` alone missed the
            # narrower case: a phone-screenshot-shaped PDF whose text layer
            # was genuinely substantive — real, selectable characters, well
            # past `classify_pdf_text_layer`'s char floor — and carried the
            # holder's NOME in the surrounding app chrome, so `_achou_algo`
            # (any of nome/cpf/rg/endereco/conjuges/estado_civil) returned
            # True and stopped right there. The document's own identity
            # data (CPF, RG, órgão) sat in an embedded IMAGE the text layer
            # never touches. When the caller has DECLARED a `tipo_documento`
            # with a known core-field contract (`releitura._TABELA_NUCLEO` —
            # the same table `deve_escalar` already reads), a text layer
            # missing any of THOSE fields gets the same second chance a
            # truly-empty one already got, whether or not it found nome.
            with coletar_uso() as uso:
                leitura = await _ler(
                    ladder, content, mimetype, filename, pular_camada_texto=True
                )
            custos.append(_custo(primario, "primaria", uso))
            texto_ocr, fonte_ocr, err_ocr = leitura.text, leitura.source, leitura.error
            if err_ocr is not None:
                # The text layer had nothing and vision could not run: that
                # is a failure to read, not an empty document — report it so
                # the consumer's bounded retry can try again.
                return IdentityFields(
                    kind=kind, source=fonte_ocr, error=err_ocr[0], error_message=err_ocr[1]
                )
            if texto_ocr.strip():
                fields = _marcar_avisos_leitura(
                    self._ler(texto_ocr, fonte_ocr, kind, titular, tipo_documento),
                    leitura,
                )

        # 🔴 ROUTED READ + TRUST GATE (owner direction 2026-10-13). Runs AFTER
        # the text-layer→vision fallthrough above so it always judges the
        # BEST first read this extractor already produced. A text layer is
        # exact (not model-dependent): no gate, no fallback.
        if fields.source is TextSource.OCR:
            fields = await self._conciliar(
                fields, content, mimetype, filename, titular, tipo_documento,
                primario=primario, fallback=fallback, confirmados=confirmados,
                custos=custos,
            )

        # 🔴 THE SILENT-PARTIAL GUARD (live prod, 2026-09-30) — checked LAST,
        # after every rung and every re-read this call is ever going to try.
        # `releitura.deve_escalar` already fires on exactly this condition
        # for an OCR-sourced read and tries a stronger model; what neither
        # `deve_escalar` nor `mesclar` ever did is say anything when that
        # escalation (or a TEXT_LAYER read the type-aware check above just
        # widened) STILL leaves a core field blank — `mesclar`'s own
        # "nothing changed" branch is the right merge decision (there is
        # truly nothing new to report) but is not the right SILENCE: three
        # real `tipo_documento="rg"` uploads persisted `extracao_fonte=ocr`,
        # `data_nascimento_confianca=alta`, and CPF/RG/órgão/gênero/
        # nacionalidade/filiação all NULL, with no code on the row saying
        # the document's own type expected more than that. This never
        # blocks persistence of what WAS found (unlike `leitura_
        # comprometida`) — a real birthdate stays a real birthdate — it
        # only names, in `aviso`, what the checklist should ask a human to
        # get a better copy of.
        faltando = releitura.campos_nucleo_faltando(fields, tipo_documento)
        if faltando:
            fields = releitura.marcar_campos_ausentes(
                fields, faltando, tipo_documento=tipo_documento
            )
        if tipo_lido is not None:
            fields = replace(
                fields,
                aviso=releitura._somar_codigo(fields.aviso, AVISO_TIPO_DOCUMENTO_DIVERGENTE),
                aviso_mensagem=releitura._somar_mensagem(
                    fields.aviso_mensagem,
                    mensagem_tipo_divergente(str(tipo_declarado), tipo_lido),
                ),
            )
        return fields

    async def _escalar(
        self,
        original: IdentityFields,
        content: bytes,
        mimetype: Optional[str],
        filename: Optional[str],
        titular: Optional[TitularEsperado],
        tipo_documento: Optional[str],
        custos: Optional[list[CustoLeitura]] = None,
    ) -> IdentityFields:
        """MEASUREMENT MODE ONLY (`modo_medicao=True`).

        One more transcription of the SAME pages with a stronger model
        (`providers.ESCALATION_OCR_MODELS`), merged via `releitura.mesclar`.

        `pular_camada_texto=True`: `releitura.deve_escalar` already gated on
        `original.source is TextSource.OCR`, so there is no text layer worth
        retrying — going straight to vision reuses the SAME rung (and the
        SAME page-by-page transcriber) the first read already paid for, per
        page, never batched.
        """
        async def _reler() -> Optional[IdentityFields]:
            with coletar_uso() as uso:
                leitura = await _ler(
                    self._get_escalation_ladder(tipo_documento),
                    content, mimetype, filename, pular_camada_texto=True,
                )
            if custos is not None:
                custos.append(_custo(self._escalation_model, "medicao", uso))
            texto, fonte, erro = leitura.text, leitura.source, leitura.error
            if erro is not None:
                logger.warning(
                    "releitura: escalation transcription failed for org=%s: %s",
                    self._org_id, erro,
                )
                return None
            if not texto.strip():
                return None
            return _marcar_avisos_leitura(
                self._ler(texto, fonte, original.kind, titular, tipo_documento),
                leitura,
            )

        escalada = await _reler()
        if escalada is None:
            # The re-read could not run: the first read stands ALONE, so only
            # a check-digit-verified critical value may be emitted.
            return releitura.sem_corroboracao(original)
        extras: tuple[IdentityFields, ...] = ()
        if not (releitura.leitura_valida(original) and releitura.leitura_valida(escalada)):
            # Fewer than two reads may count (compromised / failed anchor):
            # one more independent escalated read, so two valid ones can
            # still agree. Bounded: never more than three transcriptions.
            terceira = await _reler()
            if terceira is not None:
                extras = (terceira,)
        resultado = releitura.mesclar(
            original, escalada, escalation_model=self._escalation_model, extras=extras
        )
        if not extras and resultado.divergencias:
            # The cheap read is often too weak to corroborate anything (it
            # returned NO field on 4/5 real documents), so a field left
            # unsettled gets ONE more escalated read: two escalated reads can
            # agree where cheap+escalated cannot. Still bounded at three
            # transcriptions, and still no winner — a 2-of-3 AGREEMENT or
            # nothing.
            terceira = await _reler()
            if terceira is not None:
                resultado = releitura.mesclar(
                    original, escalada, escalation_model=self._escalation_model,
                    extras=(terceira,),
                )
        return resultado

    def _modelos(self, tipo_documento: Optional[str]) -> tuple[str, str]:
        """(primary, fallback) for this read: the routing table for the
        seed-canonical vendor, the per-provider pins otherwise."""
        if roteamento.roteia(self._provider):
            r = roteamento.rota(tipo_documento)
            return r.primario, r.fallback
        return (
            OCR_MODELS.get(self._provider, OCR_MODELS[DEFAULT_DOCUMENT_PROVIDER]),
            self._escalation_model,
        )

    def _ladder_para(
        self, tipo_documento: Optional[str], modelo: Optional[str] = None
    ) -> DocumentTextLadder:
        """The ladder for (routed model × document CLASS): the card policy
        (one native image per page) unless the declared type reads as a full
        page (banded, `transcription.render_dpi_policy_for`). `modelo=None`
        is the routed primary for the type. An injected `ladder=` (a test)
        answers for every model and class."""
        if self._ladder_injetada:
            return self._ladder
        if modelo is None:
            modelo = self._modelos(tipo_documento)[0]
        politica = render_dpi_policy_for(tipo_documento)
        pagina = politica.max_bands > 1
        padrao = OCR_MODELS.get(self._provider or DEFAULT_DOCUMENT_PROVIDER)
        if not pagina and modelo == padrao:
            return self._ladder
        chave = (modelo, pagina)
        if chave not in self._ladders:
            self._ladders[chave] = DocumentTextLadder(
                org_id=self._org_id,
                document_prompt=self._document_prompt or _IDENTITY_DOCUMENT_PROMPT,
                resolver=self._resolver,
                max_pages=self._max_pages,
                provider=self._provider,
                render_dpi_policy=politica if pagina else identity_document_render_dpi_policy(),
                ocr_model=modelo,
            )
        return self._ladders[chave]

    def _get_escalation_ladder(self, tipo_documento: Optional[str] = None) -> DocumentTextLadder:
        """MEASUREMENT MODE's escalated-model ladder, with the SAME class
        policy the first read used (a certidão escalates with bands too)."""
        if self._escalation_ladder_override is not None:
            return self._escalation_ladder_override
        return self._ladder_para(tipo_documento, self._escalation_model)

    async def _conciliar(
        self,
        fields: IdentityFields,
        content: bytes,
        mimetype: Optional[str],
        filename: Optional[str],
        titular: Optional[TitularEsperado],
        tipo_documento: Optional[str],
        *,
        primario: str,
        fallback: str,
        confirmados: Optional[Mapping[str, Any]],
        custos: list[CustoLeitura],
    ) -> IdentityFields:
        """The production path: trust gate over the primary read, ONE
        fallback read only for a doubtful critical field, reconcile just
        those fields (`releitura.conciliar`). Measurement mode and the per-org
        off switch branch off here."""
        vereditos = confianca.avaliar(
            fields, tipo_documento, modelo=primario, confirmados=confirmados
        )
        if self._modo_medicao:
            modo = "medicao"
            resultado = fields
            if self._escalar_releitura and releitura.deve_escalar(fields, tipo_documento):
                resultado = await self._escalar(
                    fields, content, mimetype, filename, titular, tipo_documento, custos
                )
            return replace(resultado, roteamento=_resumo(
                tipo_documento, primario, self._escalation_model, modo, vereditos,
                (), fields, None, resultado, custos,
            ))
        # 🔴 CONFIDENCE CALIBRATION (`confianca.calibrar`, 2026-10-19): a
        # vision-capped `baixa` (nome/rg/rne) the gate just cleared ON
        # EVIDENCE (check digit, another document, measured precision) is
        # stored as `media` — the review panel stops flagging correct reads,
        # while an unevidenced or doubtful one keeps its `baixa`. The
        # verdicts themselves (the learning-loop record) are unchanged.
        if not self._escalar_releitura:
            # Per-org OFF SWITCH: the single read, as before — verdicts are
            # recorded (learning loop) but nothing is reconciled.
            calibrado = confianca.calibrar(fields, vereditos)
            return replace(calibrado, roteamento=_resumo(
                tipo_documento, primario, None, "leitura_unica", vereditos,
                (), fields, None, calibrado, custos,
            ))
        duvidosos = confianca.criticos_duvidosos(vereditos, fields, tipo_documento)
        if not duvidosos:
            calibrado = confianca.calibrar(fields, vereditos)
            return replace(calibrado, roteamento=_resumo(
                tipo_documento, primario, fallback, "producao", vereditos,
                (), fields, None, calibrado, custos,
            ))
        lida = await self._ler_fallback(
            fallback, content, mimetype, filename, fields.kind, titular, tipo_documento, custos
        )
        substitutos: tuple[str, ...] = ()
        if lida is not None and not releitura.leitura_valida(fields) and releitura.leitura_valida(lida):
            # The primary read is out as a whole: the fallback read stands in
            # for the fields IT passes the gate on, with a MEASURED precision
            # (an unmeasured cell is no stand-in) — `releitura.conciliar`.
            vf = confianca.avaliar(lida, tipo_documento, modelo=fallback, confirmados=confirmados)
            substitutos = tuple(
                c for c, v in vf.items()
                if c in confianca.campos_criticos() and v.estado == confianca.CONFIAVEL
                and "precisao_nao_medida" not in v.motivos
            )
        resultado = releitura.conciliar(
            fields, lida, duvidosos=duvidosos, modelo_fallback=fallback,
            substitutos=substitutos,
        )
        # Only the fields the PRIMARY verdict still describes: a reconciled
        # (`duvidosos`) or substituted field's confidence is `conciliar`'s.
        resultado = confianca.calibrar(
            resultado, vereditos, excluir=tuple({*duvidosos, *substitutos}),
            original=fields,
        )
        return replace(resultado, roteamento=_resumo(
            tipo_documento, primario, fallback, "producao", vereditos,
            duvidosos, fields, lida, resultado, custos, fallback_executado=True,
        ))

    async def _ler_fallback(
        self,
        modelo: str,
        content: bytes,
        mimetype: Optional[str],
        filename: Optional[str],
        kind,
        titular: Optional[TitularEsperado],
        tipo_documento: Optional[str],
        custos: list[CustoLeitura],
    ) -> Optional[IdentityFields]:
        """ONE fallback-model read of the same pages (vision rung only — the
        primary read already established there is no usable text layer).
        `None` (logged) when the call fails or reads nothing."""
        ladder = (
            self._escalation_ladder_override
            if self._escalation_ladder_override is not None
            else self._ladder_para(tipo_documento, modelo)
        )
        with coletar_uso() as uso:
            leitura = await _ler(ladder, content, mimetype, filename, pular_camada_texto=True)
        custos.append(_custo(modelo, "fallback", uso))
        texto, fonte, erro = leitura.text, leitura.source, leitura.error
        if erro is not None:
            logger.warning(
                "roteamento: fallback read with %s failed for org=%s: %s",
                modelo, self._org_id, erro,
            )
            return None
        if not texto.strip():
            logger.warning(
                "roteamento: fallback read with %s returned no text for org=%s",
                modelo, self._org_id,
            )
            return None
        return _marcar_avisos_leitura(
            self._ler(texto, fonte, kind, titular, tipo_documento), leitura
        )

    def _ler(
        self,
        text: str,
        source: TextSource,
        kind,
        titular: Optional[TitularEsperado],
        tipo_documento: Optional[str] = None,
    ) -> IdentityFields:
        """Pure half: text + the rung that produced it -> typed fields.

        🔴 FIELD AUTHORITY (owner rule 2026-10-13, `autoridade.py`): when the
        caller declared a `tipo_documento` the authority table knows, a
        finder for a field that type is NOT the authoritative source for
        never runs, and the field is never emitted. An undeclared/unlisted
        type keeps the historical type-agnostic read.
        """
        autorizados = autoridade.campos_autorizados(tipo_documento)
        tipo_norm = autoridade.tipo_normalizado(tipo_documento)

        def pode(campo: str) -> bool:
            return autorizados is None or campo in autorizados

        def global_(campo: str) -> bool:
            # May a WHOLE-DOCUMENT finder run for `campo`? Not for a field the
            # type only emits attributed to one person (a certidão de casamento
            # names two spouses: `autoridade.SO_POR_CONJUGE`).
            return pode(campo) and not autoridade.so_por_conjuge(campo, tipo_norm)

        def explicito(campo: str) -> bool:
            # Readers that only make sense on a DECLARED type (a document
            # number with a type-specific label) never run type-agnostic.
            return autorizados is not None and campo in autorizados

        nada3: tuple = (None, "nenhuma", None)
        data, data_conf, data_label = find_birthdate(text) if pode("data_nascimento") else nada3
        nome, nome_conf, nome_label = find_name(text) if pode("nome") else nada3
        nome_conf = self._temper_name_confidence(nome_conf, source)
        # Gender is NOT tempered by source, unlike the name. Its alphabet has
        # two elements and its parser refuses every unlabelled single letter,
        # so an OCR pass cannot turn "Masculino" into a different VALID value —
        # it can only turn it into nothing. The name's risk is a plausible
        # misreading; this field has no plausible misreadings to make.
        #
        # 🔴 GENDER IS A PRINTED FIELD ONLY (owner rule 2026-10-13): read off
        # a `SEXO` label (`find_gender` is label-anchored) on a type that
        # prints one. A certidão de casamento prints none — its only gender
        # is the DERIVED one attached below (`genero_derivado=True`).
        genero_derivado = False
        if pode("genero") and tipo_norm not in autoridade.GENERO_SO_DERIVADO:
            genero, genero_conf, genero_label = find_gender(text)
        else:
            genero, genero_conf, genero_label = nada3

        # CPF is NOT tempered by source either, and for a reason the other
        # fields cannot claim: it verifies its own two check digits. An OCR
        # digit confusion (0/O, 5/S, 8/B) breaks the mod-11 arithmetic, so a
        # vision pass that misreads a CPF produces a value the parser has
        # already demoted to `baixa` on its own. Tempering here would demote
        # the reads that survived that gate — which are precisely the ones
        # worth trusting.
        cpf, cpf_conf, cpf_label = find_cpf(text) if global_("cpf") else nada3

        # The RG has NO check digit anywhere in Brazil, so it gets the name's
        # treatment: a vision-read RG is a suggestion. It has no structural
        # self-evidence to fall back on, which makes it the weakest of the
        # five — see `rg.py`.
        rg, rg_conf, rg_label = find_rg(text) if global_("rg") else nada3
        rg_conf = self._temper_name_confidence(rg_conf, source)
        if global_("rg"):
            rg_orgao, rg_orgao_conf = find_rg_orgao(text, rg)
        else:
            rg_orgao, rg_orgao_conf = None, ExtractionConfidence.NENHUMA.value
        rg_orgao_conf = self._temper_name_confidence(rg_orgao_conf, source)
        identidade_tipo: Optional[str] = None
        # 🔴 RNE IS ITS OWN KIND (owner rule 2026-10-13). A foreign national's
        # RNE/RNM/CRNM — on its own card, in a CNH "DOC. IDENTIDADE" box, or
        # under a field merely labelled "RG" (`RG: W-573.678-Z · Órgão
        # expedidor: DIREX`) — is emitted as `rne` exactly as printed, with
        # its federal issuer in `rne_orgao`, and NEVER in `rg`.
        rne: Optional[str] = None
        rne_conf: str = ExtractionConfidence.NENHUMA.value
        rne_label: Optional[str] = None
        rne_orgao: Optional[str] = None
        if pode("rne"):
            rne, rne_conf, rne_label, rne_orgao, identidade_tipo = find_rne(text)
            rne_conf = self._temper_name_confidence(rne_conf, source)
        # The CNH's 4c box, read as ONE unit: number + issuer + UF together
        # (a CNH RG used to come out without its issuer/UF).
        caixa = find_caixa_identidade_cnh(text) if (global_("rg") or pode("rne")) else None
        if caixa is not None:
            tipo_caixa, numero_caixa, org_caixa, uf_caixa = caixa
            if tipo_caixa == "rne" and pode("rne") and rne is None:
                rne, rne_label, rne_orgao = numero_caixa, "DOC. IDENTIDADE (CNH)", org_caixa
                rne_conf = self._temper_name_confidence("alta", source)
            elif tipo_caixa == "rg" and global_("rg"):
                if rg is None or only_alnum(rg) == only_alnum(numero_caixa):
                    rg = numero_caixa
                    rg_label = "DOC. IDENTIDADE / ORG. EMISSOR / UF"
                    rg_conf = self._temper_name_confidence("alta", source)
                if org_caixa and uf_caixa and only_alnum(rg or "") == only_alnum(numero_caixa):
                    rg_orgao = f"{org_caixa}/{uf_caixa}"
                    rg_orgao_conf = self._temper_name_confidence("alta", source)
        # 🔴 WHAT `rg` MAY NEVER HOLD (owner rule 2026-10-13, measured on a
        # real RNE holder's CNH: `rg='12346581446'`, a form number printed
        # at the card's foot). Dropped values are kept visible in
        # `leituras_alternativas` + an aviso — never silently.
        rg_descartado: Optional[tuple[str, str]] = None
        if rne is not None:
            # The identity box holds ONE document: with an RNE read, any `rg`
            # is either the same number or a stray run — never an RG.
            if rg is not None:
                rg_descartado = (rg, "o documento de identidade é um RNE")
                rg, rg_conf, rg_label = None, ExtractionConfidence.NENHUMA.value, None
            identidade_tipo = identidade_tipo or "rne"
        else:
            identidade_tipo = None
        if rg is not None and re.fullmatch(r"\d{11}", re.sub(r"[.\-\s/]", "", rg)):
            # Eleven digits is a CPF or a CNH Nº REGISTRO shape, never an RG
            # (no Brazilian RG body runs to 11 digits). Refused whether or
            # not its check digits verify as one of those.
            digitos = re.sub(r"\D", "", rg)
            if _ident.cpf_dv_valido(digitos):
                motivo_rg = "11 dígitos com DV de CPF"
            elif _ident.validar_cnh_registro(digitos).valido:
                motivo_rg = "11 dígitos com DV de registro de CNH"
            else:
                motivo_rg = "11 dígitos não é forma de RG"
            rg_descartado = (rg, motivo_rg)
            rg, rg_conf, rg_label = None, ExtractionConfidence.NENHUMA.value, None
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

        registro_cnh, registro_cnh_conf, _ = (
            find_registro_cnh(text) if explicito("registro_cnh") else nada3
        )

        # Estado civil / regime de bens are NOT tempered by source, for the
        # same reason `genero` is not: both parsers require an explicit
        # label, an AVERBAÇÃO event keyword, or the regime-de-bens phrase
        # itself (structural evidence, like the CPF check digit) — none of
        # which an OCR misread can turn into a DIFFERENT valid vocabulary
        # token. It can only turn a real reading into nothing.
        estado_civil, estado_civil_conf, estado_civil_label = (
            (
                find_estado_civil_certidao_casamento(text)
                if tipo_norm == "CERTIDAO_CASAMENTO"
                else find_estado_civil(text)
            )
            if pode("estado_civil")
            else nada3
        )
        regime_bens, regime_bens_conf, regime_bens_label = (
            find_regime_bens(text) if pode("regime_bens") else nada3
        )

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
            find_data_casamento(text) if pode("data_casamento") else nada3
        )
        data_emissao, data_emissao_conf, data_emissao_label = (
            find_data_emissao(text) if pode("data_emissao") else nada3
        )

        # `nacionalidade` is NOT tempered by source, for the same reason
        # `genero` and `estado_civil` are not: the parser requires an
        # explicit `NACIONALIDADE` label AND canonicalises every reading
        # before comparing, so an OCR misread can only turn a real reading
        # into nothing (or into a genuine disagreement, already `nenhuma`)
        # — never into a DIFFERENT valid vocabulary token. See
        # `nacionalidade.py` for why two spouses' readings are compared
        # AFTER canonicalising across grammatical gender, and for
        # `NOC-REMEDIATE[nacionalidade-titular-hint]` — the one case this
        # leaves unresolved: a genuinely binational couple's certidão,
        # which reports `nenhuma` here with no `titular`-hint tie-break.
        nacionalidade, nacionalidade_conf, nacionalidade_label = (
            find_nacionalidade(text) if pode("nacionalidade") else nada3
        )

        # 🔴 TWO TITULARES: SELECT WITH THE CALLER'S HINT, ELSE A NOTICE
        # -------------------------------------------------------------------
        # A certidão de casamento names TWO people with equal prominence
        # (`NOMES`, both spouses' CPFs), and `nome`/`cpf` above are each
        # single columns — `find_name`/`find_cpf` correctly decline to guess
        # which spouse belongs there. `find_name_conflitos`/
        # `find_cpf_conflitos` name the candidates.
        #
        # The caller usually KNOWS whose card the document was uploaded to,
        # and passes that person as `titular`. The hint only SELECTS among
        # values the document itself printed — see `_selecionar_titular`.
        # (Was NOC-REMEDIATE[identity-extractor-disambiguation-hint].)
        #
        # Whatever the hint cannot resolve is reported as an `aviso`, NOT as
        # `error`: the couple-level readings on this same result (estado
        # civil, regime, datas) are valid whoever the holder is, and an
        # `error` makes every consumer discard them.
        multiplos_titulares: list[str] = []
        if nome is None and pode("nome"):
            conflito_nome = find_name_conflitos(text)
            if conflito_nome:
                escolhido = _selecionar_nome(conflito_nome, titular)
                if escolhido is not None:
                    # The name's own policy still applies: a vision-read name
                    # is a suggestion. The hint chose WHICH printed name, it
                    # did not make the transcription exact.
                    nome = escolhido
                    nome_conf = self._temper_name_confidence("alta", source)
                    nome_label = "NOMES (titular do card)"
                else:
                    multiplos_titulares.append(f"nome ({len(conflito_nome)} titulares)")
        if cpf is None and pode("cpf"):
            conflito_cpf = find_cpf_conflitos(text)
            if conflito_cpf:
                escolhido_cpf = _selecionar_cpf(conflito_cpf, titular)
                if escolhido_cpf is not None:
                    # Not tempered, same as every CPF here: both candidates
                    # already passed the check-digit gate to be in the list.
                    cpf = escolhido_cpf
                    cpf_conf = "alta"
                    cpf_label = "CPF (titular do card)"
                else:
                    multiplos_titulares.append(f"cpf ({len(conflito_cpf)} titulares)")

        # Profissão — label-anchored only, NOT tempered by source for the
        # same reason `nacionalidade` is not: it needs an explicit label, so a
        # misread can only lose it or make two readings disagree (`nenhuma`).
        profissao, profissao_conf, profissao_label = (
            find_profissao(text) if pode("profissao") else nada3
        )
        # A labelled profissão the vocabulary refused ("aposentanda") is NOT
        # emitted (`profession.avaliar_profissao`) — but it is not dropped
        # silently either: named in an aviso, nearest form as a suggestion.
        profissao_invalida = (
            find_profissao_invalida(text) if pode("profissao") and profissao is None else None
        )

        # Filiação / naturalidade — anchored (`filiacao.py`), tempered like a
        # name: a vision-read parent's name is a suggestion. A certidão de
        # casamento's come ONLY from the titular spouse's own clause below.
        nome_pai, nome_pai_conf = None, ExtractionConfidence.NENHUMA.value
        nome_mae, nome_mae_conf = None, ExtractionConfidence.NENHUMA.value
        filiacao_label: Optional[str] = None
        if global_("nome_mae") or global_("nome_pai"):
            nome_pai, nome_pai_conf, nome_mae, nome_mae_conf, filiacao_label = (
                find_filiacao(text)
            )
            if not global_("nome_pai"):
                nome_pai, nome_pai_conf = None, ExtractionConfidence.NENHUMA.value
            if not global_("nome_mae"):
                nome_mae, nome_mae_conf = None, ExtractionConfidence.NENHUMA.value
            nome_pai_conf = self._temper_name_confidence(nome_pai_conf, source)
            nome_mae_conf = self._temper_name_confidence(nome_mae_conf, source)
        naturalidade, naturalidade_conf, naturalidade_label = (
            find_naturalidade(text) if global_("naturalidade") else nada3
        )
        naturalidade_conf = self._temper_name_confidence(naturalidade_conf, source)
        nome_pai_label = nome_mae_label = filiacao_label

        # Endereço — read on every document (the extractor is type-agnostic);
        # WHICH document types may promote it is the consumer's decision (a
        # certidão prints its CARTÓRIO's address, which is nobody's home).
        endereco = find_endereco(text) if pode("endereco") else None

        # Both spouses, when the document names two. The one the caller's
        # `titular` hint picked (by the name or CPF selected above) is marked,
        # and ITS per-person facts replace the whole-document readings, which
        # would otherwise mix the two spouses (two birthdates -> `nenhuma`,
        # or worse, the wrong one alone).
        #
        # `esperados` (P2 corpus, 2026-09-29) — the couple the CALLER already
        # knows (`titular.nome`/`titular.conjuge_nome`), passed through so
        # `conjuges.find_conjuges`'s anchored fallback can confirm a name
        # directly against the text when the label-driven readers above it
        # all decline (a vision transcription's own run-to-run variance
        # breaking the specific label/connector/block-opener they each
        # depend on). A caller with no hint gets `()` here, same as before.
        esperados = tuple(
            n for n in (
                titular.nome if titular else None,
                titular.conjuge_nome if titular else None,
            )
            if n
        )
        conjuges = find_conjuges(text, esperados=esperados) if pode("conjuges") else ()
        if conjuges:
            escolhido_idx = _conjuge_do_titular(conjuges, nome, cpf)
            if escolhido_idx is None and titular is not None and titular.nome:
                # The caller's own hinted name (exact, unique) — covers a
                # document whose whole-text `nome` read did not resolve.
                escolhido_idx = _conjuge_do_titular(conjuges, titular.nome, None)
            if escolhido_idx is not None:
                marcados = []
                for i, c in enumerate(conjuges):
                    marcados.append(replace(c, titular=(i == escolhido_idx)))
                conjuges = tuple(marcados)
                eu = conjuges[escolhido_idx]
                # 🔴 UNCONDITIONAL REPLACEMENT, EVEN TO ABSENT — real,
                # measured (P1/883, 2026-09-28): the comment above already
                # names the risk this closes ("or worse, the wrong one
                # alone") but the code used to only act on it when
                # `eu.data_nascimento` WAS found, silently keeping the
                # whole-document `data` above otherwise. That whole-document
                # read has no notion of WHICH of the two co-equal holders it
                # belongs to — on a tabular, one-field-per-row certidão
                # layout (read positionally by `conjuges._dados_tabulares`
                # only when each label occurs exactly twice; any other
                # count leaves it unattributed), it can land squarely on the OTHER spouse's
                # birthdate with a confident label, because THEIRS happened
                # to sit closer to a `NASCIMENTO` label than the titular's
                # own. Once a titular is resolved among two co-equal
                # holders, only THEIR segment-scoped reading may answer
                # `data_nascimento` — an unscoped document-wide guess is
                # exactly the ambiguity this field's own docstring says to
                # report as absent, never to guess.
                data, data_conf, data_label = (
                    eu.data_nascimento,
                    eu.data_nascimento_confianca if eu.data_nascimento is not None else "nenhuma",
                    "certidão (cônjuge titular)" if eu.data_nascimento is not None else None,
                )
                if eu.nacionalidade is not None and pode("nacionalidade"):
                    nacionalidade, nacionalidade_conf, nacionalidade_label = (
                        eu.nacionalidade, eu.nacionalidade_confianca, "certidão (cônjuge titular)"
                    )
                if eu.profissao is not None and pode("profissao"):
                    profissao, profissao_conf, profissao_label = (
                        eu.profissao, eu.profissao_confianca, "certidão (cônjuge titular)"
                    )
                if eu.genero is not None and genero is None and pode("genero"):
                    # DERIVED (grammatical agreement on THIS spouse's own
                    # clause) — flagged, never a reading.
                    genero, genero_conf, genero_label = (
                        eu.genero, eu.genero_confianca, "certidão (concordância — derivado)"
                    )
                    genero_derivado = True
                # 🔴 THE TITULAR'S OWN RG / FILIAÇÃO / NATURALIDADE (owner decision
                # 2026-10-21): from THEIR clause / cadastro annotation only —
                # `media` at most (attributed by position / name anchor).
                if eu.rg and pode("rg"):
                    rg, rg_conf, rg_label = (
                        eu.rg, eu.rg_confianca, "ANOTAÇÕES DE CADASTRO (cônjuge titular)"
                    )
                    rg_orgao = eu.rg_orgao
                    rg_orgao_conf = eu.rg_orgao_confianca if eu.rg_orgao else "nenhuma"
                for attr in ("nome_mae", "nome_pai", "naturalidade"):
                    valor_eu = getattr(eu, attr)
                    if valor_eu and pode(attr):
                        if attr == "nome_mae":
                            nome_mae, nome_mae_conf, nome_mae_label = (
                                valor_eu, eu.nome_mae_confianca, "certidão (cônjuge titular)"
                            )
                        elif attr == "nome_pai":
                            nome_pai, nome_pai_conf, nome_pai_label = (
                                valor_eu, eu.nome_pai_confianca, "certidão (cônjuge titular)"
                            )
                        else:
                            naturalidade, naturalidade_conf, naturalidade_label = (
                                valor_eu, eu.naturalidade_confianca, "certidão (cônjuge titular)"
                            )
                if cpf is None and eu.cpf and pode("cpf"):
                    cpf, cpf_conf, cpf_label = eu.cpf, eu.cpf_confianca, "CPF (titular do card)"
                    # The spouse pairing resolved what the bare CPF hint could
                    # not — it is no longer a withheld field.
                    multiplos_titulares = [
                        m for m in multiplos_titulares if not m.startswith("cpf ")
                    ]

        # 🔴 P1/883 (2026-09-25) — data_nascimento vs data_casamento
        # plausibility guard. Even a LABELLED read (see `conjuges.py`'s own
        # `find_birthdate` filter, above) is a transcription by a model over
        # a photographed/scanned document, and `birthdate.find_birthdate`'s
        # own sanity gate only checks a date against TODAY — it has no way
        # to know THIS document's other date. Real, measured: an image-only
        # phone-scan certidão's vision read put a birth year on the spouse
        # that would make them younger than 16 (CC art. 1.517's absolute
        # marriageable-age floor — mirrors `birthdate.MIN_AGE`) AT THE
        # MARRIAGE DATE PRINTED ON THE SAME DOCUMENT — a confusion between
        # two structurally plausible years neither `birthdate`'s own gate
        # nor a bare label match can catch alone, because both checks look
        # at only one of the two dates at a time. Comparing them against
        # EACH OTHER is the check that catches it.
        #
        # Rejected, not silently dropped: the reading is reported as an
        # `aviso`, same shape `titulares_multiplos` already uses, so a human
        # sees WHAT was withheld and why instead of a quietly empty column.
        #
        # 🔴 NOT IMPLEMENTED HERE, FLAGGED FOR THE OWNER (per the P1/883
        # brief): (a) the broader "<18 on any adult-only document" rule —
        # this extractor is type-agnostic and has no notion of which
        # document TYPES are adult-only, so generalising past the
        # marriage-specific CC art. 1.517 floor would be a guess, not a
        # measured fix; (b) source PRECEDENCE (a CNH/CIN's own
        # `data_nascimento` should outrank a certidão's when a consumer
        # holds both) — that is a cross-document decision the D1 merge path
        # in `products/social-wiring/.../identidade_extracao_service.py`
        # makes, not a single extraction result this function returns.
        matricula_certidao, matricula_conf, matricula_avisos = (
            find_matricula_certidao(
                text, tipo_documento=tipo_norm, data_emissao=data_emissao
            )
            if explicito("matricula_certidao")
            else (None, "nenhuma", ())
        )

        data_nascimento_rejeitada: Optional[date] = None
        if data is not None and data_casamento is not None:
            idade_no_casamento = data_casamento.year - data.year - (
                (data_casamento.month, data_casamento.day) < (data.month, data.day)
            )
            if idade_no_casamento < MIN_AGE:
                data_nascimento_rejeitada = data
                data, data_conf, data_label = None, "nenhuma", None

        # 🔴 "CASADO" BY KIND NEEDS THE MARRIAGE ITSELF READ (F80). The
        # casamento inference (`ROTULO_CASADO_POR_CERTIDAO`) rests on the
        # document BEING a certidão de casamento; with not even the couple
        # (two cônjuges), the date, or the regime read, nothing on the page
        # corroborates that — never `alta`, flagged for review.
        estado_civil_nao_corroborado = (
            estado_civil == "casado"
            and estado_civil_label == ROTULO_CASADO_POR_CERTIDAO
            and len(conjuges) < 2
            and data_casamento is None
            and regime_bens is None
        )
        if estado_civil_nao_corroborado:
            estado_civil_conf = ExtractionConfidence.BAIXA.value

        avisos: list[tuple[str, str]] = []
        if estado_civil_nao_corroborado:
            avisos.append((
                AVISO_ESTADO_CIVIL_NAO_CORROBORADO,
                "estado civil 'casado' deduzido apenas do tipo certidão de "
                "casamento, sem o casamento lido (cônjuges, data ou regime) — "
                "sugestão para conferência, não gravada automaticamente",
            ))
        if multiplos_titulares:
            avisos.append((
                "titulares_multiplos",
                "documento nomeia mais de um titular com igual proeminencia "
                "para: " + ", ".join(multiplos_titulares) + " — esses campos "
                "nao foram gravados; os demais (estado civil, regime, datas) sim",
            ))
        if rg_descartado is not None:
            avisos.append((
                "rg_descartado",
                f"valor lido como RG ('{rg_descartado[0]}') descartado: "
                f"{rg_descartado[1]} — mantido apenas como leitura alternativa",
            ))
        if profissao_invalida is not None:
            valor_inv, sugestao_inv = profissao_invalida
            avisos.append((
                VOCABULARIO_INVALIDO,
                f"profissao lida '{valor_inv}' nao consta do vocabulario — nao "
                "gravada" + (f"; sugestao: '{sugestao_inv}' (confirme)" if sugestao_inv else ""),
            ))
        for codigo_mat in matricula_avisos:
            avisos.append((
                codigo_mat,
                f"matricula da certidao: {codigo_mat.removeprefix('matricula_')}"
                + (" — leitura nao gravada" if matricula_certidao is None else " (aviso)"),
            ))
        if data_nascimento_rejeitada is not None:
            avisos.append((
                "data_nascimento_implausivel",
                "data de nascimento lida "
                f"({data_nascimento_rejeitada.isoformat()}) tornaria o "
                "titular menor de 16 anos na data do casamento — leitura "
                "descartada, nao gravada",
            ))

        # 🔴 Legibilidade (owner directive, 2026-09-28) — a cross-field pass
        # over the SAME transcription every parser above already read, run
        # AFTER `nome` is resolved (titular selection / conjuge pairing)
        # so the filiação check compares the value this function is ABOUT
        # TO RETURN, not a raw candidate already discarded. See
        # `legibilidade.py`'s module docstring for the measured failure this
        # closes.
        #
        # 🔴 TIPO SCOPING (P2 corpus, round 2, 2026-09-28) — the caller's OWN
        # declared `tipo_documento` (e.g. "certidao_casamento",
        # "comprovante_endereco") is what `avaliar_legibilidade` needs to
        # scope its signal set correctly — a certidão's own extenso dates
        # and cartório-footer CEP, or a comprovante's legitimate CNPJ/ICMS
        # lines, are not defects. `kind` (`classify_kind`'s FILENAME guess)
        # is only ever RG/CPF/CNH/UNKNOWN and is the fallback for a caller
        # with nothing better — never a substitute when the real caller
        # (social-wiring's `identidade_extracao_service`) already knows the
        # declared type.
        tipo_efetivo = tipo_documento or _TIPO_DOCUMENTO_POR_KIND.get(kind)
        legibilidade = avaliar_legibilidade(
            text, nome_titular=nome, tipo_documento=tipo_efetivo
        )
        if legibilidade.comprometida:
            avisos.append((
                AVISO_LEITURA_COMPROMETIDA,
                "leitura comprometida: " + (legibilidade.mensagem or "") +
                " — conferencia humana obrigatoria, nada foi gravado sem revisao",
            ))

        aviso: Optional[str] = "+".join(codigo for codigo, _ in avisos) or None
        aviso_mensagem: Optional[str] = " | ".join(msg for _, msg in avisos) or None

        return IdentityFields(
            kind=kind,
            tipo_provavel=classificar_tipo_provavel(text),
            aviso=aviso,
            aviso_mensagem=aviso_mensagem,
            data_nascimento=data,
            data_nascimento_confianca=ExtractionConfidence(data_conf),
            data_nascimento_rotulo=data_label,
            nome=nome,
            nome_confianca=ExtractionConfidence(nome_conf),
            nome_rotulo=nome_label,
            genero=genero,
            genero_confianca=ExtractionConfidence(genero_conf),
            genero_rotulo=genero_label,
            genero_derivado=genero_derivado and genero is not None,
            cpf=cpf,
            cpf_confianca=ExtractionConfidence(cpf_conf),
            cpf_rotulo=cpf_label,
            rg=rg,
            rg_confianca=ExtractionConfidence(rg_conf),
            rg_rotulo=rg_label,
            rg_orgao=rg_orgao,
            rg_orgao_confianca=ExtractionConfidence(rg_orgao_conf),
            identidade_tipo=identidade_tipo,
            rne=rne,
            rne_confianca=ExtractionConfidence(rne_conf),
            rne_rotulo=rne_label,
            rne_orgao=rne_orgao if rne else None,
            registro_cnh=registro_cnh,
            registro_cnh_confianca=ExtractionConfidence(registro_cnh_conf),
            matricula_certidao=matricula_certidao,
            matricula_certidao_confianca=ExtractionConfidence(matricula_conf),
            leituras_alternativas=(("rg", rg_descartado[0]),) if rg_descartado else (),
            ancora_falhou=ancora_falhou(text),
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
            nacionalidade=nacionalidade,
            nacionalidade_confianca=ExtractionConfidence(nacionalidade_conf),
            nacionalidade_rotulo=nacionalidade_label,
            profissao=profissao,
            profissao_confianca=ExtractionConfidence(profissao_conf),
            profissao_rotulo=profissao_label,
            nome_mae=nome_mae,
            nome_mae_confianca=ExtractionConfidence(nome_mae_conf),
            nome_mae_rotulo=nome_mae_label if nome_mae else None,
            nome_pai=nome_pai,
            nome_pai_confianca=ExtractionConfidence(nome_pai_conf),
            nome_pai_rotulo=nome_pai_label if nome_pai else None,
            naturalidade=naturalidade,
            naturalidade_confianca=ExtractionConfidence(naturalidade_conf),
            naturalidade_rotulo=naturalidade_label,
            endereco=endereco if endereco is not None and endereco.presente else None,
            conjuges=conjuges,
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




def _custo(modelo: str, papel: str, eventos: list) -> CustoLeitura:
    """One transcription's spend, from the `llm.usage` events it produced."""
    return CustoLeitura(
        modelo=modelo,
        papel=papel,
        chamadas=len(eventos),
        tokens_entrada=sum(
            (e.prompt_tokens or 0) + (e.cache_creation_input_tokens or 0)
            + (e.cache_read_input_tokens or 0)
            for e in eventos
        ),
        tokens_saida=sum(e.completion_tokens or 0 for e in eventos),
        usd=round(sum(e.cost_estimate_usd or 0.0 for e in eventos), 6),
    )


def _resumo(
    tipo_documento: Optional[str],
    primario: str,
    fallback: Optional[str],
    modo: str,
    vereditos: Mapping[str, "confianca.Veredito"],
    duvidosos: tuple[str, ...],
    primaria: IdentityFields,
    lida_fallback: Optional[IdentityFields],
    resultado: IdentityFields,
    custos: list[CustoLeitura],
    *,
    fallback_executado: bool = False,
) -> ResumoRoteamento:
    """The learning-loop record of one routed read (see `DesfechoCampo`)."""
    criticos = set(confianca.campos_criticos())
    divergentes = {c for c, _ in resultado.divergencias}
    desfechos: list[DesfechoCampo] = []
    for campo, v in vereditos.items():
        if campo not in criticos:
            continue

        def tem(f: Optional[IdentityFields]) -> bool:
            if f is None:
                return False
            return bool(f.conjuges) if campo == "conjuges" else bool(getattr(f, campo, None))

        acordo: Optional[bool] = None
        if lida_fallback is not None and tem(primaria) and tem(lida_fallback):
            if campo == "conjuges":
                acordo = releitura._chaves_conjuges(primaria) == releitura._chaves_conjuges(lida_fallback)
            else:
                acordo = releitura._mesmo_valor(
                    campo, getattr(primaria, campo), getattr(lida_fallback, campo)
                )
        if campo in divergentes:
            desfecho = "divergiu" if lida_fallback is not None else "nao_conciliado"
        elif not tem(resultado):
            desfecho = "nao_conciliado" if campo in duvidosos and lida_fallback is None else "sem_leitura"
        elif campo in duvidosos:
            if acordo:
                desfecho = "concordou"
            elif lida_fallback is None and not fallback_executado:
                desfecho = "nao_conciliado"
            else:
                desfecho = "dv"
        else:
            desfecho = "armazenado"
        def imp(f: Optional[IdentityFields]) -> Optional[str]:
            if f is None:
                return None
            return confianca.impressao(campo, f.conjuges if campo == "conjuges" else getattr(f, campo, None))

        desfechos.append(DesfechoCampo(
            campo=campo, veredito=v.estado, motivos=v.motivos,
            resultado=desfecho, acordo=acordo,
            impressao_primaria=imp(primaria), impressao_fallback=imp(lida_fallback),
        ))
    return ResumoRoteamento(
        tipo_documento=tipo_documento,
        modelo_primario=primario,
        modelo_fallback=fallback,
        modo=modo,
        fallback_executado=fallback_executado,
        campos=tuple(desfechos),
        custos=tuple(custos),
    )


def _achou_algo(fields: IdentityFields) -> bool:
    """Did this TEXT LAYER read find what the document is FOR?

    A text layer that only carries boilerplate must fall through to vision.
    Measured on the P2 corpus (2026-09-28): the gov.br CIN PDF's text layer
    holds only the app's legal notice ("Compartilhado pelo aplicativo
    gov.br…", a date, "Decreto nº …") while the identity data sits in an
    embedded image — an incidental date/emission read counted as "found
    something", vision never ran, and the CIN came back empty. A date alone
    (birth/emission) is not enough; the read must carry a core identity field
    (nome/CPF/RG), an address, the spouses, or an estado civil."""
    return (
        any(fields.presente(c) for c in ("nome", "cpf", "rg", "rne"))
        or fields.endereco is not None
        or bool(fields.conjuges)
        or fields.presente("estado_civil")
    )


def _conjuge_do_titular(
    conjuges: tuple[ConjugeLido, ...], nome: Optional[str], cpf: Optional[str]
) -> Optional[int]:
    """Index of the spouse the titular selection above landed on, else None.

    Keyed on what `_selecionar_nome` / `_selecionar_cpf` already CHOSE (the
    document's own spelling / digits), so the two selections cannot disagree
    about who the titular is.
    """
    idx: Optional[int] = None
    if nome:
        alvo = _chave_nome(nome)
        achados = [i for i, c in enumerate(conjuges) if _chave_nome(c.nome) == alvo]
        if len(achados) == 1:
            idx = achados[0]
        if idx is None:
            # The titular may be known by the name she held BEFORE adopting
            # her married name (`nome` then holds the adopted form). Unique
            # exact match only.
            achados = [
                i for i, c in enumerate(conjuges)
                if c.nome_anterior and _chave_nome(c.nome_anterior) == alvo
            ]
            if len(achados) == 1:
                idx = achados[0]
    if idx is None and cpf:
        alvo_cpf = only_digits(cpf)
        achados = [i for i, c in enumerate(conjuges) if c.cpf and only_digits(c.cpf) == alvo_cpf]
        if len(achados) == 1:
            idx = achados[0]
    return idx


def _chave_nome(valor: str) -> str:
    """Accent-stripped, upper-cased, whitespace-collapsed — for MATCHING."""
    return chave_nome(valor)


def _selecionar_nome(
    candidatos: list[str], titular: Optional[TitularEsperado]
) -> Optional[str]:
    """The ONE printed candidate that is the hinted person, else None.

    Exact match first. Then `name.nomes_compativeis` (word containment — a
    registered "REGINA MARIA PELOSI" against a maiden name printed as
    "REGINA MARIA PELOSI RANGEL") — accepted only when it picks out exactly
    one candidate. Returns the document's spelling, never the hint's.
    """
    if titular is None or not titular.nome:
        return None
    alvo = _chave_nome(titular.nome)
    if not alvo:
        return None
    exatos = [c for c in candidatos if _chave_nome(c) == alvo]
    if len(exatos) == 1:
        return exatos[0]
    contidos = [c for c in candidatos if nomes_compativeis(c, titular.nome)]
    return contidos[0] if len(contidos) == 1 else None


def _selecionar_cpf(
    candidatos: list[str], titular: Optional[TitularEsperado]
) -> Optional[str]:
    """The printed CPF equal (digits only) to the hinted one, else None."""
    if titular is None or not titular.cpf:
        return None
    alvo = only_digits(titular.cpf)
    iguais = [c for c in candidatos if only_digits(c) == alvo]
    return iguais[0] if len(iguais) == 1 else None


__all__ = ["LadderIdentityExtractor"]
