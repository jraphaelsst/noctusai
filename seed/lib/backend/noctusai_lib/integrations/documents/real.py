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
from dataclasses import replace
from typing import Optional

from noctusai_lib.integrations.documents.address import find_endereco
from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.civil_status import (
    find_data_casamento,
    find_data_emissao,
    find_estado_civil,
    find_regime_bens,
)
from noctusai_lib.integrations.documents.conjuges import ConjugeLido, find_conjuges
from noctusai_lib.integrations.documents.cpf import (
    find_cpf,
    find_cpf_conflitos,
    only_digits,
)
from noctusai_lib.integrations.documents.gender import find_gender
from noctusai_lib.integrations.documents.fake import classify_kind
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.misfile import classificar_tipo_provavel
from noctusai_lib.integrations.documents.transcription import (
    identity_document_render_dpi_policy,
)
from noctusai_lib.integrations.documents.nacionalidade import find_nacionalidade
from noctusai_lib.integrations.documents.name import (
    chave_nome,
    find_name,
    find_name_conflitos,
    nomes_compativeis,
)
from noctusai_lib.integrations.documents.profession import find_profissao
from noctusai_lib.integrations.documents.rg import find_rg, find_rg_orgao
from noctusai_lib.integrations.documents.types import (
    CAMPOS,
    ExtractionConfidence,
    IdentityFields,
    TextSource,
    TitularEsperado,
)

logger = logging.getLogger(__name__)

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

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
        titular: Optional[TitularEsperado] = None,
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

        fields = self._ler(text, source, kind, titular)
        if source is TextSource.TEXT_LAYER and not _achou_algo(fields):
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
            texto_ocr, fonte_ocr, err_ocr = await self._ladder.to_text(
                content, mimetype, filename, pular_camada_texto=True
            )
            if err_ocr is not None:
                # The text layer had nothing and vision could not run: that
                # is a failure to read, not an empty document — report it so
                # the consumer's bounded retry can try again.
                return IdentityFields(
                    kind=kind, source=fonte_ocr, error=err_ocr[0], error_message=err_ocr[1]
                )
            if texto_ocr.strip():
                return self._ler(texto_ocr, fonte_ocr, kind, titular)
        return fields

    def _ler(
        self,
        text: str,
        source: TextSource,
        kind,
        titular: Optional[TitularEsperado],
    ) -> IdentityFields:
        """Pure half: text + the rung that produced it -> typed fields."""
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
        nacionalidade, nacionalidade_conf, nacionalidade_label = find_nacionalidade(text)

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
        if nome is None:
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
        if cpf is None:
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
        profissao, profissao_conf, profissao_label = find_profissao(text)

        # Endereço — read on every document (the extractor is type-agnostic);
        # WHICH document types may promote it is the consumer's decision (a
        # certidão prints its CARTÓRIO's address, which is nobody's home).
        endereco = find_endereco(text)

        # Both spouses, when the document names two. The one the caller's
        # `titular` hint picked (by the name or CPF selected above) is marked,
        # and ITS per-person facts replace the whole-document readings, which
        # would otherwise mix the two spouses (two birthdates -> `nenhuma`,
        # or worse, the wrong one alone).
        conjuges = find_conjuges(text)
        if conjuges:
            escolhido_idx = _conjuge_do_titular(conjuges, nome, cpf)
            if escolhido_idx is not None:
                marcados = []
                for i, c in enumerate(conjuges):
                    marcados.append(replace(c, titular=(i == escolhido_idx)))
                conjuges = tuple(marcados)
                eu = conjuges[escolhido_idx]
                if eu.data_nascimento is not None:
                    data, data_conf, data_label = (
                        eu.data_nascimento, eu.data_nascimento_confianca, "certidão (cônjuge titular)"
                    )
                if eu.nacionalidade is not None:
                    nacionalidade, nacionalidade_conf, nacionalidade_label = (
                        eu.nacionalidade, eu.nacionalidade_confianca, "certidão (cônjuge titular)"
                    )
                if eu.profissao is not None:
                    profissao, profissao_conf, profissao_label = (
                        eu.profissao, eu.profissao_confianca, "certidão (cônjuge titular)"
                    )
                if eu.genero is not None and genero is None:
                    genero, genero_conf, genero_label = (
                        eu.genero, eu.genero_confianca, "certidão (concordância)"
                    )
                if cpf is None and eu.cpf:
                    cpf, cpf_conf, cpf_label = eu.cpf, eu.cpf_confianca, "CPF (titular do card)"
                    # The spouse pairing resolved what the bare CPF hint could
                    # not — it is no longer a withheld field.
                    multiplos_titulares = [
                        m for m in multiplos_titulares if not m.startswith("cpf ")
                    ]

        aviso: Optional[str] = None
        aviso_mensagem: Optional[str] = None
        if multiplos_titulares:
            aviso = "titulares_multiplos"
            aviso_mensagem = (
                "documento nomeia mais de um titular com igual proeminencia "
                "para: " + ", ".join(multiplos_titulares) + " — esses campos "
                "nao foram gravados; os demais (estado civil, regime, datas) sim"
            )

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
            nacionalidade=nacionalidade,
            nacionalidade_confianca=ExtractionConfidence(nacionalidade_conf),
            nacionalidade_rotulo=nacionalidade_label,
            profissao=profissao,
            profissao_confianca=ExtractionConfidence(profissao_conf),
            profissao_rotulo=profissao_label,
            endereco=endereco if endereco.presente else None,
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




def _achou_algo(fields: IdentityFields) -> bool:
    """Did this read find ANY field a consumer can use?"""
    return (
        any(fields.presente(c) for c in CAMPOS)
        or fields.data_emissao is not None
        or fields.endereco is not None
        or bool(fields.conjuges)
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
