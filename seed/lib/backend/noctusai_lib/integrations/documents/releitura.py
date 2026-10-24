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

THE AGREEMENT GATE (owner decision 2026-10-13 — supersedes every rule below
that picks a winner)
-------------------------------------------------------------------------
Scans and photos are transcribed by a generative vision model that INVENTS
content on dense pages: the same marriage certificate gave two different
divorce averbações, and estado_civil came out divorciado / casado / viúvo on
different runs of the same code. Heuristics that choose between two
disagreeing reads (compromised-first-read-loses, averbação-wins, wrong-shape-
RG-loses, implausible-name-loses) were whack-a-mole. The rule is now:

1. CRITICAL fields (`CAMPOS_CRITICOS`: nome, cpf, rg(+órgão), rne, data_
   nascimento, estado_civil, regime_bens, data_casamento; the spouses'
   names — matched per PERSON by identity, never as one list, see
   `_decidir_conjuges`; the certidão matrícula) are emitted only when TWO
   independent transcriptions agree after normalisation. The escalated re-read therefore
   ALWAYS runs for such documents (`deve_escalar`).
2. A CPF / certidão matrícula whose check digit verifies may stand alone.
3. On disagreement (or a reading only one read produced): NO value; every
   reading in `leituras_alternativas` / `divergencias`; aviso
   `divergencia_leituras`. A consumer opens a human review with them.
4. A transcription holding a CPF or 32-digit matrícula whose check digit
   FAILS is `ancora_falhou`: its readings never count. Likewise a
   `leitura_comprometida` or failed read — a third read is taken when fewer
   than two valid reads exist (`real.LadderIdentityExtractor._escalar`).

🔴 ALWAYS-TWO-READS IS NOW MEASUREMENT-ONLY (owner direction 2026-10-13,
later the same day): "conciliation only on low-reliability extractions that
don't pass the first model's quality and trust gate. Always debating every
run is too expensive." Production reads ONCE with the routed primary model
(`roteamento.rota`), judges every critical field (`confianca.avaliar`) and
pays for ONE fallback read only when a critical field is `duvidoso`; then
`conciliar` reconciles just those fields under the rules above (no third
read). `deve_escalar` + `mesclar` + the third read are the MEASUREMENT mode
(`modo_medicao=True`, evaluation harnesses only).

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

import re

import logging
from dataclasses import dataclass, replace
from typing import Any, Optional

from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.name import chave_nome, nomes_compativeis
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
    # A foreign national's own card — the number is an RNE, never an RG.
    "RNE": _RegraNucleo(campos=("nome", "rne")),
    "CRNM": _RegraNucleo(campos=("nome", "rne")),
    "RNM": _RegraNucleo(campos=("nome", "rne")),
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
    "CERTIDAO_NASCIMENTO": _RegraNucleo(campos=("nome", "data_nascimento")),
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
    faltando = [
        campo for campo in regra.campos
        if not fields.presente(campo)
        # A foreigner's CNH prints an RNE in the identity box — the box is
        # filled, just with the other kind (owner rule 2026-10-13).
        and not (campo == "rg" and fields.presente("rne"))
    ]
    if regra.exige_endereco and fields.endereco is None:
        faltando.append("endereco")
    if regra.exige_dois_conjuges and len(fields.conjuges) != 2:
        faltando.append("conjuges")
    return tuple(faltando)


def deve_escalar(fields: IdentityFields, tipo_documento: Optional[str]) -> bool:
    """Should the caller read the SAME pages again with a stronger model?
    MEASUREMENT MODE ONLY (`modo_medicao=True`) — production decides with the
    trust gate (`confianca.criticos_duvidosos`) instead.

    🔴 ALWAYS, for an OCR read of a document that carries critical identity
    fields (owner decision 2026-10-13): the agreement gate (`mesclar`) needs
    a SECOND independent transcription before any critical field may be
    stored, so the re-read no longer waits for a trigger. The legacy
    triggers (`leitura_comprometida`, a wrong-shape RG, a missing core field)
    remain for types that carry no critical field.

    `fields.source is not TextSource.OCR` short-circuits to `False`: an exact
    PDF text layer is not model-dependent, so a stronger VISION model reads
    the identical bytes no better.
    """
    if fields.source is not TextSource.OCR:
        return False
    if carrega_campos_criticos(fields, tipo_documento):
        return True
    if fields.leitura_comprometida:
        return True
    if resolucao_reduzida(fields):
        # The page reached the model below its legibility floor — a
        # lower-trust read gets the same second look a compromised one does.
        return True
    if rg_anomalo(fields):
        return True
    return bool(campos_nucleo_faltando(fields, tipo_documento))


