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
1. **Validators** — an invalid side loses outright, whatever its tier: a CPF
   whose check digits fail, a date that does not parse, or (RG-specific) one
   reading that is the OTHER's prefix missing only the trailing check digit
   (a CNH prints the RG without it) — the longer one, carrying its own DV,
   wins regardless of which side it is on.
2. **Corroboration** — a value independently proposed by TWO OR MORE distinct
   sources outranks a single dissenting one, regardless of either side's own
   tier. `historico` carries every OTHER (valor, origem) this (owner, campo)
   has ever seen proposed (`campo_conflitos.historico_valores`) — the
   evidence a THIRD document already settled what looks, today, like a
   two-way disagreement.
3. **Source tier** — the higher measured `PRECISAO` wins. Equal, unmeasured,
   or too-thin-to-trust precision on both sides is NOT a tier decision.
4. Anything still standing needs a human — same posture as today
   (`requer_humano=True`), never a coin flip.

Owner rules beyond this generic order (the married-name adoption rule,
`identidade_extracao_service._nome_anterior_confirma_adocao`; the proof-of-
address holder+recency rule, `identidade_extracao_service.
aplicar_endereco_ao_cliente`) stay with their own callers — they need field-
specific context (`estado_civil`, `nomes_anteriores`, a document's holder)
this generic resolver has no business carrying. They run BEFORE this
resolver is ever consulted, exactly as they do today; this module only
covers what falls through to the generic `else:` conflict branch.

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
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.rg import only_alnum

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


def _validar(campo: str, valor: Any) -> Optional[bool]:
    """`True`/`False` when this campo carries a self-verifying shape (a
    check-digit document number, a date), `None` when there is nothing to
    validate (an empty value, or a campo/valor this function has no verifier
    for) — `None` never counts as either a pass or a fail in
    `resolver_divergencia`."""
    if _vazio(valor):
        return None
    texto = str(valor)
    if campo == "cpf":
        return _cpf_valido(texto)
    if campo == "cnpj":
        return _cnpj_valido(texto)
    if campo in ("data_nascimento", "data_casamento"):
        return _data_valida(texto)
    return None


def _rg_vencedor_por_dv(valor_atual: Any, valor_proposto: Any) -> Optional[str]:
    """`'atual'` / `'proposto'` / `None` — the RG-specific validator rule:
    when one reading is exactly the OTHER's prefix missing only the trailing
    check digit (a CNH prints the RG without it — measured 39%/38% precision
    against the RG card's/matrícula's fuller reading), the longer one, DV
    included, wins — whichever side it happens to be on."""
    a, b = only_alnum(str(valor_atual or "")), only_alnum(str(valor_proposto or ""))
    if not a or not b or a == b:
        return None
    if b.startswith(a) and len(b) == len(a) + 1:
        return "proposto"
    if a.startswith(b) and len(a) == len(b) + 1:
        return "atual"
    return None


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


def normalizar_logradouro(valor: Optional[str]) -> str:
    """Accent/case/space-normalised, with its FIRST token (when it is a
    street-type abbreviation or its spelled-out form) rewritten onto one
    canonical spelling — `"AV Paulista"` and `"Avenida Paulista"` normalise
    to the same string, so comparing the two is no longer a conflict."""
    if not valor:
        return ""
    decomposed = unicodedata.normalize("NFKD", valor)
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    colapsado = re.sub(r"\s+", " ", sem_acento.upper()).strip()
    if not colapsado:
        return ""
    partes = colapsado.split(" ", 1)
    primeiro = partes[0].rstrip(".")
    canonico = _LOGRADOURO_CANONICO.get(primeiro)
    if canonico is None:
        return colapsado
    resto = partes[1] if len(partes) > 1 else ""
    return f"{canonico} {resto}".strip()


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

    @property
    def corroborado(self) -> bool:
        return self.regra == "corroboracao"


def _decisao(vencedor: str, regra: str, motivo: str) -> Decisao:
    return Decisao(vencedor=vencedor, regra=regra, motivo=motivo, requer_humano=False)


_HUMANO = Decisao(
    vencedor=None, regra="requer_humano",
    motivo="Nenhum validador, corroboração ou diferença de precisão medida "
           "separa as duas leituras — decisão humana necessária.",
    requer_humano=True,
)


def resolver_divergencia(
    campo: str,
    *,
    valor_atual: Any,
    origem_atual: Optional[str],
    valor_proposto: Any,
    origem_proposto: str,
    mesmo_valor: Callable[[str, Any, Any], bool],
    historico: Sequence[tuple[Any, Optional[str]]] = (),
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
    """
    # 1. Validators — an invalid side loses outright, whatever its tier.
    ok_atual = _validar(campo, valor_atual)
    ok_proposto = _validar(campo, valor_proposto)
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

    if campo == "rg":
        vencedor_dv = _rg_vencedor_por_dv(valor_atual, valor_proposto)
        if vencedor_dv is not None:
            perdedor_origem = origem_proposto if vencedor_dv == "atual" else origem_atual
            return _decisao(
                vencedor_dv, "rg_prefixo_dv",
                f"rg: uma leitura é a outra sem o dígito verificador — a "
                f"mais longa (com DV) vence ({perdedor_origem!r} perde).",
            )

    # 2. Corroboration — ≥2 distinct origins agreeing outranks a lone
    # dissenter, regardless of tier.
    origens_atual = {origem_atual} if origem_atual else set()
    origens_proposto = {origem_proposto} if origem_proposto else set()
    for valor, origem in historico:
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
    "CORROBORACAO_MINIMA",
    "N_MINIMO_VALIDACAO",
    "PRECISAO",
    "PRECISAO_VALIDACAO_AUTOMATICA",
    "Decisao",
    "Precisao",
    "normalizar_logradouro",
    "only_digits",
    "precisao_de",
    "resolver_divergencia",
    "valido_para_contrato_sem_revisao",
]
