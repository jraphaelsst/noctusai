"""Resolve a `cliente_campo_conflitos`-shaped divergence without a human —
owner directive, 2026-09-29, quoted verbatim:

    "Those data divergencies we've been having on extractions, i need you to
    reason on how to solve this and resolve divergencies without the need of
    a human. You are to do this using docs and done contracts. The idea is
    for us to dont need to reason on every file, but to parse correctly each
    and every data we will need on the contract."

WHAT THIS IS
------------
A pure, table-driven POLICY: given two disagreeing readings of the same
`clientes` field (the one already on file, and a newly-extracted one), decide
which one is the FACT — or admit that only a human can tell, exactly as
today. `resolver_divergencia` never touches a database; the DB-aware wrapper
that opens/updates a `cliente_campo_conflitos` row lives in
`app.services.campo_conflitos` (`resolver_e_registrar`), which calls this
module for the decision and stays owner-column-agnostic itself — the same
split `campo_conflitos.py` already draws between "open/dedupe mechanics" and
"what counts as the same value" (that one stays with each caller too).

THE EVIDENCE (owner directive, 2026-09-29 — measured on prod: every
extracted value per source vs. the 10 SIGNED P2 contracts; precision = share
equal to the contract's final value)
--------------------------------------------------------------------------
    nome_oficial:  cnh 19/19, rg 2/2, serasa_crednet 12/12 (100%);
                   matricula 16/19 (84%); certidao_casamento 3/5 (60%).
    cpf:           cnh 19/19, rg 1/1, serasa_crednet 12/12 (100%);
                   certidao_casamento 2/3 (67%).
    rg:            rg (card) 2/2 (100%); cnh 7/18 (39% — the CNH prints the
                   RG WITHOUT its check digit; the contract carries the full
                   RG); matricula 6/16 (38%).
    rg_orgao_expedidor: matricula 14/14 (100%), cnh 19/20 (95%).
    genero:        cnh 11/11 (100%), matricula 18/19 (95%),
                   certidao_casamento 3/4 (75%).
    nacionalidade: cnh 17/17, certidao_casamento 6/6, certidao_nascimento
                   6/6, matricula 19/19 (100%).
    estado_civil:  certidao_casamento 13/13, matricula 3/3 (100%).
    regime_bens:   certidao_casamento 12/12 (100%).
    profissao:     matricula 3/3 (100%) — few linked yet at measurement time
                   (a re-link fix, 116244ecd, landed the same day).

`PRECISAO` below is this table, as data, with each cell's sample size (`n`)
carried alongside the ratio — a tier comparison with `n=1` or `n=2` is
noted, never hidden, so a future recalibration
(`noctus.dev.divergencia_calibrar`, the read-only MCP tool that recomputes
this same shape from `~/.noctusai/private/answer-keys/` as more signed
contracts arrive) can tell a well-measured cell from a thin one at a glance.

THE RESOLUTION ORDER (owner directive)
---------------------------------------
0. **Equivalence** (owner rule 2026-10-01, `canonical-identifiers`) — for an
   identifier campo (cpf / rg / rg_orgao_expedidor / cnpj / cep), two readings
   the registry PROVES are the same identifier (`30128742` — a CNH's RG
   without its check digit — and `30.128.742-9`; `412.954.238-98` and
   `41295423898`) are not a disagreement at all: `vencedor='atual'`, the
   on-file provenance is untouched, the stored form is canonicalised by
   its own write path / the backfill — never by stamping the other source's
   provenance over it.
0b. **Refinement** (2026-10-03, P3/P4 test loop) — an órgão expedidor
   reading that is the other one plus the UF it lacked (`SSP` from a bank
   form vs `SSP/SP` from the CNH) is the same órgão, stated completely:
   the complete one is kept (`identificadores.orgao_refinamento`).
1a. **Type routing** — a reading that is a VALID instance of ANOTHER type
   (a CPF `297.556.088-50` in the RG field) is not this campo's value and
   loses to one that is not misrouted. The one exception is the CIN, whose
   identity number IS the holder's own CPF (`cpf_proprio`).
1. **Validators** — an invalid side loses outright, whatever its tier: a CPF
   whose check digits fail, a date that does not parse, or an RG whose SP
   check digit fails (`15.668.564-3` vs `16.669.554-3` — an OCR digit
   swap; the one that verifies wins). A reading that merely LACKS its RG
   check digit is completed arithmetically by the registry
   (`identificador.ler`) — it is equivalent, not a loser.
1b. **Live evidence** (`EvidenciaViva`, 2026-09-29 second pass) — a side
   whose OWN document no longer asserts it (deleted, or re-read to a
   different value) has been RETRACTED and loses to a side that has not;
   the conflict row merely remembers it. Positive evidence only: a value
   with no document behind it (manual, derived, legacy) is never judged
   retracted.
   Measured on the prod queue: 897's on-file name came from a CNH pass whose
   re-read no longer carries a name at all — and the surviving Serasa
   reading is the one the signed contract used. A two-person document (a
   certidão de casamento) asserts a PER-PERSON fact only through the spouse
   entry attributed to this person (`titular`, or a CPF match) — its flat
   single-person columns name nobody in particular (882's certidão "RG"
   disagreed with the CNH; the contract carries the CNH's).
2. **Corroboration** — a value independently proposed by TWO OR MORE distinct
   sources outranks a single dissenting one, regardless of either side's own
   tier. `historico` carries every OTHER (valor, origem) this (owner, campo)
   has ever seen proposed (`campo_conflitos.historico_valores`), and
   `EvidenciaViva.afirmacoes` every value a live document asserts right now
   — a value merely APPLIED without a conflict (so never "proposed") is
   still a source that agrees.
3. **Source tier** — the higher measured `PRECISAO` wins. Equal, unmeasured,
   or too-thin-to-trust precision on both sides is NOT a tier decision.
Across every step: **a human-entered or human-confirmed value is never
   overridden** (`atual_humano=True`, owner rule 2026-10-03) — a verdict
   for the proposed side comes back as `requer_humano` instead; a verdict
   that KEEPS the human's value still stands. The one exception is a value
   PROVEN invalid (`REGRAS_PROVA_OBJETIVA`: failing check digit, another
   type's identifier) — pinned behaviour since 2026-09-29.
4. Anything still standing needs a human — same posture as today
   (`requer_humano=True`), never a coin flip.

Owner rules beyond this generic order (the married-name adoption rule,
`identidade_extracao_service._nome_anterior_confirma_adocao`; the proof-of-
address holder+recency rule, `identidade_extracao_service.
aplicar_endereco_ao_cliente`; the cross-party identity check,
`decisao_outra_pessoa`, R4 below) stay with their own callers — they need
field-specific context (`estado_civil`, `nomes_anteriores`, a document's
holder, every OTHER party's own identity fields) this generic resolver has
no business carrying. They run BEFORE this resolver is ever consulted,
exactly as they do today; this module only covers what falls through to the
generic `else:` conflict branch.

R1-R5 (owner directive, 2026-09-30, live-test evidence — 5 historical deals
re-run on prod): a rule can settle every pending conflict a live re-run
surfaced, none of it needing a human.
R1 — re-resolution on new evidence: `identidade_extracao_service.
revalidar_negociacao` re-runs `backfill_resolver_conflitos_pendentes` over
this cliente AND every other party of the same `atendimento`(s) after every
extraction, so a name that lands on ONE person's card can settle a PENDING
conflict sitting on ANOTHER's (a bill-holder check with nothing to compare
against yet).
R2 — address fill on empty address: `_decidir_endereco_pendente` no longer
treats an empty on-file address as unresolvable-forever
(`ignorado_composto`); the holder-tier resolver (`_decisao_endereco_por_
titular`) now also recognises another ATENDIMENTO PARTY as a verified
holder (`_titular_e_parte_ou_conjuge`, extended), and auto-rejects a
genuinely unrelated holder when the cliente already holds an address from
their own document.
R3 — household propagation: `identidade_extracao_service.
propagar_endereco_domicilio` fills a spouse's empty address from the
other's own-document address, tagged `origem="conjuge_domicilio"` — a tier
BELOW any own document (never overwrites one), and un-fills itself the
moment the source no longer qualifies (retracted document, address cleared).
R5 — two-person documents: the unattributed-flat-field withholding
(`identidade_extracao_service._processar`) now covers every
`CAMPOS_POR_PESSOA` field, not only `cpf` — an unresolved certidão
attribution withholds ALL of a two-person document's per-person facts, not
just the one that was measured first.

WHAT NEVER REACHES THIS MODULE AT ALL
--------------------------------------
A `leitura_comprometida` read (owner rule: low-legibility docs always need a
human) is withheld from `clientes` at `extrair_identidade`'s own gate
(`pode_persistir=False` for every field on that read) BEFORE
`aplicar_campos_ao_cliente` ever compares it against what is on file — it
never becomes a `valor_proposto` here, so this module never needs (and must
never grow) a `leitura_comprometida` parameter of its own. See
`identidade_extracao_service.TestLeituraComprometidaWithholdsEverything`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional, Sequence

from noctusai_lib.integrations.documents.cnpj import is_valid as _cnpj_valido
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_valido
from noctusai_lib.integrations.documents.address import (
    normalizar_logradouro as _seed_normalizar_logradouro,
)
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.rg import rg_shape_valido
from noctusai_lib.primitives import identificador as _ident

from app.services import identificadores as _ids

#: Precision the validation gate requires to skip a human click entirely
#: (BUILD item 2) — `n >= N_MINIMO_VALIDACAO` guards against a 2/2 or 1/1
#: cell (real in the evidence table above) reading as confidently as a 19/19
#: one; both numbers are the owner's own thresholds ("≥95% with n≥10").
PRECISAO_VALIDACAO_AUTOMATICA = 0.95
N_MINIMO_VALIDACAO = 10

#: A value independently proposed by this many DISTINCT origins outranks a
#: single dissenting one (BUILD item 1, "corroboration").
CORROBORACAO_MINIMA = 2


@dataclass(frozen=True)
class Precisao:
    """One `PRECISAO[campo][origem]` cell — the ratio AND its sample size,
    kept together so a caller can never read "1.0" without also seeing
    whether that was 19 contracts or 1."""

    precisao: float
    n: int


#: The evidence table itself — see the module docstring. Keyed by the SAME
#: strings `identidade_extracao_service` already uses for `campo.item_key`
#: and for `origem` (a `cliente_documentos.tipo_documento`, or
#: `crednet_service`'s `"serasa_crednet"`, or `qualificacao_service.
#: ORIGEM_MATRICULA == "matricula"`) — no re-mapping needed at any call site.
PRECISAO: dict[str, dict[str, Precisao]] = {
    "nome_oficial": {
        "cnh": Precisao(1.0, 19),
        "rg": Precisao(1.0, 2),
        "serasa_crednet": Precisao(1.0, 12),
        "matricula": Precisao(0.84, 19),
        "certidao_casamento": Precisao(0.60, 5),
    },
    "cpf": {
        "cnh": Precisao(1.0, 19),
        "rg": Precisao(1.0, 1),
        "serasa_crednet": Precisao(1.0, 12),
        "certidao_casamento": Precisao(0.67, 3),
    },
    "rg": {
        # The RG identity CARD — same string as the `cpf`/`rg_orgao_
        # expedidor` cells below, coincidentally also the campo's own name.
        "rg": Precisao(1.0, 2),
        "cnh": Precisao(0.39, 18),
        "matricula": Precisao(0.38, 16),
    },
    "rg_orgao_expedidor": {
        "matricula": Precisao(1.0, 14),
        "cnh": Precisao(0.95, 20),
    },
    "genero": {
        "cnh": Precisao(1.0, 11),
        "matricula": Precisao(0.95, 19),
        "certidao_casamento": Precisao(0.75, 4),
    },
    "nacionalidade": {
        "cnh": Precisao(1.0, 17),
        "certidao_casamento": Precisao(1.0, 6),
        "certidao_nascimento": Precisao(1.0, 6),
        "matricula": Precisao(1.0, 19),
    },
    "estado_civil": {
        "certidao_casamento": Precisao(1.0, 13),
        "matricula": Precisao(1.0, 3),
    },
    "regime_bens": {
        "certidao_casamento": Precisao(1.0, 12),
    },
    "profissao": {
        "matricula": Precisao(1.0, 3),
    },
}

# 2026-10-05 — divergence-email study (137 deduped records / 155 emails,
# private dataset; precision of a source AS THE PROPOSED SIDE =
# right / (right + wrong), `lado_correto` per fonte x campo; 'equal'
# (normalisation-only) and '?' (undecided) rows excluded):
#   endereco  comprovante_endereco 14 right / 17 decided -> 0.82 (n=17)
#             ficha_cadastral       8 right /  9 decided -> 0.89 (n=9)
#   rg_orgao_expedidor ficha_cadastral 2/2 (n=2, thin)
#   nome_oficial       ficha_cadastral 1/2 (n=2, thin)
#   certidao_casamento rg 0/4 and data_nascimento 0/3 — the flat
#             single-person columns of a two-person document name nobody
#             (same finding as step 1b's attribution rule).
#   cin: no identity-field rows in the dataset; by CONVENTION it mirrors the
#   RG card cell (the CIN IS the national RG replacement), same n so it can
#   never auto-validate on tier alone.
# Existing signed-contract cells above are never overwritten by this study.
_PRECISAO_ESTUDO_2026_10_05: dict[str, dict[str, Precisao]] = {
    "endereco": {
        "ficha_cadastral": Precisao(0.89, 9),
        "comprovante_endereco": Precisao(0.82, 17),
    },
    "rg_orgao_expedidor": {"ficha_cadastral": Precisao(1.0, 2)},
    "nome_oficial": {
        "ficha_cadastral": Precisao(0.5, 2),
        "cin": Precisao(1.0, 2),
    },
    "rg": {
        "certidao_casamento": Precisao(0.0, 4),
        "cin": Precisao(1.0, 2),
    },
    "data_nascimento": {"certidao_casamento": Precisao(0.0, 3)},
    "cpf": {"cin": Precisao(1.0, 1)},
}
for _campo, _cells in _PRECISAO_ESTUDO_2026_10_05.items():
    for _origem, _cell in _cells.items():
        PRECISAO.setdefault(_campo, {}).setdefault(_origem, _cell)


def precisao_de(campo: str, origem: Optional[str]) -> Optional[Precisao]:
    """The measured `(precisao, n)` for this (campo, origem), or `None` when
    unmeasured — an unknown source is never silently treated as low-tier
    (0.0) nor as trusted (1.0); it simply cannot win on TIER alone."""
    if not origem:
        return None
    return PRECISAO.get(campo, {}).get(origem)


def valido_para_contrato_sem_revisao(
    campo: str, origem: Optional[str], *, corroborado: bool = False
) -> bool:
    """BUILD item 2 — may this machine value feed
    `validacao_extracao.exigir_sem_pendentes` without a human click?

    `corroborado=True` (≥2 independent documents already agree — see
    `CORROBORACAO_MINIMA`) always qualifies, whatever the source's own tier.
    Otherwise: `precisao >= PRECISAO_VALIDACAO_AUTOMATICA` AND
    `n >= N_MINIMO_VALIDACAO` — the owner's own two-part bar, so a thin
    2/2 cell (real in the evidence table) never auto-validates on tier alone.
    """
    if corroborado:
        return True
    p = precisao_de(campo, origem)
    return bool(
        p is not None
        and p.precisao >= PRECISAO_VALIDACAO_AUTOMATICA
        and p.n >= N_MINIMO_VALIDACAO
    )


# ─── Validators (resolution step 1) ─────────────────────────────────────────


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _data_valida(valor: Any) -> Optional[bool]:
    texto = str(valor)[:10]
    try:
        date.fromisoformat(texto)
    except (ValueError, TypeError):
        return False
    return True


def _validar(
    campo: str, valor: Any, *, uf: Optional[str] = None
) -> Optional[bool]:
    """`True`/`False` when this campo carries a self-verifying shape (a
    check-digit document number, a date), `None` when there is nothing to
    validate (an empty value, or a campo/valor this function has no verifier
    for) — `None` never counts as either a pass or a fail in
    `resolver_divergencia`.

    `rg`: the registry's reading decides (`identificador.ler`) — an SP RG
    whose check digit fails is `False`, one whose digit verifies is `True`,
    one WITHOUT a digit (completed arithmetically) is `None`: absence of
    the digit is not an error, only a wrong one is. `uf` keeps an RG from a
    state with no evidenced mask out of the SP check."""
    if _vazio(valor):
        return None
    texto = str(valor)
    if campo == "cpf":
        return _cpf_valido(texto)
    if campo == "cnpj":
        return _cnpj_valido(texto)
    if campo == "rg":
        leitura = _ident.ler("rg", texto, uf=uf)
        if leitura.dv_ok is False:
            return False
        if leitura.cabe and leitura.dv_ok:
            return True
        return None
    if campo in ("data_nascimento", "data_casamento"):
        return _data_valida(texto)
    return None


def _tipo_trocado(
    campo: str, valor: Any, *, uf: Optional[str], cpf_proprio: Any
) -> Optional[str]:
    """The OTHER identifier type `valor` is a valid instance of when it sits
    in the wrong campo (a CPF in the RG field), else None. The CIN exception:
    an RG equal to its holder's own CPF is a legitimate RG
    (`identificadores.para_gravar`)."""
    tipo = _ids.TIPO_POR_CAMPO.get(campo)
    if tipo is None or _vazio(valor):
        return None
    g = _ids.para_gravar(tipo, valor, uf=uf, cpf_proprio=cpf_proprio)
    return g.tipo_detectado if g.rejeitado_por_tipo else None


# ─── Address logradouro normalisation (owner rule: kill format-only noise) ──

#: `AV/AVENIDA, R/RUA, AL/ALAMEDA, EST/ESTRADA, TV/TRAVESSA, ROD/RODOVIA,
#: PC/PRAÇA` (owner directive, 2026-09-29) — every abbreviated AND full form
#: maps to ONE canonical token, so a `logradouro` compare never opens a
#: conflict over spelling alone. Measured against the evidence: logradouro
#: 4/9, número 6/9, cidade 4/6, CEP 5/8 — "partly abbreviation/format
#: differences (AV vs AVENIDA etc.)".
_LOGRADOURO_CANONICO: dict[str, str] = {
    "AV": "AVENIDA", "AVENIDA": "AVENIDA",
    "R": "RUA", "RUA": "RUA",
    "AL": "ALAMEDA", "ALAMEDA": "ALAMEDA",
    "EST": "ESTRADA", "ESTRADA": "ESTRADA",
    "TV": "TRAVESSA", "TRAVESSA": "TRAVESSA",
    "ROD": "RODOVIA", "RODOVIA": "RODOVIA",
    "PC": "PRACA", "PRACA": "PRACA", "PRAÇA": "PRACA",
}


_CONECTORES = frozenset({"DE", "DA", "DO", "DAS", "DOS", "E"})
_TIPOS_LOGRADOURO = frozenset(_LOGRADOURO_CANONICO.values())


def _sem_acento_upper(valor: str) -> str:
    decomposed = unicodedata.normalize("NFKD", valor)
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.upper()).strip()


def normalizar_logradouro(valor: Optional[str]) -> str:
    """Comparison string for a logradouro: the seed's
    `address.normalizar_logradouro` (doubled-type collapse, type and
    PROF/PRF abbreviation expansion, connector case) folded to accent-free
    upper case — `"AV Paulista"` == `"Avenida Paulista"`. Connectors are kept
    here; `chave_logradouro` drops them and the type for the loosest compare."""
    if not valor or not valor.strip():
        return ""
    return _sem_acento_upper(_seed_normalizar_logradouro(valor) or valor)


def chave_logradouro(valor: Optional[str]) -> str:
    """The street NAME alone — type and connectors stripped. A CEP lookup says
    `Estrada X`, the document says `Rua X`: same street, so the same key."""
    tokens = normalizar_logradouro(valor).replace(",", " ").split()
    if tokens and (tokens[0].rstrip(".") in _TIPOS_LOGRADOURO):
        tokens = tokens[1:]
    return " ".join(t for t in tokens if t not in _CONECTORES)


def logradouros_equivalentes(a: Optional[str], b: Optional[str]) -> bool:
    """Two logradouro strings that differ only by street type, doubled type,
    connectors, accents/case or PROF=PRF are the same street."""
    ka, kb = chave_logradouro(a), chave_logradouro(b)
    return bool(ka) and ka == kb


_PARTICULAS_NOME = frozenset({"DE", "DA", "DO", "DAS", "DOS", "E"})


def nomes_equivalentes(a: Any, b: Any) -> bool:
    """Same person name up to accents, case, spacing and name particles."""
    if _vazio(a) or _vazio(b):
        return False

    def chave(v: Any) -> tuple[str, ...]:
        return tuple(
            t for t in re.split(r"[^A-Z]+", _sem_acento_upper(str(v)))
            if t and t not in _PARTICULAS_NOME
        )

    return bool(chave(a)) and chave(a) == chave(b)


_RNE_RG = re.compile(r"^[A-Z]-?(\d{3})\.?(\d{3})-?[A-Z0-9]$")


def _rne_digitos(valor: Any) -> Optional[str]:
    m = _RNE_RG.match(_sem_acento_upper(str(valor)).replace(" ", ""))
    return f"{m.group(1)}{m.group(2)}" if m else None


def rg_rne_equivalente(a: Any, b: Any) -> bool:
    """An RNE RG shaped `X-###.###-X` carries the same number as the bare
    `######` the other source prints."""
    if _vazio(a) or _vazio(b) or not (rg_shape_valido(str(a)) and rg_shape_valido(str(b))):
        return False
    da, db = _rne_digitos(a), _rne_digitos(b)
    if da is not None and re.fullmatch(r"\d{6}", only_digits(str(b)) or "") and not re.search(r"[A-Za-z]", str(b)):
        return da == only_digits(str(b))
    if db is not None and re.fullmatch(r"\d{6}", only_digits(str(a)) or "") and not re.search(r"[A-Za-z]", str(a)):
        return db == only_digits(str(a))
    return da is not None and da == db


# ─── Confidence + attestation + plausibility (steps C / A / P) ─────────────

#: Confidence labels that must never contest a filled value.
CONFIANCAS_BAIXAS = frozenset({"baixa", "nenhuma", "desconhecida"})


#: A stored read at these confidences (or a human value) may hold against a
#: weak proposal.
CONFIANCAS_FIRMES = frozenset({"media", "alta"})


def _atual_firme(atual_humano: bool, confianca_atual: Optional[str]) -> bool:
    return bool(atual_humano) or (
        isinstance(confianca_atual, str)
        and _sem_acento_upper(confianca_atual).lower() in CONFIANCAS_FIRMES
    )


def _leitura_instavel(
    campo: str, proposto: Any, leituras: Sequence[Any],
    mesmo_valor: Callable[[str, Any, Any], bool],
) -> bool:
    return any(not _vazio(v) and not mesmo_valor(campo, v, proposto) for v in leituras)


def confianca_baixa(confianca: Any) -> bool:
    return isinstance(confianca, str) and _sem_acento_upper(confianca).lower() in CONFIANCAS_BAIXAS


#: `(origem, campo)` pairs where the source cannot ATTEST the field, so its
#: reading never contests a filled value (class "source can't attest").
FONTE_NAO_ATESTA: frozenset[tuple[str, str]] = frozenset({
    ("cin", "estado_civil"),
    ("cnh", "nacionalidade"),
    # a certidão de nascimento without an averbação only INFERS "solteiro".
    ("certidao_nascimento", "estado_civil"),
    # matrícula's cadastro is the old-format one; the municipal source wins.
    ("matricula", "prefeitura_cadastro_imobiliario"),
})

#: Órgãos expedidores that exist (leading token before the UF). An OCR word
#: such as SERRA is not one.
ORGAOS_EXPEDIDORES_CONHECIDOS = frozenset({
    "SSP", "SJS", "SDS", "SESP", "SEJUSP", "SEDS", "SJTC", "SSPDS", "DETRAN",
    "PC", "PCI", "PM", "PF", "DPF", "IFP", "IGP", "DGPC", "IIRGD", "IML",
    "ITEP", "POLITEC", "SPTC", "DIC", "DGPT", "MAER", "MEX", "MB", "MD",
    "CNIG", "DPMAF", "DELEMIG", "DICRIM", "CGPI", "SESEG", "SEJUS", "SDSP",
    "CBM", "CBMERJ", "CREA", "OAB", "CRM", "CRC", "CRQ", "COREN", "DRT",
})
_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

IDADE_MINIMA_NEGOCIO = 18


def orgao_conhecido(valor: Any) -> Optional[bool]:
    """True/False when the leading token is/isn't a known órgão, None if empty."""
    if _vazio(valor):
        return None
    tokens = [t for t in re.split(r"[^A-Z]+", _sem_acento_upper(str(valor))) if t]
    tokens = [t for t in tokens if t not in _UFS or len(tokens) == 1]
    if not tokens:
        return None
    return tokens[0] in ORGAOS_EXPEDIDORES_CONHECIDOS