def rg_anomalo(fields: IdentityFields) -> bool:
    """Does `fields.rg` have the wrong SHAPE for its issuer's UF
    (`identificador.rg_anomalia`: truncated / CPF-shaped)?"""
    if not fields.rg:
        return False
    from noctusai_lib.integrations.documents.rg import separar_orgao_uf

    uf = separar_orgao_uf(fields.rg_orgao)[1]
    return _ident.rg_anomalia(fields.rg, uf=uf) is not None


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
        # RG — an agreement.
        return _ident.equivalentes(campo, str(a), str(b)) is True
    if campo in ("rne", "matricula_certidao"):
        return re.sub(r"[^0-9A-Z]", "", strip_accents_upper(str(a))) == re.sub(
            r"[^0-9A-Z]", "", strip_accents_upper(str(b))
        )
    if campo == "nome":
        return chave_nome(str(a)) == chave_nome(str(b))
    if campo in ("data_nascimento", "data_casamento"):
        return a == b
    # estado_civil / regime_bens / nacionalidade / genero / profissao: each
    # parser already canonicalises its own vocabulary (see `types.
    # IdentityFields`'s per-field comments) — an accent/case difference on
    # an otherwise-identical token is transcription noise, not a new fact.
    return strip_accents_upper(str(a)) == strip_accents_upper(str(b))


# ─── The agreement gate ───────────────────────────────────────────────────

#: 🔴 CRITICAL IDENTITY FIELDS (owner decision 2026-10-13). A generative
#: vision model invents content on dense pages (the same certidão gave two
#: different divorce averbações; estado_civil came out divorciado / casado /
#: viúvo on different runs of the same code), and heuristics that PICK A
#: WINNER between two disagreeing reads were whack-a-mole. These fields are
#: emitted only when two independent transcriptions AGREE; otherwise they are
#: EMPTY, both readings ride in `leituras_alternativas`/`divergencias`, and
#: the aviso `divergencia_leituras` names the field. `rg_orgao`/`rne_orgao`
#: travel with their number; the spouses' names are checked as `conjuges`.
CAMPOS_CRITICOS: tuple[str, ...] = (
    "nome", "cpf", "rg", "rne", "data_nascimento", "estado_civil",
    "regime_bens", "data_casamento",
)
#: Critical but not in `CAMPOS` (group/document-level).
_GRUPOS_CRITICOS: tuple[str, ...] = ("matricula_certidao",)

AVISO_DIVERGENCIA = "divergencia_leituras"

#: Fields whose own check digit lets ONE read stand alone (strong evidence:
#: a mis-copied digit passes a mod-11 check ~1 time in 100).
_CAMPOS_COM_DV = frozenset({"cpf", "matricula_certidao"})

#: Declared types whose critical fields no consumer reads (an address
#: document contributes its address only) — never re-read for them.
_TIPOS_SEM_CRITICOS = frozenset({"COMPROVANTE_ENDERECO"})


def _tem(leitura: IdentityFields, campo: str) -> bool:
    return bool(getattr(leitura, campo, None))


def carrega_campos_criticos(
    fields: IdentityFields, tipo_documento: Optional[str]
) -> bool:
    """Does this document carry critical identity fields? A declared type with
    an authority rule answers from the rule; a type without one is judged by
    what the first read actually found."""
    from noctusai_lib.integrations.documents import autoridade

    tipo = autoridade.tipo_normalizado(tipo_documento)
    if tipo in _TIPOS_SEM_CRITICOS:
        return False
    autorizados = autoridade.campos_autorizados(tipo_documento)
    if autorizados is not None:
        return bool(
            autorizados & (set(CAMPOS_CRITICOS) | {"conjuges", "matricula_certidao"})
        )
    # No authority rule (cpf card, ficha, an undeclared/unlisted type): judged
    # by what the first read actually found.
    return (
        any(_tem(fields, c) for c in CAMPOS_CRITICOS)
        or bool(fields.conjuges)
        or _tem(fields, "matricula_certidao")
    )


def leitura_valida(leitura: IdentityFields) -> bool:
    """May this transcription count toward agreement? Not when the call
    failed, the legibility gate flagged it, or a check-digit anchor in it
    failed (it demonstrably mis-copied digits)."""
    return (
        leitura.error is None
        and not leitura.leitura_comprometida
        and not leitura.ancora_falhou
    )


def _dv_ok(campo: str, valor: Any) -> bool:
    if campo == "cpf":
        return _ident.ler("cpf", str(valor)).dv_ok is True
    if campo == "matricula_certidao":
        r = _ident.validar_matricula_rcpn(valor)
        return bool(r.valido and not r.avisos)
    return False


