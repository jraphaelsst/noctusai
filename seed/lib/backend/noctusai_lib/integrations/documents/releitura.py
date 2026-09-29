"""Re-read escalation: when the cheap vision pass is untrustworthy or
incomplete, read the SAME pages again with a stronger model and merge
deterministically. Never guesses.

WHY THIS EXISTS — MEASURED, NOT ASSUMED (P2 corpus, 2026-09-28)
-----------------------------------------------------------------
`legibilidade.py`'s gate already catches a hallucinated read and withholds
it for a human. What it cannot catch is plain RUN-TO-RUN VARIANCE: the same
RG, read 4 times locally, came back correctly every time; the same file,
read once in prod, came back empty. Neither read looked "suspicious" on its
own terms — the model was simply less lucky once. A second, independent
read with a stronger model (`documents.providers.ESCALATION_OCR_MODELS`) is
a fresh roll of the dice against exactly that failure mode, on the SAME
bytes the first read already paid to rasterize.

This module owns the two PURE decisions that surround that second call:

1. `deve_escalar` — should a caller bother re-reading at all? (`documents.
   real.LadderIdentityExtractor` owns the IO — calling the ladder again
   with the escalation model — this module only says whether to.)
2. `mesclar` — given both reads, what is the honest combined answer?

WHY THE MERGE IS CONSERVATIVE, NEVER A TIE-BREAKER
---------------------------------------------------
Two independent transcriptions AGREEING is real corroborating evidence — a
fourth measured shape for `ExtractionConfidence.MEDIA`, alongside the three
that dataclass's own docstring already enumerates (money's extenso match,
the MRZ corroboration, `conjuges`' positional attribution). Two
transcriptions DISAGREEING is the opposite: neither reading is more
trustworthy than the other just because one ran second, so the honest
answer is "we don't know", never "pick the newer one" — that is exactly the
kind of guess this whole extractor family refuses to make (see
`types.IdentityFields`'s own module-level contract). A disagreement is
therefore reported ABSENT, with the conflict named in `aviso`, and routed
to whatever human-review surface the consumer already has for a `sugestao`
— never silently overridden by either side.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Optional

from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.name import chave_nome
from noctusai_lib.integrations.documents.rg import only_alnum
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.documents.types import (
    CAMPOS,
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

logger = logging.getLogger(__name__)

#: The aviso code this module's finding is surfaced under — "+"-joined with
#: any other code the extractor already raises (see `real.py`'s `avisos`
#: list and `legibilidade.AVISO_LEITURA_COMPROMETIDA`, the same convention).
AVISO_RELEITURA = "releitura_modelo_superior"


@dataclass(frozen=True)
class _RegraNucleo:
    """One row of the trigger table: what "the first read is COMPLETE"
    means for one declared document type."""

    #: `CAMPOS` names that must be `presente()` for the type to be
    #: considered complete. Missing ANY one of these triggers a re-read.
    campos: tuple[str, ...] = ()
    #: The address group (`IdentityFields.endereco`, not a `CAMPOS` member)
    #: must be present.
    exige_endereco: bool = False
    #: The document must have resolved BOTH spouses
    #: (`len(IdentityFields.conjuges) == 2`) — only meaningful for a type
    #: that structurally names two people.
    exige_dois_conjuges: bool = False


#: THE declarative trigger table (normalized `tipo_documento` ->
#: completeness rule). A type absent here never triggers on missing-field
#: grounds — the same restrictive default `legibilidade.ClasseDocumento
#: .OUTRO` uses; `leitura_comprometida` (checked independently in
#: `deve_escalar`, below) is the only signal an unlisted type can still
#: trigger on.
_TABELA_NUCLEO: dict[str, _RegraNucleo] = {
    # Cards — nome/cpf always; rg additionally, ONLY where the card prints
    # one (a CIN/CPF card carries no RG number of its own).
    "RG": _RegraNucleo(campos=("nome", "cpf", "rg")),
    "CNH": _RegraNucleo(campos=("nome", "cpf", "rg")),
    "CIN": _RegraNucleo(campos=("nome", "cpf")),
    "CPF": _RegraNucleo(campos=("nome", "cpf")),
    # Comprovante — the address IS the document's own subject (mirrors
    # `legibilidade.ClasseDocumento.COMPROVANTE`'s own scoping).
    "COMPROVANTE_ENDERECO": _RegraNucleo(exige_endereco=True),
    # Certidão de casamento structurally names two people — a read that
    # resolved fewer than two is incomplete even when estado_civil itself
    # came through. Certidão de nascimento carries no such expectation (its
    # "cônjuges" concept does not apply), but DOES carry an
    # estado-civil-relevant averbação just like the marriage one (see
    # `identidade_extracao_service._TIPOS_CERTIDAO_ESTADO_CIVIL`).
    "CERTIDAO_CASAMENTO": _RegraNucleo(
        campos=("estado_civil",), exige_dois_conjuges=True
    ),
    "CERTIDAO_NASCIMENTO": _RegraNucleo(campos=("estado_civil",)),
}


def deve_escalar(fields: IdentityFields, tipo_documento: Optional[str]) -> bool:
    """Should the caller read the SAME pages again with a stronger model?

    `fields.source is not TextSource.OCR` short-circuits to `False` even
    when `leitura_comprometida` — an exact PDF text layer is not
    model-dependent, so a stronger VISION model reads the identical bytes
    no better. Escalation only helps a transcription that already went
    through a vision pass.
    """
    if fields.source is not TextSource.OCR:
        return False
    if fields.leitura_comprometida:
        return True
    regra = _TABELA_NUCLEO.get(strip_accents_upper(tipo_documento or ""))
    if regra is None:
        return False
    if any(not fields.presente(campo) for campo in regra.campos):
        return True
    if regra.exige_endereco and fields.endereco is None:
        return True
    if regra.exige_dois_conjuges and len(fields.conjuges) != 2:
        return True
    return False


#: A two-model AGREEMENT promotes a field's confidence by ONE step, never
#: past `MEDIA` — see the module docstring. `NENHUMA` has nothing to
#: promote (a present value at `NENHUMA` confidence should not occur, but
#: the map stays total rather than partial); `ALTA` is already past the
#: corroboration ceiling.
_PROMOCAO_UM_DEGRAU: dict[ExtractionConfidence, ExtractionConfidence] = {
    ExtractionConfidence.NENHUMA: ExtractionConfidence.NENHUMA,
    ExtractionConfidence.BAIXA: ExtractionConfidence.MEDIA,
    ExtractionConfidence.MEDIA: ExtractionConfidence.MEDIA,
    ExtractionConfidence.ALTA: ExtractionConfidence.ALTA,
}


#: Fields where, on a disagreement, the escalated (stronger-model) read is
#: kept as a `baixa` suggestion instead of blanking the field. Only fields
#: with measured evidence belong here (RG: escalated read right 3/3 on the
#: P2 corpus); everything else keeps "disagreement is absence".
_ADOTA_ESCALADA_NA_DIVERGENCIA = frozenset({"rg"})


def _mesmo_valor(campo: str, a: Any, b: Any) -> bool:
    """Do these two INDEPENDENT reads of the SAME document state the same
    fact for `campo`?

    Deliberately STRICTER than `identidade_extracao_service._mesmo_valor`
    (which compares a fresh extraction against a human-typed record, where
    "close enough to be the same person" is the right bar): here both
    values are machine transcriptions of the IDENTICAL source, so the bar
    is exact-modulo-normalisation, and a genuine difference — even a
    dropped middle name — is a disagreement, never a match.
    """
    if campo == "cpf":
        return only_digits(str(a)) == only_digits(str(b))
    if campo == "rg":
        return only_alnum(str(a)) == only_alnum(str(b))
    if campo == "nome":
        return chave_nome(str(a)) == chave_nome(str(b))
    if campo in ("data_nascimento", "data_casamento"):
        return a == b
    # estado_civil / regime_bens / nacionalidade / genero / profissao: each
    # parser already canonicalises its own vocabulary (see `types.
    # IdentityFields`'s per-field comments) — an accent/case difference on
    # an otherwise-identical token is transcription noise, not a new fact.
    return strip_accents_upper(str(a)) == strip_accents_upper(str(b))


def _somar_codigo(atual: Optional[str], codigo: str) -> str:
    codigos = atual.split("+") if atual else []
    if codigo not in codigos:
        codigos.append(codigo)
    return "+".join(codigos)


def _somar_mensagem(atual: Optional[str], mensagem: str) -> str:
    return f"{atual} | {mensagem}" if atual else mensagem


def mesclar(
    original: IdentityFields, escalada: IdentityFields, *, escalation_model: str
) -> IdentityFields:
    """Deterministic, conservative merge of a first read and its escalated
    re-read (same pages, stronger model) — call only when `deve_escalar`
    said yes. Field-by-field over `CAMPOS`: a gap in `original` is filled
    from `escalada`; a value both carry that AGREES may have its confidence
    promoted one step (never past `MEDIA` — see `_PROMOCAO_UM_DEGRAU`); a
    value both carry that DISAGREES is reported ABSENT, never chosen.
    """
    if escalada.error is not None:
        # The escalation call itself failed (network/credentials/quota) —
        # nothing to merge. The ORIGINAL read's own retry policy is
        # unaffected by this best-effort second call failing.
        logger.warning(
            "releitura: escalation with %s failed: %s",
            escalation_model, escalada.error_message or escalada.error,
        )
        return original

    if escalada.leitura_comprometida:
        # Both readings are compromised. The original was already withheld
        # (the human gate `IdentityFields.leitura_comprometida` already
        # enforces) — recorded so a reviewer sees the stronger model was
        # tried and ALSO could not trust this transcription, rather than
        # silently stopping at one attempt.
        return replace(
            original,
            aviso=_somar_codigo(original.aviso, AVISO_RELEITURA),
            aviso_mensagem=_somar_mensagem(
                original.aviso_mensagem,
                f"releitura com {escalation_model} também comprometida — "
                "ambas as leituras retidas para revisão humana",
            ),
        )

    # 🔴 A CLEAN ESCALATED READ LIFTS THE `leitura_comprometida` GATE.
    # Escalating exists PRECISELY so a document does not stay withheld
    # forever on one bad transcription — "the escalated read is not
    # comprometida" is the brief's own condition for "use it". The CODE is
    # what `IdentityFields.leitura_comprometida` actually gates on, so it is
    # removed here; `aviso_mensagem` (below) keeps the FULL history —
    # including the original comprometida sentence — for audit, since it is
    # human-facing prose, never machine-matched (see `AVISO_LEITURA_
    # COMPROMETIDA`'s own docstring).
    estava_comprometida = original.leitura_comprometida
    codigos = [
        c for c in (original.aviso.split("+") if original.aviso else [])
        if c != AVISO_LEITURA_COMPROMETIDA
    ]

    updates: dict[str, Any] = {}
    preenchidos: list[str] = []
    confirmados: list[str] = []
    conflitantes: list[str] = []
    adotados: list[str] = []

    for campo in CAMPOS:
        tinha = original.presente(campo)
        tem_escalada = escalada.presente(campo)
        if not tinha and tem_escalada:
            updates[campo] = getattr(escalada, campo)
            updates[f"{campo}_confianca"] = getattr(escalada, f"{campo}_confianca")
            updates[f"{campo}_rotulo"] = getattr(escalada, f"{campo}_rotulo", None)
            preenchidos.append(campo)
            if campo == "rg":
                # `rg_orgao` TRAVELS WITH `rg` — see `types.IdentityFields
                # .rg_orgao`'s own comment. Whichever side supplies `rg`
                # must also supply its issuer.
                updates["rg_orgao"] = escalada.rg_orgao
                updates["rg_orgao_confianca"] = escalada.rg_orgao_confianca
        elif tinha and tem_escalada:
            v0, v1 = getattr(original, campo), getattr(escalada, campo)
            if _mesmo_valor(campo, v0, v1):
                atual_conf = getattr(original, f"{campo}_confianca")
                nova_conf = _PROMOCAO_UM_DEGRAU[atual_conf]
                if nova_conf is not atual_conf:
                    updates[f"{campo}_confianca"] = nova_conf
                    confirmados.append(campo)
            elif campo in _ADOTA_ESCALADA_NA_DIVERGENCIA:
                # Measured exception (P2 corpus, 2026-09-29): on every RG
                # disagreement (3/3 CNHs) the escalated read matched the
                # signed contract and the first read was wrong — blanking the
                # field discarded the right answer. So the stronger model's
                # value is kept, but only as a `baixa` suggestion with an
                # explicit divergence note: still human-gated, never alta.
                updates[campo] = v1
                updates[f"{campo}_confianca"] = ExtractionConfidence.BAIXA
                updates[f"{campo}_rotulo"] = getattr(escalada, f"{campo}_rotulo", None)
                if campo == "rg":
                    updates["rg_orgao"] = escalada.rg_orgao
                    updates["rg_orgao_confianca"] = (
                        ExtractionConfidence.BAIXA if escalada.rg_orgao else ExtractionConfidence.NENHUMA
                    )
                adotados.append(campo)
            else:
                # Genuine disagreement — never pick one. Reported absent,
                # not merely demoted to a suggestion: two independent
                # models disagreeing is a stronger signal of trouble than
                # either read's own confidence describes on its own.
                updates[campo] = None
                updates[f"{campo}_confianca"] = ExtractionConfidence.NENHUMA
                updates[f"{campo}_rotulo"] = None
                conflitantes.append(campo)
        # both absent: nothing to do — neither read found this field.

    # Grupo fields (outside `CAMPOS`) — filled ONLY when the original had
    # none at all. NOC-REMEDIATE[releitura-conjuge-merge]: this does not
    # cross-check each spouse's OWN facts field-by-field against a
    # partially-resolved original — aligning "which escalated cônjuge is
    # the same person as which original cônjuge" needs its own matching
    # rule this module does not yet have. 2026-09-28.
    if original.endereco is None and escalada.endereco is not None:
        updates["endereco"] = escalada.endereco
        preenchidos.append("endereco")
    if len(original.conjuges) != 2 and len(escalada.conjuges) == 2:
        updates["conjuges"] = escalada.conjuges
        preenchidos.append("conjuges")
    if original.data_emissao is None and escalada.data_emissao is not None:
        updates["data_emissao"] = escalada.data_emissao
        updates["data_emissao_confianca"] = escalada.data_emissao_confianca
        updates["data_emissao_rotulo"] = escalada.data_emissao_rotulo

    if not updates and not estava_comprometida:
        # Nothing changed and there was no gate to lift — no provenance
        # worth recording.
        return original

    partes: list[str] = []
    if estava_comprometida:
        partes.append("não ficou comprometida — leitura original liberada")
    if preenchidos:
        partes.append("preencheu: " + ", ".join(preenchidos))
    if confirmados:
        partes.append("confirmou: " + ", ".join(confirmados))
    if adotados:
        partes.append(
            "divergiu (adotado o valor do modelo superior como sugestão baixa — "
            "confirme): " + ", ".join(adotados)
        )
    if conflitantes:
        partes.append(
            "divergiu (descartado, revisão humana necessária): "
            + ", ".join(conflitantes)
        )
    mensagem = f"releitura com {escalation_model} " + "; ".join(partes)

    if AVISO_RELEITURA not in codigos:
        codigos.append(AVISO_RELEITURA)

    return replace(
        original,
        aviso="+".join(codigos) or None,
        aviso_mensagem=_somar_mensagem(original.aviso_mensagem, mensagem),
        **updates,
    )


__all__ = ["AVISO_RELEITURA", "deve_escalar", "mesclar"]