def _menor_de_idade(valor: Any, referencia: Optional[date]) -> bool:
    try:
        nasc = date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return False
    ref = referencia or date.today()
    anos = ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))
    return anos < IDADE_MINIMA_NEGOCIO or nasc > ref


def _razao_social_defeituosa(valor: Any, outro: Any) -> bool:
    if _vazio(valor):
        return False
    texto = str(valor).strip()
    if "\u26a0" in texto or texto.endswith(("...", "\u2026")):
        return True
    if _vazio(outro):
        return False
    a, b = _sem_acento_upper(texto), _sem_acento_upper(str(outro))
    return len(a) < len(b) and b.startswith(a)


def _implausivel(
    campo: str, valor: Any, outro: Any, *, referencia: Optional[date]
) -> Optional[str]:
    """Why `valor` is OBJECTIVELY not a plausible value of `campo` (age under
    18 at the deal, unknown órgão, a damaged/truncated razão social), else
    None. Check-digit failures stay with `_validar`."""
    if _vazio(valor):
        return None
    if campo == "data_nascimento" and _menor_de_idade(valor, referencia):
        return f"idade inferior a {IDADE_MINIMA_NEGOCIO} anos na data do negócio"
    if campo == "rg_orgao_expedidor" and orgao_conhecido(valor) is False:
        return "órgão expedidor fora da lista de órgãos conhecidos"
    if campo == "razao_social" and _razao_social_defeituosa(valor, outro):
        return "razão social truncada ou com marcador de leitura (⚠)"
    return None