def _agrupar(
    campo: str, pares: list[tuple[IdentityFields, Any]]
) -> list[list[tuple[IdentityFields, Any]]]:
    grupos: list[list[tuple[IdentityFields, Any]]] = []
    for leitura, valor in pares:
        for g in grupos:
            if _mesmo_valor(campo, g[0][1], valor):
                g.append((leitura, valor))
                break
        else:
            grupos.append([(leitura, valor)])
    return grupos


def _como_texto(valor: Any) -> str:
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


def _somar_codigo(atual: Optional[str], codigo: str) -> str:
    codigos = atual.split("+") if atual else []
    if codigo not in codigos:
        codigos.append(codigo)
    return "+".join(codigos)


def _somar_mensagem(atual: Optional[str], mensagem: str) -> str:
    return f"{atual} | {mensagem}" if atual else mensagem


def _limpar(campo: str) -> dict[str, Any]:
    """The `replace(...)` kwargs that EMPTY a field and what travels with it."""
    out: dict[str, Any] = {campo: None}
    if campo in CAMPOS or campo == "matricula_certidao":
        out[f"{campo}_confianca"] = ExtractionConfidence.NENHUMA
    if campo in CAMPOS:
        out[f"{campo}_rotulo"] = None
    if campo == "rg":
        out.update(rg_orgao=None, rg_orgao_confianca=ExtractionConfidence.NENHUMA)
    if campo == "rne":
        out.update(rne_orgao=None)
    return out


def _preencher(
    campo: str, fonte: IdentityFields, *, promover: bool, irmaos: list[IdentityFields]
) -> dict[str, Any]:
    """The `replace(...)` kwargs that set `campo` (and what travels with it)
    from the read `fonte`. `irmaos` are the other reads that AGREED — an
    issuer one of them printed fills a gap in `fonte`'s."""
    conf = getattr(fonte, f"{campo}_confianca")
    out: dict[str, Any] = {
        campo: getattr(fonte, campo),
        f"{campo}_confianca": _PROMOCAO_UM_DEGRAU[conf] if promover else conf,
    }
    if campo in CAMPOS:
        out[f"{campo}_rotulo"] = getattr(fonte, f"{campo}_rotulo", None)
    if campo in ("rg", "rne"):
        orgao = f"{campo}_orgao"
        com_orgao = next((l for l in [fonte, *irmaos] if getattr(l, orgao)), None)
        out[orgao] = getattr(com_orgao, orgao) if com_orgao else None
        if campo == "rg":
            out["rg_orgao_confianca"] = (
                com_orgao.rg_orgao_confianca if com_orgao else ExtractionConfidence.NENHUMA
            )
        if campo == "rne":
            out["identidade_tipo"] = fonte.identidade_tipo or "rne"
    return out


def _decidir_campo(
    campo: str, todas: list[IdentityFields], validas: list[IdentityFields]
) -> tuple[Optional[dict[str, Any]], list[str], str]:
    """`(kwargs_se_estabelecido, outros_valores, via)` for ONE critical field
    (`via` = `acordo` | `dv` | `nenhuma`).

    - ≥2 VALID reads agree (after normalisation) -> the field is set from
      them, confidence promoted one step; any read that differed rides as an
      alternative.
    - otherwise, exactly one distinct DV-VALID value among the valid reads
      (cpf / matrícula only) -> it stands alone, as evidence of its own.
    - otherwise NOTHING is set (`kwargs` None): every distinct reading
      (every read, valid or not — shown, never counted) is returned for
      review.
    """
    pares = [(l, getattr(l, campo)) for l in validas if _tem(l, campo)]
    grupos = _agrupar(campo, pares)
    concordes = [g for g in grupos if len(g) >= 2]
    if concordes:
        g = max(concordes, key=len)
        fonte = g[0][0]
        if campo in ("rg", "rne", "cpf"):
            # Prefer the member whose value is fullest (an RG WITH its check
            # digit beats the same RG without one).
            fonte = max(g, key=lambda p: len(re.sub(r"[^0-9A-Za-z]", "", str(p[1]))))[0]
        kwargs = _preencher(campo, fonte, promover=True, irmaos=[l for l, _ in g])
        return kwargs, [_como_texto(gg[0][1]) for gg in grupos if gg is not g], "acordo"
    if campo in _CAMPOS_COM_DV:
        com_dv = [g for g in grupos if _dv_ok(campo, g[0][1])]
        if len(com_dv) == 1:
            kwargs = _preencher(campo, com_dv[0][0][0], promover=False, irmaos=[])
            return kwargs, [_como_texto(g[0][1]) for g in grupos if g is not com_dv[0]], "dv"
    valores: list[str] = []
    for l in todas:
        if _tem(l, campo):
            texto = _como_texto(getattr(l, campo))
            if texto not in valores:
                valores.append(texto)
    return None, valores, "nenhuma"


