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

from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.name import chave_nome
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.documents.types import (
    CAMPOS,
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)
from noctusai_lib.primitives import identificador as _ident

logger = logging.getLogger(__name__)

#: The aviso code this module's finding is surfaced under — "+"-joined with
#: any other code the extractor already raises (see `real.py`'s `avisos`
#: list and `legibilidade.AVISO_LEITURA_COMPROMETIDA`, the same convention).
AVISO_RELEITURA = "releitura_modelo_superior"

#: 🔴 THE SILENT-PARTIAL THIS CLOSES (live prod, 2026-09-30). Three
#: `tipo_documento="rg"` uploads persisted with `extracao_fonte="ocr"`,
#: `data_nascimento_confianca="alta"` — but CPF, RG number, órgão, gênero,
#: nacionalidade and filiação all came back NULL. Nothing was WRONG: the
#: escalation this module already runs (`deve_escalar`) fired, tried the
#: stronger model, and STILL found nothing for those fields on either read.
#: `mesclar`'s own `if not updates and not estava_comprometida: return
#: original` path is exactly right for that case — there is genuinely
#: nothing new to report — but "nothing changed" and "the document's core
#: fields are still missing" are different facts, and only the first one
#: got an aviso. A birthdate at `alta` sitting beside four blank required
#: columns, with no code on the row saying so, reads as a clean success to
#: any consumer that does not independently re-derive `_TABELA_NUCLEO` for
#: itself. This aviso is that missing signal, raised once — by the CALLER,
#: after whatever reads it is going to get have already happened (the
#: first read, the text-layer→vision fallthrough, and the escalation, if
#: any) — never by this module directly (see `campos_nucleo_faltando`,
#: which stays a pure query with no opinion on when to call it).
AVISO_CAMPOS_NUCLEO_AUSENTES = "campos_nucleo_ausentes"


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


def campos_nucleo_faltando(
    fields: IdentityFields, tipo_documento: Optional[str]
) -> tuple[str, ...]:
    """Which of the declared type's CORE fields (`_TABELA_NUCLEO`) this
    reading still lacks — empty when the type has no completeness rule, or
    when the rule is fully satisfied.

    THE SAME declarative table `deve_escalar` already reads, factored out
    so a SECOND caller (`real.py`'s post-read completeness check, added for
    the silent-partial fix — see `AVISO_CAMPOS_NUCLEO_AUSENTES`) can ask
    "is this reading complete for its type" without re-deriving the table
    or re-implementing `deve_escalar`'s own OCR/comprometida gating (which
    that caller does not want: a TEXT-LAYER read missing a core field is
    just as incomplete as an OCR one, even though it would never trigger a
    RE-READ — see `deve_escalar`'s own docstring for why THAT gate exists
    only for the escalation decision, not for completeness itself).

    A type absent from `_TABELA_NUCLEO` never reports anything missing —
    the same restrictive default `deve_escalar`/`legibilidade.
    ClasseDocumento.OUTRO` use: an unlisted type carries no known
    completeness contract, so silence is the honest answer, not a guess.
    """
    regra = _TABELA_NUCLEO.get(strip_accents_upper(tipo_documento or ""))
    if regra is None:
        return ()
    faltando = [campo for campo in regra.campos if not fields.presente(campo)]
    if regra.exige_endereco and fields.endereco is None:
        faltando.append("endereco")
    if regra.exige_dois_conjuges and len(fields.conjuges) != 2:
        faltando.append("conjuges")
    return tuple(faltando)


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
    return bool(campos_nucleo_faltando(fields, tipo_documento))


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
    if campo in ("cpf", "rg"):
        # The ONE identifier registry (`primitives.identificador`, owner rule
        # 2026-10-01): same identifier in any punctuation, and an RG read
        # without its check digit (a CNH) against the full one is the SAME
        # RG — an agreement, not a disagreement that blanks or demotes it.
        return _ident.equivalentes(campo, str(a), str(b)) is True
    if campo == "nome":
        return chave_nome(str(a)) == chave_nome(str(b))
    if campo in ("data_nascimento", "data_casamento"):
        return a == b
    # estado_civil / regime_bens / nacionalidade / genero / profissao: each
    # parser already canonicalises its own vocabulary (see `types.
    # IdentityFields`'s per-field comments) — an accent/case difference on
    # an otherwise-identical token is transcription noise, not a new fact.
    return strip_accents_upper(str(a)) == strip_accents_upper(str(b))


#: Fields whose check digit can break a tie between two DISAGREEING reads.
_CAMPOS_COM_DV = frozenset({"cpf", "rg"})