# ─── The generic resolver (resolution steps 1-3; step 4 is "ask a human") ──


@dataclass(frozen=True)
class Decisao:
    """One resolver verdict. `vencedor` is `None` iff `requer_humano` — never
    both a verdict AND a request for a human, so a caller can branch on
    `requer_humano` alone and never has to special-case a `None` winner."""

    vencedor: Optional[str]  # 'atual' | 'proposto' | None
    regra: str
    motivo: str
    requer_humano: bool
    #: Pre-selection for the human gate: set only when `requer_humano` and an
    #: objective plausibility proof (`plausibilidade`) favours that side —
    #: the UI may pre-pick it, nothing is applied.
    sugerido: Optional[str] = None

    @property
    def corroborado(self) -> bool:
        return self.regra == "corroboracao"


#: Documents that describe TWO people. Their per-person facts are only
#: attributable through the spouse entry that is this person.
DOCUMENTOS_DUAS_PESSOAS = frozenset({"certidao_casamento"})

#: Facts that differ between two spouses — the ones a two-person document
#: cannot assert without attribution. Couple-level facts (estado_civil,
#: regime_bens, data_casamento) are the same for both and stay out.
#: `nacionalidade` stays out too: measured 6/6 from the certidão's flat
#: reading, because both nubentes are almost always of one nationality.
CAMPOS_POR_PESSOA = frozenset(
    {"nome_oficial", "cpf", "rg", "rg_orgao_expedidor", "data_nascimento", "genero", "profissao"}
)


