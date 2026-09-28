"""Read BOTH spouses off a certidão de casamento.

`find_name` / `find_cpf` correctly decline to put one of two equally prominent
spouses into a single `nome` / `cpf` slot (see `real.py`'s "TWO TITULARES"
note). That left the other spouse's facts on the floor: a couple's certidão
names both people, and both of them usually sign the same contract.

This module attributes the per-PERSON facts to each spouse separately:

- **nome** — the two candidates `find_name_conflitos` already names;
- **cpf** — the first check-digit-valid CPF printed after that spouse's name
  and before the other spouse's (the form model's `NOMES` block prints
  `NAME / CPF / NAME / CPF`);
- **data de nascimento, nacionalidade, profissão, gênero** — read from that
  spouse's OWN qualification paragraph ("ALMIR ..., nascido no dia ...,
  de nacionalidade brasileira, filho de ..."), never from the whole document,
  where the other spouse's readings would collide with them. See the
  comment beside `find_birthdate(seg_orig)`, below, for a P1/883
  (2026-09-25) real bug this segment-scoping does NOT by itself fully
  cover, and what does (a cross-document plausibility check in `real.py`).
  A TABULAR certidão (one labelled row per field, no such clause) is read
  by `_dados_tabulares` instead: the k-th `DATA DE NASCIMENTO` /
  `NACIONALIDADE` / `PROFISSÃO` row after the names belongs to the k-th
  spouse, when that label occurs exactly twice (P1/883, 2026-09-28).

Couple-level facts (estado civil, regime de bens, data do casamento) are NOT
here: they belong to both spouses equally and stay on `IdentityFields`.

🔴 GÊNERO FROM GRAMMAR IS A SUGGESTION
---------------------------------------
A certidão prints no `SEXO` box, but its prose agrees in gender with the
person it qualifies: "nascido" / "filho" vs "nascida" / "filha". That is real
evidence, but inferential, so it is `baixa` — and "de nacionalidade
brasileira" is deliberately NOT a marker (`nacionalidade` is a feminine noun
whatever the person's sex).

Pure, deterministic, never raises. Returns `()` whenever the document does
not name exactly two spouses — a single-holder document is the ordinary
extractor's job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.cpf import _CPF_RE, format_cpf, is_valid
from noctusai_lib.integrations.documents.gender import FEMININO, MASCULINO
from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets
from noctusai_lib.integrations.documents.nacionalidade import find_nacionalidade
from noctusai_lib.integrations.documents.name import find_name_conflitos
from noctusai_lib.integrations.documents.profession import find_profissao
from noctusai_lib.integrations.documents.text import strip_accents_upper

#: How far past a spouse's name its CPF may sit when no second name bounds it.
_CPF_JANELA = 200
#: How long a qualification paragraph may run before it is cut.
_SEGMENTO_MAX = 700

_MARCAS_MASC = re.compile(r"\b(?:NASCIDO|FILHO|PORTADOR|INSCRITO|DOMICILIADO)\b")
_MARCAS_FEM = re.compile(r"\b(?:NASCIDA|FILHA|PORTADORA|INSCRITA|DOMICILIADA)\b")


@dataclass(frozen=True)
class ConjugeLido:
    """One spouse's per-person facts, each with its own confidence string."""

    nome: str
    cpf: Optional[str] = None
    cpf_confianca: str = "nenhuma"
    data_nascimento: Optional[date] = None
    data_nascimento_confianca: str = "nenhuma"
    nacionalidade: Optional[str] = None
    nacionalidade_confianca: str = "nenhuma"
    profissao: Optional[str] = None
    profissao_confianca: str = "nenhuma"
    genero: Optional[str] = None
    genero_confianca: str = "nenhuma"
    #: Set by the extractor (never by this module) when the caller's
    #: `TitularEsperado` hint selected this spouse.
    titular: bool = False


def _padrao_nome(nome: str) -> re.Pattern[str]:
    """The name as it appears in normalised text, any whitespace between
    words (a line break inside a long name is common in a scan)."""
    palavras = strip_accents_upper(nome).split()
    return re.compile(r"\b" + r"\s+".join(re.escape(p) for p in palavras) + r"\b")