def _vencedor_por_dv(campo: str, a: Any, b: Any) -> Optional[str]:
    """`'original'` / `'escalada'` when EXACTLY ONE of two disagreeing reads
    passes the field's check digit and the other fails it, else `None`.

    A one-digit OCR slip passes a mod-11 check 1 time in ~11 (CPF: 1 in 100),
    so a reading that verifies against one that does not is overwhelmingly
    the right one — deterministic, zero extra API cost, and the only honest
    way to break a tie between two models (`15.668.564-3` vs
    `16.669.554-3`). Both valid, both invalid, or a field with no check
    digit stays what it was: a disagreement."""
    if campo not in _CAMPOS_COM_DV:
        return None
    la, lb = _ident.ler(campo, str(a)), _ident.ler(campo, str(b))
    if la.dv_ok is True and lb.dv_ok is False:
        return "original"
    if lb.dv_ok is True and la.dv_ok is False:
        return "escalada"
    return None


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
    dv_adotados: list[str] = []
    dv_mantidos: list[str] = []

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
            elif (vencedor_dv := _vencedor_por_dv(campo, v0, v1)) is not None:
                if vencedor_dv == "original":
                    # The first read verifies, the escalated one does not —
                    # keep the first, untouched.
                    dv_mantidos.append(campo)
                else:
                    # The escalated read verifies, the first does not — adopt
                    # it, but as a `baixa` suggestion with a divergence note:
                    # still human-gated, never alta.
                    updates[campo] = v1
                    updates[f"{campo}_confianca"] = ExtractionConfidence.BAIXA
                    updates[f"{campo}_rotulo"] = getattr(escalada, f"{campo}_rotulo", None)
                    if campo == "rg":
                        updates["rg_orgao"] = escalada.rg_orgao
                        updates["rg_orgao_confianca"] = (
                            ExtractionConfidence.BAIXA if escalada.rg_orgao else ExtractionConfidence.NENHUMA
                        )
                    dv_adotados.append(campo)
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

    if not updates and not estava_comprometida and not dv_mantidos:
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
    if dv_adotados:
        partes.append(
            "divergiu (adotado o valor com dígito verificador válido do modelo "
            "superior como sugestão baixa — confirme): " + ", ".join(dv_adotados)
        )
    if dv_mantidos:
        partes.append(
            "divergiu (mantido o valor da primeira leitura, o único com dígito "
            "verificador válido): " + ", ".join(dv_mantidos)
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


#: Human-readable field names for `marcar_campos_ausentes`'s message —
#: `CAMPOS`/`_TABELA_NUCLEO` entries are attribute names, not prose.
_NOME_CAMPO = {
    "nome": "nome",
    "cpf": "CPF",
    "rg": "RG",
    "estado_civil": "estado civil",
    "endereco": "endereço",
    "conjuges": "os dois cônjuges",
}


def marcar_campos_ausentes(
    fields: IdentityFields, faltando: tuple[str, ...], *, tipo_documento: Optional[str] = None
) -> IdentityFields:
    """Append `AVISO_CAMPOS_NUCLEO_AUSENTES` naming which of the document's
    OWN core fields never came through — call once, after every rung this
    read is going to try (the text-layer→vision fallthrough, the
    escalation) has already run, with whatever `faltando` still reports.

    Additive, like every other `aviso` this package accumulates
    (`_somar_codigo`/`_somar_mensagem`): a document already flagged
    `leitura_comprometida` or `titulares_multiplos` keeps BOTH codes,
    because each names an independent reason a human should look at this
    read rather than trust it unattended.

    A no-op (`fields` returned unchanged) when `faltando` is empty — the
    caller is expected to check `campos_nucleo_faltando(...)` itself before
    calling this, but a defensive empty call must not fabricate an aviso
    over nothing.
    """
    if not faltando:
        return fields
    nomes = ", ".join(_NOME_CAMPO.get(c, c) for c in faltando)
    return replace(
        fields,
        aviso=_somar_codigo(fields.aviso, AVISO_CAMPOS_NUCLEO_AUSENTES),
        aviso_mensagem=_somar_mensagem(
            fields.aviso_mensagem,
            f"documento tipo {tipo_documento or fields.tipo_provavel or 'declarado'} "
            f"sem {nomes} — campo(s) que o próprio tipo de documento deveria "
            "carregar não foram lidos em nenhuma tentativa; solicite uma "
            "cópia melhor ou confira manualmente",
        ),
    )


__all__ = [
    "AVISO_CAMPOS_NUCLEO_AUSENTES",
    "AVISO_RELEITURA",
    "campos_nucleo_faltando",
    "deve_escalar",
    "marcar_campos_ausentes",
    "mesclar",
]