@dataclass(frozen=True)
class EvidenciaViva:
    """What this person's LIVE documents say about one campo right now.

    `afirmacoes`: `(valor, tipo_documento)` per live document, attribution
    already applied by the caller (see `DOCUMENTOS_DUAS_PESSOAS`) — extra
    corroboration for step 2.
    `atual_sustentado` / `proposto_sustentado`: does the SPECIFIC document
    behind each side still assert it? `False` only on positive evidence —
    that document was deleted, now reads a different value, or is a
    two-person document with no entry attributed to this person. `None`
    when the caller cannot tell (no document behind the value: a manual
    entry, a derived value, legacy data, or the reading being applied at
    this very moment) — `None` never counts as retracted."""

    afirmacoes: tuple[tuple[Any, str], ...] = ()
    atual_sustentado: Optional[bool] = None
    proposto_sustentado: Optional[bool] = None


def _decisao(vencedor: str, regra: str, motivo: str) -> Decisao:
    return Decisao(vencedor=vencedor, regra=regra, motivo=motivo, requer_humano=False)


_HUMANO = Decisao(
    vencedor=None, regra="requer_humano",
    motivo="Nenhum validador, corroboração ou diferença de precisão medida "
           "separa as duas leituras — decisão humana necessária.",
    requer_humano=True,
)