def _genero(segmento_norm: str) -> tuple[Optional[str], str]:
    masc = bool(_MARCAS_MASC.search(segmento_norm))
    fem = bool(_MARCAS_FEM.search(segmento_norm))
    if masc and not fem:
        return (MASCULINO, "baixa")
    if fem and not masc:
        return (FEMININO, "baixa")
    return (None, "nenhuma")
_ROTULOS_TABULARES: dict[str, re.Pattern[str]] = {
    "data_nascimento": re.compile(r"(?m)^[ \t]*DATA\s+DE\s+NASCIMENTO\b"),
    "nacionalidade": re.compile(r"(?m)^[ \t]*NACIONALIDADE\b"),
    "profissao": re.compile(r"(?m)^[ \t]*(?:PROFISSAO|OCUPACAO)\b"),
}
#: Couple-level rows that close the per-person block of a tabular certidão.
_ROTULOS_DO_CASAL = re.compile(
    r"(?m)^[ \t]*(?:DATA\s+(?:DO|DE)\s+CASAMENTO|REGIME\s+DE\s+BENS|AVERBAC|ANOTAC|OBSERVAC)"
)
_ORDEM_CONFIANCA = ("nenhuma", "baixa", "media", "alta")


def _no_maximo_media(confianca: str) -> str:
    """Attribution by position is an inference, never `alta`."""
    if _ORDEM_CONFIANCA.index(confianca) > _ORDEM_CONFIANCA.index("media"):
        return "media"
    return confianca


def _dados_tabulares(
    text: str, norm: str, origem: list[int], indice: int, fim_dos_nomes: int
) -> dict:
    """Per-person facts of the `indice`-th spouse on a TABULAR certidão.

    That layout prints no "NOME, nascido ..." clause: after the `NOMES` block
    each per-person field is its own labelled row, once per spouse, in the
    same order as the names. A label that occurs EXACTLY twice after the
    names is split by position — its k-th row belongs to the k-th spouse.
    Any other count is ambiguous and yields nothing for that field. Each
    row's reading is bounded by the next labelled row (per-person or
    couple-level), so another row's value cannot bleed in; its confidence
    is capped at `media` because the attribution is positional.
    """
    limites = sorted(
        {m.start() for r in _ROTULOS_TABULARES.values() for m in r.finditer(norm, fim_dos_nomes)}
        | {m.start() for m in _ROTULOS_DO_CASAL.finditer(norm, fim_dos_nomes)}
    )
    trechos: dict[str, str] = {}
    for campo, rotulo in _ROTULOS_TABULARES.items():
        linhas = list(rotulo.finditer(norm, fim_dos_nomes))
        if len(linhas) != 2:
            continue
        a = linhas[indice].start()
        fim = min(next((x for x in limites if x > a), len(norm)), a + _SEGMENTO_MAX)
        if fim > a:
            trechos[campo] = text[origem[a] : origem[fim - 1] + 1]
    dados: dict = {}
    if "data_nascimento" in trechos:
        d, conf, _ = find_birthdate(trechos["data_nascimento"])
        if d:
            dados.update(data_nascimento=d, data_nascimento_confianca=_no_maximo_media(conf))
    if "nacionalidade" in trechos:
        nac, conf, _ = find_nacionalidade(trechos["nacionalidade"])
        if nac:
            dados.update(nacionalidade=nac, nacionalidade_confianca=_no_maximo_media(conf))
    if "profissao" in trechos:
        prof, conf, _ = find_profissao(trechos["profissao"])
        if prof:
            dados.update(profissao=prof, profissao_confianca=_no_maximo_media(conf))
    return dados