def _chaves_conjuges(leitura: IdentityFields) -> frozenset[str]:
    return frozenset(chave_nome(c.nome) for c in leitura.conjuges if c.nome)


def _texto_conjuges(leitura: IdentityFields) -> str:
    return " / ".join(c.nome for c in leitura.conjuges if c.nome)


# ─── Spouses: agreement by IDENTITY, never by string equality ─────────────
#
# 🔴 F96 (prod, 2026-10-24): a legible certidão's primary read named "A +
# LUCIANA" (the second name cut at a line break), the re-read named only "A";
# the gate compared the two NAME SETS for equality, found them unequal, and
# dropped BOTH spouses — including "A", on which the two reads AGREED. A
# list is not a field: each spouse is a person, matched across reads by who
# they are (normalised name, incl. the maiden/married forms either read
# printed, plus the birth date when both reads have one), and only what
# genuinely conflicts goes to review.

#: Per-person facts compared between two reads of the SAME spouse; a
#: difference is a conflict for review, never resolved by picking a side.
_CAMPOS_CONJUGE_CONFLITO: tuple[str, ...] = ("cpf", "data_nascimento")
#: Per-person facts a matched spouse may take from the other read when its
#: own read left them empty (the person is corroborated; the gap is not a
#: disagreement).
_CAMPOS_CONJUGE_LACUNA: tuple[str, ...] = (
    "nome_anterior", "cpf", "data_nascimento", "nacionalidade", "profissao",
    "genero", "rg", "rg_orgao", "nome_mae", "nome_pai", "naturalidade",
)


def _nomes_do_conjuge(c: Any) -> list[str]:
    return [n for n in (c.nome, c.nome_anterior) if n]


def _mesma_pessoa(a: Any, b: Any) -> bool:
    """Do two reads' spouse entries name the SAME person?

    Equal normalised name (current or maiden form, on either side) -> yes.
    Otherwise the same prenome AND word-containment (`nomes_compativeis` — a
    fuller transcription of the same name), unless both reads carry a birth
    date and the dates differ. A one-word fragment ("LUCIANA") is never an
    identity — `nomes_compativeis` needs two significant words."""
    na, nb = _nomes_do_conjuge(a), _nomes_do_conjuge(b)
    if any(chave_nome(x) == chave_nome(y) for x in na for y in nb):
        return True
    compat = any(
        chave_nome(x).split()[:1] == chave_nome(y).split()[:1] and nomes_compativeis(x, y)
        for x in na for y in nb
    )
    if not compat:
        return False
    return not (a.data_nascimento and b.data_nascimento and a.data_nascimento != b.data_nascimento)