#: Rules whose verdict PROVES the on-file value is not a valid value of this
#: campo at all — its check digit fails (`validador`), or it is a valid
#: identifier of ANOTHER type (`tipo_detectado`). These still replace a
#: hand-typed value (pinned since 2026-09-29: a typed `111.111.111-11` loses
#: to a CNH's valid CPF); every other rule's preference for the proposed
#: side yields to a human value (`atual_humano`).
REGRAS_PROVA_OBJETIVA = frozenset({"validador", "tipo_detectado"})

_HUMANO_PROTEGIDO_MOTIVO = (
    "o valor em registro foi digitado ou confirmado por uma pessoa — nunca "
    "sobrescrito automaticamente; a regra {regra!r} preferiria o proposto."
)


def _protegido(regra: str) -> Decisao:
    return Decisao(
        vencedor=None, regra="valor_humano",
        motivo=_HUMANO_PROTEGIDO_MOTIVO.format(regra=regra), requer_humano=True,
    )


#: R4 (owner directive, 2026-09-30, live-test evidence): the three fields a
#: document can print that belong to exactly ONE person and to nobody else
#: in the same negotiation. `endereco` is deliberately excluded — a shared
#: household address legitimately belongs to more than one party (see
#: `identidade_extracao_service.propagar_endereco_domicilio`), so "another
#: party has this too" is not evidence of misfiling there the way it is for
#: an identity number or a name.
CAMPOS_IDENTIDADE_EXCLUSIVA = frozenset({"nome_oficial", "cpf", "rg"})