def find_conjuges(text: str) -> tuple[ConjugeLido, ...]:
    """Both spouses of a certidão de casamento, in document order.

    `()` unless the document names exactly two equally-prominent holders.
    """
    candidatos = find_name_conflitos(text or "")
    if not candidatos or len(candidatos) != 2:
        return ()
    norm, origem = normalized_with_offsets(text)

    ocorrencias: dict[str, list[re.Match[str]]] = {}
    for nome in candidatos:
        achados = list(_padrao_nome(nome).finditer(norm))
        if not achados:
            return ()
        ocorrencias[nome] = achados
    ordem = sorted(candidatos, key=lambda n: ocorrencias[n][0].start())

    cpfs = [
        (m.start(), format_cpf(m.group(1)))
        for m in _CPF_RE.finditer(norm)
        if is_valid(m.group(1))
    ]
    usados: set[int] = set()

    out: list[ConjugeLido] = []
    for i, nome in enumerate(ordem):
        outro = ordem[1 - i]
        inicio = ocorrencias[nome][0].end()
        limite = ocorrencias[outro][0].start() if i == 0 else inicio + _CPF_JANELA
        if limite <= inicio:
            limite = inicio + _CPF_JANELA
        cpf = None
        for pos, valor in cpfs:
            if inicio <= pos < limite and pos not in usados and valor:
                cpf = valor
                usados.add(pos)
                break

        # The qualification paragraph: the first occurrence of the name
        # followed by a comma ("NAME, nascido ..."). Bounded by the other
        # spouse's paragraph, a blank line, or `_SEGMENTO_MAX`.
        qualif = next(
            (m for m in ocorrencias[nome] if re.match(r"\s*,", norm[m.end() : m.end() + 3])),
            None,
        )
        dados: dict = {}
        if qualif is not None:
            a = qualif.end()
            fim = min(len(norm), a + _SEGMENTO_MAX)
            for m in ocorrencias[outro]:
                if m.start() > a:
                    fim = min(fim, m.start())
                    break
            quebra = norm.find("\n\n", a)
            if 0 <= quebra < fim:
                fim = quebra
            if fim > a:
                seg_orig = text[origem[a] : origem[fim - 1] + 1]
                seg_norm = norm[a:fim]
                d, d_conf, _ = find_birthdate(seg_orig)
                # 🔴 P1/883 (2026-09-25) — NOT restricted to a labelled read
                # here, and that took a real test failure to confirm rather
                # than assumed. The MAINLINE certidão phrasing spells the
                # date in words first, echoing it numerically in parens
                # immediately after — "nascido no dia quatro de outubro de
                # mil novecentos e sessenta e um (04/10/1961)" — and
                # `birthdate.py` cannot parse the fully-spelled-out form (its
                # `_TEXTUAL_DATE` needs a DIGIT day; only the numeric echo
                # matches). The extenso words between "nascido" and "(" are
                # long enough that `birthdate._LABEL_WINDOW` (48 chars) never
                # reaches back to the label from the ONE date `birthdate.py`
                # can actually see, so that date is scored `baixa`
                # (unlabelled) even on a clean, correctly-transcribed
                # document — trying a labelled-only gate here demonstrably
                # broke `test_each_spouse_gets_their_own_facts`'s own real
                # certidão fixture. The defence this segment already had —
                # bounding the read to THIS spouse's own qualification
                # clause, so the couple's celebration date or the other
                # spouse's birthdate cannot bleed in — plus the NEW
                # data_nascimento-vs-data_casamento plausibility cross-check
                # below in `real.py` (which catches exactly the implausible
                # value P1/883 measured, regardless of which confidence tier
                # produced it) are the two defences this module ships.
                # Widening `birthdate.py`'s own label reach, or teaching it
                # `civil_status.py`'s extenso-date parsing, would close the
                # remaining gap more precisely — flagged as a follow-up, not
                # done here (see the delivery report: `civil_status.py` is
                # outside this branch's edit scope).
                nac, nac_conf, _ = find_nacionalidade(seg_orig)
                prof, prof_conf, _ = find_profissao(seg_orig)
                gen, gen_conf = _genero(seg_norm)
                dados = dict(
                    data_nascimento=d,
                    data_nascimento_confianca=d_conf if d else "nenhuma",
                    nacionalidade=nac,
                    nacionalidade_confianca=nac_conf if nac else "nenhuma",
                    profissao=prof,
                    profissao_confianca=prof_conf if prof else "nenhuma",
                    genero=gen,
                    genero_confianca=gen_conf,
                )
        if qualif is None:
            dados = _dados_tabulares(text, norm, origem, i, ocorrencias[ordem[1]][0].end())
        out.append(
            ConjugeLido(
                nome=nome,
                cpf=cpf,
                cpf_confianca="alta" if cpf else "nenhuma",
                **dados,
            )
        )
    return tuple(out)


__all__ = ["ConjugeLido", "find_conjuges"]