def _parear_conjuges(
    xs: tuple[Any, ...], ys: tuple[Any, ...]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """One-to-one matching `(pares, sobra_x, sobra_y)` — exact-name pairs
    first, then the looser identity rule, each spouse used once."""
    pares: list[tuple[int, int]] = []
    usados_y: set[int] = set()
    for exato in (True, False):
        for i, x in enumerate(xs):
            if any(i == p for p, _ in pares):
                continue
            for j, y in enumerate(ys):
                if j in usados_y:
                    continue
                igual = any(
                    chave_nome(a) == chave_nome(b)
                    for a in _nomes_do_conjuge(x) for b in _nomes_do_conjuge(y)
                )
                if (igual if exato else _mesma_pessoa(x, y)):
                    pares.append((i, j))
                    usados_y.add(j)
                    break
    feitos_x = {i for i, _ in pares}
    return (
        sorted(pares),
        [i for i in range(len(xs)) if i not in feitos_x],
        [j for j in range(len(ys)) if j not in usados_y],
    )


def conjuges_concordam(a: IdentityFields, b: IdentityFields) -> bool:
    """Do two reads name the SAME spouses (identity, not string equality)?"""
    if not a.conjuges or not b.conjuges or len(a.conjuges) != len(b.conjuges):
        return False
    _, sobra_a, sobra_b = _parear_conjuges(a.conjuges, b.conjuges)
    return not sobra_a and not sobra_b


def _fundir_conjuge(x: Any, y: Any) -> tuple[Any, list[str]]:
    """One corroborated spouse out of two reads of them: the fuller name
    (word-containment already established it is the same name), gaps filled
    from the other read, and any per-person fact the two reads state
    DIFFERENTLY emptied — returned as `"campo: a ≠ b"` for review."""
    base, outro = (x, y)
    if len(chave_nome(y.nome)) > len(chave_nome(x.nome)) and not x.nome_anterior:
        base, outro = (y, x)
    upd: dict[str, Any] = {}
    conflitos: list[str] = []
    for campo in _CAMPOS_CONJUGE_CONFLITO:
        va, vb = getattr(base, campo), getattr(outro, campo)
        if va and vb and not _mesmo_valor(campo, va, vb):
            upd[campo] = None
            upd[f"{campo}_confianca"] = "nenhuma"
            conflitos.append(f"{campo} {_como_texto(va)} ≠ {_como_texto(vb)}")
    for campo in _CAMPOS_CONJUGE_LACUNA:
        if campo in upd or getattr(base, campo):
            continue
        valor = getattr(outro, campo)
        if not valor:
            continue
        upd[campo] = valor
        conf = f"{campo}_confianca"
        if hasattr(outro, conf):
            upd[conf] = getattr(outro, conf)
        if campo == "genero":
            upd["genero_derivado"] = outro.genero_derivado
    if outro.confirmado_cabecalho and not base.confirmado_cabecalho:
        upd["confirmado_cabecalho"] = True
    return (replace(base, **upd) if upd else base), conflitos


def _decidir_conjuges(
    validas: list[IdentityFields],
) -> tuple[Optional[tuple[Any, ...]], list[str]]:
    """`(conjuges_estabelecidos | None, leituras_para_revisao)`.

    Over the best-matching pair of VALID reads: every spouse both reads name
    (by identity) is established, merged (`_fundir_conjuge`); a spouse only
    ONE read names is kept when that read itself printed them twice — the
    certidão's header "Nomes:" list AND the qualification block
    (`ConjugeLido.confirmado_cabecalho`) — else withheld for review; a
    per-person fact the reads state differently is emptied for review.
    `None` when no spouse is corroborated at all (fewer than two valid reads
    naming spouses, or no spouse in common)."""
    com = [l for l in validas if l.conjuges]
    melhor: Optional[tuple[int, IdentityFields, IdentityFields, Any]] = None
    for i in range(len(com)):
        for j in range(i + 1, len(com)):
            x, y = com[i], com[j]
            # The read naming more spouses leads (its order is kept).
            if len(y.conjuges) > len(x.conjuges):
                x, y = y, x
            pareio = _parear_conjuges(x.conjuges, y.conjuges)
            if pareio[0] and (melhor is None or len(pareio[0]) > melhor[0]):
                melhor = (len(pareio[0]), x, y, pareio)
    if melhor is None:
        return None, []
    _, x, y, (pares, sobra_x, sobra_y) = melhor
    revisao: list[str] = []
    out: list[Any] = []
    casados = dict(pares)
    for i, cx in enumerate(x.conjuges):
        if i in casados:
            fundido, conflitos = _fundir_conjuge(cx, y.conjuges[casados[i]])
            out.append(fundido)
            revisao += [f"{fundido.nome}: {c}" for c in conflitos]
        elif cx.confirmado_cabecalho and len(x.conjuges) <= 2:
            out.append(cx)
        else:
            revisao.append(cx.nome)
    revisao += [y.conjuges[j].nome for j in sobra_y]
    return tuple(out), revisao


def _portao(leituras: list[IdentityFields], *, modelo: Optional[str]) -> IdentityFields:
    """The agreement gate over every read of ONE document (the cheap read
    first). Pure; see `mesclar`."""
    original = leituras[0]
    validas = [l for l in leituras if leitura_valida(l)]
    # The result's NON-critical content comes from the first read that may
    # be trusted at all; critical fields are recomputed from agreement.
    base = original if leitura_valida(original) else (validas[0] if validas else original)

    updates: dict[str, Any] = {}
    estabelecidos: list[str] = []
    por_dv: list[str] = []
    divergentes: list[tuple[str, tuple[str, ...]]] = []
    alternativas: list[tuple[str, str]] = list(base.leituras_alternativas)

    def anotar(campo: str, valores: list[str]) -> None:
        for v in valores:
            if (campo, v) not in alternativas:
                alternativas.append((campo, v))

    for campo in (*CAMPOS_CRITICOS, *_GRUPOS_CRITICOS):
        if not any(_tem(l, campo) for l in leituras):
            continue
        kwargs, outros, via = _decidir_campo(campo, leituras, validas)
        anotar(campo, outros)
        if kwargs is not None:
            updates.update(kwargs)
            (estabelecidos if via == "acordo" else por_dv).append(campo)
        else:
            updates.update(_limpar(campo))
            divergentes.append((campo, tuple(outros)))

    # Spouses: matched by IDENTITY between two valid reads (`_decidir_conjuges`).
    if any(l.conjuges for l in leituras):
        conjuges_ok, revisao = _decidir_conjuges(validas)
        if conjuges_ok is not None:
            updates["conjuges"] = conjuges_ok
            if revisao:
                anotar("conjuges", revisao)
                divergentes.append(("conjuges", tuple(revisao)))
            else:
                estabelecidos.append("conjuges")
        else:
            updates["conjuges"] = ()
            textos = [
                t for t in dict.fromkeys(_texto_conjuges(l) for l in leituras if l.conjuges) if t
            ]
            anotar("conjuges", textos)
            divergentes.append(("conjuges", tuple(textos)))

    # rg/rne exclusive: the identity box holds ONE document.
    rg_final = updates.get("rg", base.rg)
    if updates.get("rne", base.rne) and rg_final:
        anotar("rg", [_como_texto(rg_final)])
        updates.update(_limpar("rg"))
    if not updates.get("rg", base.rg) and not updates.get("rne", base.rne):
        updates["identidade_tipo"] = None

    # Non-critical fields (genero, nacionalidade, profissao): fill a gap from
    # another valid read; a disagreement keeps the base reading pending.
    outras = [l for l in validas if l is not base]
    for campo in CAMPOS:
        if campo in CAMPOS_CRITICOS:
            continue
        outra = next((l for l in outras if l.presente(campo)), None)
        if outra is None:
            continue
        if not base.presente(campo):
            for suf in ("", "_confianca", "_rotulo"):
                updates[f"{campo}{suf}"] = getattr(outra, f"{campo}{suf}", None)
        elif _mesmo_valor(campo, getattr(base, campo), getattr(outra, campo)):
            conf = getattr(base, f"{campo}_confianca")
            if _PROMOCAO_UM_DEGRAU[conf] is not conf:
                updates[f"{campo}_confianca"] = _PROMOCAO_UM_DEGRAU[conf]
        else:
            updates[f"{campo}_confianca"] = ExtractionConfidence.BAIXA
            anotar(campo, [_como_texto(getattr(outra, campo))])
    for grupo in ("endereco", "data_emissao", "registro_cnh"):
        if not getattr(base, grupo):
            achado = next((l for l in outras if getattr(l, grupo)), None)
            if achado is not None:
                updates[grupo] = getattr(achado, grupo)
                for suf in ("_confianca", "_rotulo"):
                    if hasattr(achado, f"{grupo}{suf}"):
                        updates[f"{grupo}{suf}"] = getattr(achado, f"{grupo}{suf}")

    # Provenance.
    codigos = base.aviso.split("+") if base.aviso else []
    mensagem_base = base.aviso_mensagem
    if base is not original:
        # The cheap read was set aside: keep ITS non-gate codes (e.g.
        # titulares_multiplos), drop the readability flag that no longer
        # describes the transcription the result is built from.
        for c in (original.aviso.split("+") if original.aviso else []):
            if c != AVISO_LEITURA_COMPROMETIDA and c not in codigos:
                codigos.append(c)
        mensagem_base = original.aviso_mensagem
    partes: list[str] = []
    fora = [
        "comprometida" if l.leitura_comprometida
        else ("âncora CPF/matrícula com DV inválido" if l.ancora_falhou else "falhou")
        for l in leituras if not leitura_valida(l)
    ]
    if fora:
        partes.append("leitura(s) fora da concordância: " + ", ".join(fora))
    if estabelecidos:
        partes.append("concordaram (duas leituras independentes): " + ", ".join(estabelecidos))
    if por_dv:
        partes.append("dígito verificador válido (leitura única): " + ", ".join(por_dv))
    if divergentes:
        partes.append(
            "SEM valor — leituras divergentes ou não corroboradas; nenhuma foi "
            "escolhida, todas anexadas para revisão: "
            + "; ".join(f"{c}: " + " ≠ ".join(v) if v else c for c, v in divergentes)
        )
        if AVISO_DIVERGENCIA not in codigos:
            codigos.append(AVISO_DIVERGENCIA)
    if len(leituras) > 1 and AVISO_RELEITURA not in codigos:
        codigos.append(AVISO_RELEITURA)
    if len(validas) < 2:
        partes.append("menos de duas leituras válidas — nada foi corroborado")

    if alternativas != list(base.leituras_alternativas):
        updates["leituras_alternativas"] = tuple(alternativas)
    updates["divergencias"] = tuple(divergentes)
    rotulo_modelo = f"releitura com {modelo}: " if modelo else "leitura única: "
    return replace(
        base,
        aviso="+".join(codigos) or None,
        aviso_mensagem=(
            _somar_mensagem(mensagem_base, rotulo_modelo + "; ".join(partes))
            if partes else mensagem_base
        ),
        **updates,
    )


def mesclar(
    original: IdentityFields,
    escalada: IdentityFields,
    *,
    escalation_model: str,
    extras: tuple[IdentityFields, ...] = (),
) -> IdentityFields:
    """Combine a first read and its escalated re-read(s) (same pages, stronger
    model) under the AGREEMENT GATE — call only when `deve_escalar` said yes.

    A critical field (`CAMPOS_CRITICOS`, the spouses' names, the certidão
    matrícula) is set only when two VALID reads agree after normalisation;
    a single read whose CPF / matrícula check digit verifies may stand alone
    for that field. Otherwise the field is EMPTY, every reading rides in
    `leituras_alternativas` + `divergencias`, and `divergencia_leituras` names
    it. NO heuristic picks a winner (the old compromised-first-read-loses /
    averbação-wins / RG-shape / implausible-name rules are gone for critical
    fields). A read whose call failed, that was flagged `leitura_comprometida`,
    or whose transcription failed its check-digit anchor (`ancora_falhou`)
    never counts toward agreement.
    """
    if escalada.error is not None:
        # The escalation call itself failed (network/credentials/quota):
        # the first read stands ALONE, so only a check-digit-verified value
        # may be emitted.
        logger.warning(
            "releitura: escalation with %s failed: %s",
            escalation_model, escalada.error_message or escalada.error,
        )
        return sem_corroboracao(original)
    if original.source is not TextSource.OCR:
        return original
    leituras = [original, escalada, *(e for e in extras if e.error is None)]
    return _portao(leituras, modelo=escalation_model)


def sem_corroboracao(original: IdentityFields) -> IdentityFields:
    """The gate over a SINGLE read (the re-read could not run): critical
    fields stand only when their own check digit verifies (a valid CPF /
    matrícula); every other critical reading is withheld for review."""
    if original.source is not TextSource.OCR:
        return original
    return _portao([original], modelo=None)



def conciliar(
    primaria: IdentityFields,
    fallback: Optional[IdentityFields],
    *,
    duvidosos: tuple[str, ...],
    modelo_fallback: str,
    substitutos: tuple[str, ...] = (),
) -> IdentityFields:
    """PRODUCTION reconciliation (owner direction 2026-10-13): the primary
    read stands for every field the trust gate passed (`confianca`); only the
    `duvidosos` critical fields are reconciled against ONE fallback read,
    under the agreement gate's rules (`_portao`) — agreement -> stored;
    a check digit that verifies -> stands alone; otherwise EMPTY with both
    readings in `divergencias` for a human (`divergencia_leituras`).

    `fallback=None` (the fallback read failed / produced nothing): the
    doubtful fields get the single-read gate (`sem_corroboracao` rules) and
    the gate-passing fields are kept.

    A gate-passing field the fallback read DIFFERENTLY (it ran for another
    field) keeps the primary value — the gate passed it — and the other
    reading rides in `leituras_alternativas` for the record.

    `substitutos` — only meaningful when the PRIMARY read is invalid as a
    whole (compromised / failed anchor): there is nothing to agree with, so
    the fallback read stands in as the read the gate judges. The caller
    names the fields that passed the trust gate AS THE FALLBACK MODEL's read
    with a MEASURED, sufficient precision (an unmeasured cell is not enough
    for a stand-in); those are stored from the fallback read, the rest stay
    empty for review. Measured on the real benchmark replay: this settles
    the certidão / CNH fields whose primary read failed its anchor, while
    the stand-in rule's measured-precision bar keeps Opus's thin-sample RG
    names (3 wrong in measurement mode) in review.
    """
    if primaria.source is not TextSource.OCR:
        return primaria
    leituras = [primaria] + ([fallback] if fallback is not None and fallback.error is None else [])
    gate = _portao(leituras, modelo=modelo_fallback if len(leituras) > 1 else None)
    if not leitura_valida(primaria):
        # The whole primary read is out (compromised / failed anchor): every
        # critical field was doubtful; the fallback read stands in for the
        # fields the caller found trustworthy on it (`substitutos`).
        if fallback is None or fallback.error is not None or not substitutos:
            return gate
        upd: dict[str, Any] = {}
        postos: list[str] = []
        for campo in substitutos:
            if campo == "conjuges":
                if fallback.conjuges and not gate.conjuges:
                    upd["conjuges"] = fallback.conjuges
                    postos.append(campo)
                continue
            if _tem(fallback, campo) and not _tem(gate, campo):
                upd.update(_preencher(campo, fallback, promover=False, irmaos=[]))
                postos.append(campo)
        if not postos:
            return gate
        divs = tuple(d for d in gate.divergencias if d[0] not in postos)
        cods = gate.aviso.split("+") if gate.aviso else []
        if not divs and AVISO_DIVERGENCIA in cods:
            cods.remove(AVISO_DIVERGENCIA)
        return replace(
            gate,
            divergencias=divs,
            aviso="+".join(cods) or None,
            aviso_mensagem=_somar_mensagem(
                gate.aviso_mensagem,
                f"leitura primária inválida; leitura de {modelo_fallback} aprovada no "
                "portão de confiança (precisão medida) para: " + ", ".join(postos),
            ),
            **upd,
        )
    updates: dict[str, Any] = {}
    mantidos: list[str] = []
    for campo in (*CAMPOS_CRITICOS, *_GRUPOS_CRITICOS):
        if campo in duvidosos or not _tem(primaria, campo):
            continue
        if _tem(gate, campo) and _mesmo_valor(campo, getattr(gate, campo), getattr(primaria, campo)):
            continue
        updates.update(_preencher(campo, primaria, promover=False, irmaos=[]))
        mantidos.append(campo)
    if "conjuges" not in duvidosos and primaria.conjuges:
        if _chaves_conjuges(gate) != _chaves_conjuges(primaria):
            updates["conjuges"] = primaria.conjuges
            mantidos.append("conjuges")
    if "rg" in updates and (updates.get("rne") or gate.rne):
        # The identity box holds ONE document: never re-introduce an RG
        # next to an RNE the gate kept.
        for k in ("rg", "rg_confianca", "rg_rotulo", "rg_orgao", "rg_orgao_confianca"):
            updates.pop(k, None)
        mantidos.remove("rg")
    if updates.get("rg") or updates.get("rne"):
        updates["identidade_tipo"] = primaria.identidade_tipo
    divergencias = tuple(d for d in gate.divergencias if d[0] not in mantidos)
    codigos = gate.aviso.split("+") if gate.aviso else []
    if not divergencias and AVISO_DIVERGENCIA in codigos:
        codigos.remove(AVISO_DIVERGENCIA)
    mensagem = gate.aviso_mensagem
    if mantidos:
        mensagem = _somar_mensagem(
            mensagem,
            "aprovados no portão de confiança da leitura primária (mantidos): "
            + ", ".join(mantidos),
        )
    return replace(
        gate,
        divergencias=divergencias,
        aviso="+".join(codigos) or None,
        aviso_mensagem=mensagem,
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


def resolucao_reduzida(fields: IdentityFields) -> bool:
    """Was this read transcribed from a page delivered BELOW its render
    policy's legibility floor (`vision_tiling.AVISO_RESOLUCAO_REDUZIDA`)?
    Membership in the "+"-joined `aviso`, never a substring match."""
    from noctusai_lib.integrations.documents.vision_tiling import AVISO_RESOLUCAO_REDUZIDA

    return bool(fields.aviso) and AVISO_RESOLUCAO_REDUZIDA in fields.aviso.split("+")


def marcar_resolucao_reduzida(fields: IdentityFields) -> IdentityFields:
    """Append `resolucao_reduzida`: the transcription behind this read had
    to deliver at least one page to the vision model below its legibility
    floor (`documents.vision_tiling` — the page could not be banded within
    its policy). The text is complete; it is LOWER TRUST — `deve_escalar`
    re-reads it, and a human reviewing it should know the model saw a
    coarser image than the policy asked for. Idempotent."""
    from noctusai_lib.integrations.documents.vision_tiling import AVISO_RESOLUCAO_REDUZIDA

    if resolucao_reduzida(fields):
        return fields
    return replace(
        fields,
        aviso=_somar_codigo(fields.aviso, AVISO_RESOLUCAO_REDUZIDA),
        aviso_mensagem=_somar_mensagem(
            fields.aviso_mensagem,
            "página(s) enviada(s) ao modelo de visão abaixo da resolução "
            "mínima de legibilidade — leitura de confiança reduzida",
        ),
    )


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
    "AVISO_DIVERGENCIA",
    "AVISO_RELEITURA",
    "CAMPOS_CRITICOS",
    "campos_nucleo_faltando",
    "carrega_campos_criticos",
    "conciliar",
    "deve_escalar",
    "leitura_valida",
    "marcar_campos_ausentes",
    "marcar_resolucao_reduzida",
    "mesclar",
    "resolucao_reduzida",
    "sem_corroboracao",
]