def decisao_outra_pessoa(
    campo: str,
    valor_proposto: Any,
    *,
    mesmo_valor: Callable[[str, Any, Any], bool],
    valores_outras_pessoas: Sequence[tuple[Any, str]],
) -> Optional[Decisao]:
    """R4 — a proposed identity value that equals, after normalisation,
    another PARTY's (or their attributed spouse's) value in the same
    `atendimento` is not this person's fact at all: the document was
    misfiled onto the wrong card, or is genuinely someone else's. Returns an
    auto-REJECT `Decisao` (`vencedor='atual'` — never apply the proposal,
    whatever is or isn't already on file) naming whose value it is, or
    `None` when nothing in `valores_outras_pessoas` matches (the ordinary
    case — proceed to the generic resolver/fill-empty path as before).

    `campo` outside `CAMPOS_IDENTIDADE_EXCLUSIVA`, or an empty
    `valor_proposto`, is always `None` — this rule has nothing to say about
    an address or a couple-level fact, and an empty proposal was never
    going anywhere regardless.

    `valores_outras_pessoas` is `[(valor, papel), ...]` — the caller's own
    job (`identidade_extracao_service._valores_outras_pessoas`) to gather:
    which OTHER clientes count as "another party" (co-parties of the same
    `atendimento`, an attributed certidão spouse) and what label to show
    for each (`papel` — "comprador", "vendedor", "cônjuge", ...).
    """
    if campo not in CAMPOS_IDENTIDADE_EXCLUSIVA or _vazio(valor_proposto):
        return None
    for valor, papel in valores_outras_pessoas:
        if _vazio(valor):
            continue
        if mesmo_valor(campo, valor, valor_proposto):
            return _decisao(
                "atual", "outra_pessoa",
                f"{campo}: o valor pertence a {papel} desta negociação — "
                f"documento provavelmente arquivado na pessoa errada.",
            )
    return None


def resolver_divergencia(
    campo: str,
    *,
    valor_atual: Any,
    origem_atual: Optional[str],
    valor_proposto: Any,
    origem_proposto: str,
    mesmo_valor: Callable[[str, Any, Any], bool],
    historico: Sequence[tuple[Any, Optional[str]]] = (),
    evidencia: Optional[EvidenciaViva] = None,
    uf: Optional[str] = None,
    cpf_proprio: Any = None,
    atual_humano: bool = False,
    confianca_proposta: Optional[str] = None,
    leituras_mesmo_documento: Sequence[Any] = (),
    proposto_inferido: bool = False,
    data_negocio: Optional[date] = None,
    confianca_atual: Optional[str] = None,
) -> Decisao:
    """Decide `'atual'` vs `'proposto'` for one disagreeing (campo, valores)
    pair, or admit a human is needed. Pure — no I/O, no DB. `mesmo_valor` is
    the caller's own field-aware fact-equality (`identidade_extracao_
    service._mesmo_valor`), injected rather than imported, so this module
    stays free of a circular import back onto its own caller — the same DI
    shape `campo_conflitos.notificar_conflitos` already uses for
    `notify_one`.

    `historico` is every OTHER `(valor, origem)` this (owner, campo) has
    ever seen proposed (`campo_conflitos.historico_valores`) — the
    corroboration evidence. Entries that agree with neither `valor_atual`
    nor `valor_proposto` are a third, different value and are ignored here
    (this resolver decides between the two CANDIDATES in front of it, not a
    three-way vote).

    `evidencia` (optional) is what the person's live documents assert now —
    step 1b's retraction check and extra corroboration. Omitted, the
    resolver behaves exactly as before it existed.

    `uf` (the UF of the person's órgão expedidor) and `cpf_proprio` (the
    person's own CPF) are the identifier registry's reading context — see
    `_validar` / `_tipo_trocado`. Both optional; omitted, an RG is read with
    the SP mask and a CPF in the RG field is never exempt.

    `atual_humano` — the on-file value was typed (`origem='manual'`) or
    confirmed (`confirmado_por` set) by a person: any verdict for the
    PROPOSED side is turned into `requer_humano` (regra `valor_humano`).

    `confianca_proposta` — the proposed reading's confidence; baixa / nenhuma
    / desconhecida never contests a filled value. `leituras_mesmo_documento`
    — the other values the SAME document produced across reads: when they
    differ from the proposal the reading is unstable and counts as low
    confidence. `proposto_inferido` — the proposal is an inference, not an
    attestation (`ROTULO_SOLTEIRO_INFERIDO`). `data_negocio` — reference date
    for the age plausibility proof (default today). `confianca_atual` — the
    stored value's own read confidence; unknown (None) is the conservative
    path: a weak proposal against a stored value that is neither human nor
    read with real confidence needs a human.
    """
    decisao = _resolver(
        campo,
        valor_atual=valor_atual, origem_atual=origem_atual,
        valor_proposto=valor_proposto, origem_proposto=origem_proposto,
        mesmo_valor=mesmo_valor, historico=historico, evidencia=evidencia,
        uf=uf, cpf_proprio=cpf_proprio,
        confianca_proposta=confianca_proposta,
        leituras_mesmo_documento=leituras_mesmo_documento,
        proposto_inferido=proposto_inferido, data_negocio=data_negocio,
        confianca_atual=confianca_atual, atual_humano=atual_humano,
    )
    if (
        decisao.vencedor == "proposto"
        and decisao.regra in ("tier", "corroboracao", "retratado")
        and not _vazio(valor_atual)
        and (confianca_baixa(confianca_proposta) or _leitura_instavel(
            campo, valor_proposto, leituras_mesmo_documento, mesmo_valor))
        and not _atual_firme(atual_humano, confianca_atual)
    ):
        # a weak proposal never wins on soft evidence over a weak/unknown
        # stored value either — a human decides.
        return _HUMANO
    if (
        atual_humano
        and decisao.vencedor == "proposto"
        and decisao.regra not in REGRAS_PROVA_OBJETIVA
    ):
        return _protegido(decisao.regra)
    return decisao


def _resolver(
    campo: str,
    *,
    valor_atual: Any,
    origem_atual: Optional[str],
    valor_proposto: Any,
    origem_proposto: str,
    mesmo_valor: Callable[[str, Any, Any], bool],
    historico: Sequence[tuple[Any, Optional[str]]],
    evidencia: Optional[EvidenciaViva],
    uf: Optional[str],
    cpf_proprio: Any,
    confianca_proposta: Optional[str] = None,
    leituras_mesmo_documento: Sequence[Any] = (),
    proposto_inferido: bool = False,
    data_negocio: Optional[date] = None,
    confianca_atual: Optional[str] = None,
    atual_humano: bool = False,
) -> Decisao:
    """`resolver_divergencia`'s steps 0-4, before the human guard."""
    # 0. Equivalence — format-only differences are not a disagreement.
    tipo_id = _ids.TIPO_POR_CAMPO.get(campo)
    if (
        tipo_id is not None
        and not _vazio(valor_atual)
        and not _vazio(valor_proposto)
        and _ids.iguais(
            tipo_id, valor_atual, valor_proposto,
            **({"uf": uf} if tipo_id == "rg" and uf else {}),
        )
    ):
        return _decisao(
            "atual", "equivalencia",
            f"{campo}: as duas leituras ({origem_atual} e {origem_proposto}) "
            f"são o mesmo identificador, só muda a formatação ou o dígito "
            f"verificador ausente — nada a decidir.",
        )

    # 0b. Refinement — the same órgão, one reading missing only its UF.
    if campo == "rg_orgao_expedidor":
        refinado = _ids.orgao_refinamento(valor_atual, valor_proposto)
        if refinado is not None:
            vencedor = "atual" if refinado == _ids.MAIS_COMPLETO_A else "proposto"
            completo = valor_atual if vencedor == "atual" else valor_proposto
            return _decisao(
                vencedor, "refinamento",
                f"{campo}: as duas leituras ({origem_atual} e {origem_proposto}) "
                f"nomeiam o mesmo órgão; só {completo!r} traz a UF — mantida a "
                f"leitura completa.",
            )

    # 0c. Normalisation-only differences (logradouro type/connectors, RNE
    # RG shape, name particles) are equal, not a disagreement.
    if not _vazio(valor_atual) and not _vazio(valor_proposto):
        equivalente = False
        if campo in ("endereco", "logradouro"):
            equivalente = logradouros_equivalentes(str(valor_atual), str(valor_proposto))
        elif campo == "rg":
            equivalente = rg_rne_equivalente(valor_atual, valor_proposto)
        elif campo == "nome_oficial":
            equivalente = nomes_equivalentes(valor_atual, valor_proposto)
        if equivalente:
            return _decisao(
                "atual", "equivalencia",
                f"{campo}: as duas leituras ({origem_atual} e {origem_proposto}) "
                f"diferem só por normalização (tipo/conectores/partículas/"
                f"formato) — nada a decidir.",
            )

    if not _vazio(valor_atual):
        # C. Confidence — a weak or unstable reading never contests a filled
        # value; it is recorded, no human conflict.
        instavel = _leitura_instavel(
            campo, valor_proposto, leituras_mesmo_documento, mesmo_valor)
        if confianca_baixa(confianca_proposta) or instavel:
            motivo = (
                "o mesmo documento deu valores diferentes entre leituras"
                if instavel and not confianca_baixa(confianca_proposta)
                else f"confiança {confianca_proposta or 'baixa'} na leitura proposta"
            )
            if _atual_firme(atual_humano, confianca_atual):
                return _decisao(
                    "atual", "confianca_baixa",
                    f"{campo}: {motivo} ({origem_proposto}) — o valor em "
                    f"registro é humano ou foi lido com confiança firme; "
                    f"registrada sem conflito.",
                )
            # Stored side is itself weak/unknown: do NOT short-circuit and do
            # NOT entrench it — fall through to validators / tier, which may
            # still decide on evidence; otherwise the generic human verdict.
        # A. Attestation — a source that cannot attest this field (or only
        # infers it) never contests a filled value.
        if proposto_inferido or (origem_proposto, campo) in FONTE_NAO_ATESTA:
            return _decisao(
                "atual", "fonte_nao_atesta",
                f"{campo}: {origem_proposto!r} não atesta este campo (valor "
                f"inferido ou fora do que o documento comprova) — não contesta "
                f"o valor em registro.",
            )

    # 1a. Type routing — a valid identifier of ANOTHER type is not this
    # campo's value.
    tipo_atual = _tipo_trocado(campo, valor_atual, uf=uf, cpf_proprio=cpf_proprio)
    tipo_proposto = _tipo_trocado(campo, valor_proposto, uf=uf, cpf_proprio=cpf_proprio)
    if tipo_atual and not tipo_proposto:
        return _decisao(
            "proposto", "tipo_detectado",
            f"{campo}: o valor em registro ({origem_atual}) é um "
            f"{tipo_atual.upper()} válido, não um {campo.upper()}; o proposto "
            f"({origem_proposto}) não está no campo errado.",
        )
    if tipo_proposto and not tipo_atual:
        return _decisao(
            "atual", "tipo_detectado",
            f"{campo}: o valor proposto ({origem_proposto}) é um "
            f"{tipo_proposto.upper()} válido, não um {campo.upper()}; o em "
            f"registro ({origem_atual}) não está no campo errado.",
        )

    # 1. Validators — an invalid side loses outright, whatever its tier.
    ok_atual = _validar(campo, valor_atual, uf=uf)
    ok_proposto = _validar(campo, valor_proposto, uf=uf)
    if ok_atual is False and ok_proposto is not False:
        return _decisao(
            "proposto", "validador",
            f"{campo}: o valor em registro ({origem_atual}) falha o dígito "
            f"verificador; o proposto ({origem_proposto}) verifica.",
        )
    if ok_proposto is False and ok_atual is not False:
        return _decisao(
            "atual", "validador",
            f"{campo}: o valor proposto ({origem_proposto}) falha o dígito "
            f"verificador; o em registro ({origem_atual}) verifica.",
        )

    # 1c. Plausibility — objective proof one side is not a valid value.
    pl_atual = _implausivel(campo, valor_atual, valor_proposto, referencia=data_negocio)
    pl_proposto = _implausivel(campo, valor_proposto, valor_atual, referencia=data_negocio)
    if pl_proposto and not pl_atual:
        return _decisao(
            "atual", "plausibilidade",
            f"{campo}: o valor proposto ({origem_proposto}) é implausível — "
            f"{pl_proposto}; o em registro não.",
        )
    if pl_atual and not pl_proposto:
        return Decisao(
            vencedor=None, regra="plausibilidade", requer_humano=True,
            sugerido="proposto",
            motivo=f"{campo}: o valor em registro ({origem_atual}) é "
                   f"implausível — {pl_atual}; proposto pré-selecionado, "
                   f"confirmação humana necessária.",
        )

    # 1b. Live evidence — a value no live document asserts any more has been
    # retracted; the side that still has support wins.
    if evidencia is not None:
        sust_atual, sust_proposto = evidencia.atual_sustentado, evidencia.proposto_sustentado
        if sust_atual is False and sust_proposto is not False:
            return _decisao(
                "proposto", "retratado",
                f"{campo}: o documento {origem_atual!r} que sustentava o valor "
                f"em registro não o afirma mais (excluído, relido com outro "
                f"valor, ou de duas pessoas sem atribuição a esta); o "
                f"proposto ({origem_proposto}) não foi retratado.",
            )
        if sust_proposto is False and sust_atual is not False:
            return _decisao(
                "atual", "retratado",
                f"{campo}: o documento {origem_proposto!r} da proposta não a "
                f"afirma mais (excluído, relido com outro valor, ou de duas "
                f"pessoas sem atribuição a esta); o em registro "
                f"({origem_atual}) não foi retratado.",
            )

    # 2. Corroboration — ≥2 distinct origins agreeing outranks a lone
    # dissenter, regardless of tier.
    origens_atual = {origem_atual} if origem_atual else set()
    origens_proposto = {origem_proposto} if origem_proposto else set()
    fontes = list(historico) + list(evidencia.afirmacoes if evidencia is not None else ())
    for valor, origem in fontes:
        if not origem or _vazio(valor):
            continue
        if mesmo_valor(campo, valor, valor_atual):
            origens_atual.add(origem)
        elif mesmo_valor(campo, valor, valor_proposto):
            origens_proposto.add(origem)
    n_atual, n_proposto = len(origens_atual), len(origens_proposto)
    if n_atual >= CORROBORACAO_MINIMA or n_proposto >= CORROBORACAO_MINIMA:
        if n_atual > n_proposto:
            return _decisao(
                "atual", "corroboracao",
                f"{campo}: {n_atual} fontes independentes concordam com o "
                f"valor em registro contra {n_proposto} com o proposto.",
            )
        if n_proposto > n_atual:
            return _decisao(
                "proposto", "corroboracao",
                f"{campo}: {n_proposto} fontes independentes concordam com "
                f"o valor proposto contra {n_atual} com o em registro.",
            )
        # Equal corroboration on both sides (both >= 2) — fall through to
        # tier; a genuine 2-vs-2 split is not decided by counting alone.

    # 3. Source tier — the higher MEASURED precision wins.
    p_atual = precisao_de(campo, origem_atual)
    p_proposto = precisao_de(campo, origem_proposto)
    if p_atual is not None and p_proposto is not None and p_atual.precisao != p_proposto.precisao:
        if p_atual.precisao > p_proposto.precisao:
            return _decisao(
                "atual", "tier",
                f"{campo}: {origem_atual!r} tem precisão medida "
                f"{p_atual.precisao:.0%} (n={p_atual.n}) contra "
                f"{p_proposto.precisao:.0%} (n={p_proposto.n}) de "
                f"{origem_proposto!r}.",
            )
        return _decisao(
            "proposto", "tier",
            f"{campo}: {origem_proposto!r} tem precisão medida "
            f"{p_proposto.precisao:.0%} (n={p_proposto.n}) contra "
            f"{p_atual.precisao:.0%} (n={p_atual.n}) de {origem_atual!r}.",
        )

    # 4. Same tier, unmeasured tier, or an unresolved 2-vs-2 corroboration
    # split — a human decides, exactly as today.
    return _HUMANO


__all__ = [
    "REGRAS_PROVA_OBJETIVA",
    "CAMPOS_IDENTIDADE_EXCLUSIVA",
    "CAMPOS_POR_PESSOA",
    "CORROBORACAO_MINIMA",
    "DOCUMENTOS_DUAS_PESSOAS",
    "EvidenciaViva",
    "N_MINIMO_VALIDACAO",
    "PRECISAO",
    "PRECISAO_VALIDACAO_AUTOMATICA",
    "Decisao",
    "Precisao",
    "decisao_outra_pessoa",
    "normalizar_logradouro",
    "chave_logradouro",
    "logradouros_equivalentes",
    "nomes_equivalentes",
    "rg_rne_equivalente",
    "orgao_conhecido",
    "confianca_baixa",
    "CONFIANCAS_BAIXAS",
    "CONFIANCAS_FIRMES",
    "FONTE_NAO_ATESTA",
    "only_digits",
    "precisao_de",
    "resolver_divergencia",
    "valido_para_contrato_sem_revisao",
]
