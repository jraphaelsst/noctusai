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
from noctusai_lib.integrations.documents.name import (
    find_name_conflitos,
    looks_like_a_name,
    nomes_em_par,
)
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
    #: The nubente's OWN pre-marriage/maiden name, when a structured
    #: "Primeiro/Segundo Cônjuge" block prints one AND it differs from
    #: `nome` — see `_ler_bloco_estruturado`. `nome` itself always holds the
    #: document's CURRENT/post-marriage form when the certidão states one
    #: ("Nome que o [...] cônjuge passou a utilizar"): that is the name a
    #: contract signs against, so it is the primary field; the maiden name
    #: rides here as secondary, never the other way round (P1/883,
    #: 2026-09-28).
    nome_anterior: Optional[str] = None
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


# ─── The "Primeiro/Segundo Cônjuge" structured-block layout (P1/883,
# 2026-09-28) ────────────────────────────────────────────────────────────
#
# A national CNJ-standardised certidão names neither a `NOMES` table nor a
# narrative "NOME, nascido ..." clause. Instead each nubente owns a literal
# "Primeiro Cônjuge:" / "Segundo Cônjuge:" block (also "1º"/"2º Cônjuge" —
# the ordinal-indicator glyph decomposes to a bare "o" under
# `text.strip_accents_upper`'s own NFKD pass, same as every other accent
# this package strips), holding that spouse's OWN nome / data de
# nascimento / nacionalidade, and — separately — a
# "Nome que o [primeiro|segundo] cônjuge passou a utilizar" line stating
# their CURRENT (post-marriage) name. This is recognised as an INDEPENDENT
# two-holder signal, never routed through `find_name_conflitos`: that
# function's own `NOMES ATUAL DOS CONJUGES` multi-holder header (when the
# document ALSO carries one, printed separately near the top, purely as an
# index) prints the spouses' CURRENT names, which can legitimately differ
# from this layout's own per-block name — collapsing both into ONE
# candidate pool would report 3 distinct holders instead of 2 whenever both
# signals are present on the same document.

_CONJUGE_BLOCO_RE = re.compile(r"\b(PRIMEIRO|SEGUNDO|1O?|2O?)\s+CONJUGE\b\s*[:\-]?\s*")
_NOME_ATUAL_CONJUGE_RE = re.compile(
    r"\bNOME\s+QUE\s+O\s+(PRIMEIRO|SEGUNDO|1O?|2O?)\s+CONJUGE\s+PASSOU\s+A\s+UTILIZAR\b\s*[:\-]?\s*"
)
#: Rows that close a nubente's own block — the couple's shared facts start
#: here. Broader than `_ROTULOS_DO_CASAL` above: this layout's own wording
#: is "Data DA CELEBRAÇÃO do casamento", not the tabular layout's bare
#: "Data DO casamento" — a distinct constant rather than widening the
#: tabular one, so the two readers stay independently correct.
_FIM_BLOCO_ESTRUTURADO_RE = re.compile(
    r"(?m)^[ \t]*(?:DATA\s+D[AO]\s+(?:CELEBRACAO\s+D[AO]\s+)?CASAMENTO|"
    r"REGIME\s+DE\s+BENS|AVERBAC|ANOTAC|OBSERVAC)"
)
_PRIMEIRO_MARCAS = frozenset({"PRIMEIRO", "1", "1O"})

#: 🔴 THE BUG THIS CLOSES — real, measured (P1/883, 2026-09-28): the
#: "Nome atual dos cônjuges" header interleaves each current name with a
#: "Número do CPF" row — but a cartório's own matrícula-number row
#: ("Matrícula: 123.456.789-10") sits right after it, is CPF-shaped by
#: coincidence, and can pass the check-digit gate too. Unguarded, the
#: general name-to-name CPF window below would credit it to whichever
#: spouse's occurrence happens to be nearest — a wrong, unrelated number
#: written onto a person's record. A CPF-shaped value is never ours when a
#: "Matrícula" label sits immediately before it, full stop — not
#: demoted, rejected, the same posture `labels.py` takes for a
#: value-type decoy.
_MATRICULA_LABEL_RE = re.compile(r"\bMATRICULA\b")
_MATRICULA_JANELA = 40


def _e_valor_de_matricula(norm: str, pos: int) -> bool:
    """Is the CPF-shaped match at `pos` actually a Matrícula number
    mislabelled — never a real CPF?"""
    janela = norm[max(0, pos - _MATRICULA_JANELA) : pos]
    return _MATRICULA_LABEL_RE.search(janela) is not None


def _ordinal(rotulo: str) -> int:
    """0 for the first spouse's own marker, 1 for the second's."""
    return 0 if rotulo in _PRIMEIRO_MARCAS else 1


def _extrai_valor_apos(norm: str, fim: int) -> Optional[str]:
    """The name-shaped value right after a label: on the SAME line, or —
    when that line carries none of its own — the very next line. Mirrors
    `name._candidatos`'s own same-line/next-line idiom; kept local rather
    than imported, since this module already defines its own label
    readers (`_ROTULOS_TABULARES` et al.) independently of `name.py`."""
    quebra = norm.find("\n", fim)
    fim_linha = quebra if quebra >= 0 else len(norm)
    bruto = norm[fim:fim_linha].strip(" :\t-–—.|*")
    if bruto:
        return bruto if looks_like_a_name(bruto) else None
    if quebra < 0:
        return None
    prox_quebra = norm.find("\n", quebra + 1)
    fim_prox = prox_quebra if prox_quebra >= 0 else len(norm)
    proximo = norm[quebra + 1 : fim_prox].strip(" :\t-–—.|*")
    return proximo if proximo and looks_like_a_name(proximo) else None


def _cpfs_por_adjacencia(
    norm: str, nomes: tuple[str, str], cpfs: list[tuple[int, str]]
) -> tuple[Optional[str], Optional[str]]:
    """The CPF printed adjacent to each of two co-equal names — same
    windowing rule `find_conjuges`'s own narrative/tabular branch already
    uses (a name's FIRST occurrence to the other's, or a fixed
    `_CPF_JANELA` past it), factored out so the structured-block reader
    below can reuse it against a DIFFERENT pair of name strings (this
    layout's own printed names, not `find_name_conflitos`'s)."""
    ocorrencias = [list(_padrao_nome(n).finditer(norm)) for n in nomes]
    if not ocorrencias[0] or not ocorrencias[1]:
        return (None, None)
    usados: set[int] = set()
    resultado: list[Optional[str]] = []
    for i in range(2):
        outro = ocorrencias[1 - i]
        inicio = ocorrencias[i][0].end()
        limite = outro[0].start() if i == 0 else inicio + _CPF_JANELA
        if limite <= inicio:
            limite = inicio + _CPF_JANELA
        cpf = None
        for pos, valor in cpfs:
            if inicio <= pos < limite and pos not in usados and valor:
                cpf = valor
                usados.add(pos)
                break
        resultado.append(cpf)
    return (resultado[0], resultado[1])


def _ler_bloco_estruturado(text: str) -> tuple[ConjugeLido, ...]:
    """Both spouses of a "Primeiro/Segundo Cônjuge" structured-block
    certidão — see the section header above. `()` unless BOTH block
    openers are present, each with exactly one name-shaped value."""
    norm, origem = normalized_with_offsets(text)

    # 🔴 "Nome QUE O primeiro cônjuge passou a utilizar" contains the exact
    # substring "PRIMEIRO CONJUGE" that `_CONJUGE_BLOCO_RE` also matches —
    # a real, measured false-positive (P1/883, 2026-09-28): unguarded, the
    # block-opener scan below saw it as a SECOND "Primeiro Cônjuge" block
    # and rejected the whole document as malformed. Spans of the
    # "nome atual" label are computed first so a block-opener match landing
    # inside one is recognised as part of THAT phrase, never a fresh block.
    nome_atual_spans = [m.span() for m in _NOME_ATUAL_CONJUGE_RE.finditer(norm)]

    def _dentro_de_nome_atual(m: "re.Match[str]") -> bool:
        return any(a <= m.start() < b for a, b in nome_atual_spans)

    blocos: dict[int, "re.Match[str]"] = {}
    for m in _CONJUGE_BLOCO_RE.finditer(norm):
        if _dentro_de_nome_atual(m):
            continue
        idx = _ordinal(m.group(1))
        if idx in blocos:
            return ()  # more than one of the same ordinal — malformed, never guess
        blocos[idx] = m
    if len(blocos) != 2:
        return ()

    nomes: dict[int, str] = {}
    for idx, m in blocos.items():
        valor = _extrai_valor_apos(norm, m.end())
        if valor is None:
            return ()
        nomes[idx] = valor

    inicio_bloco = {0: blocos[0].end(), 1: blocos[1].end()}
    fim_bloco = {
        0: blocos[1].start(),
        1: next(
            (
                m.start()
                for m in _FIM_BLOCO_ESTRUTURADO_RE.finditer(norm, blocos[1].end())
            ),
            min(len(norm), blocos[1].end() + _SEGMENTO_MAX),
        ),
    }

    nomes_atuais: dict[int, str] = {}
    for m in _NOME_ATUAL_CONJUGE_RE.finditer(norm):
        idx = _ordinal(m.group(1))
        valor = _extrai_valor_apos(norm, m.end())
        if valor is not None:
            nomes_atuais[idx] = valor

    cpfs = [
        (m.start(), format_cpf(m.group(1)))
        for m in _CPF_RE.finditer(norm)
        if is_valid(m.group(1)) and not _e_valor_de_matricula(norm, m.start())
    ]
    cpf0, cpf1 = _cpfs_por_adjacencia(norm, (nomes[0], nomes[1]), cpfs)
    cpfs_por_indice = {0: cpf0, 1: cpf1}

    out: list[ConjugeLido] = []
    for idx in (0, 1):
        a, fim = inicio_bloco[idx], fim_bloco[idx]
        seg_orig = text[origem[a] : origem[fim - 1] + 1] if fim > a else ""
        seg_norm = norm[a:fim] if fim > a else ""

        d, d_conf, _ = find_birthdate(seg_orig) if seg_orig else (None, "nenhuma", None)
        nac, nac_conf, _ = (
            find_nacionalidade(seg_orig) if seg_orig else (None, "nenhuma", None)
        )
        prof, prof_conf, _ = (
            find_profissao(seg_orig) if seg_orig else (None, "nenhuma", None)
        )
        gen, gen_conf = _genero(seg_norm)

        cpf = cpfs_por_indice[idx]
        nome_bloco = nomes[idx]
        nome_atual = nomes_atuais.get(idx)
        # The CURRENT (post-marriage) name is what a contract signs against
        # — see `ConjugeLido.nome_anterior`'s own comment — so it is
        # preferred whenever the certidão states one and it actually
        # differs from the block's own printed name.
        nome_final = nome_atual if nome_atual else nome_bloco
        nome_anterior = nome_bloco if nome_atual and nome_atual != nome_bloco else None

        out.append(
            ConjugeLido(
                nome=nome_final,
                nome_anterior=nome_anterior,
                cpf=cpf,
                cpf_confianca="alta" if cpf else "nenhuma",
                data_nascimento=d,
                data_nascimento_confianca=d_conf if d else "nenhuma",
                nacionalidade=nac,
                nacionalidade_confianca=nac_conf if nac else "nenhuma",
                profissao=prof,
                profissao_confianca=prof_conf if prof else "nenhuma",
                genero=gen,
                genero_confianca=gen_conf,
            )
        )
    return tuple(out)


# ─── The OLD-NARRATIVE opening-clause layout (P2 corpus, 2026-09-28)
# ──────────────────────────────────────────────────────────────────────────
#
# A pre-CNJ certidão frequently names BOTH nubentes only ONCE, in the
# document's own opening recital — "foi feito assento do matrimônio de
# FULANO e CICRANA" / "foi registrado o casamento (religioso) de FULANO com
# CICRANA" — and never repeats either name again: the per-nubente paragraphs
# that follow ("O contratante nascido em ...", "ELE, nascido em ...") qualify
# whoever was just named WITHOUT restating a name at all. Neither
# `_ler_bloco_estruturado` (no "Primeiro/Segundo Cônjuge" block) nor
# `find_name_conflitos` (no `NOME`/`NOMES` label anywhere) sees this
# document at all — every candidate pool used elsewhere in this module is
# built on a LABEL, and this clause is bare narrative prose. This is an
# INDEPENDENT reader for that one specific recital, tried before falling
# back to the labelled paths below.
#: The `,?` covers "Foi feito o casamento, de FULANO ... com CICRANA ..." —
#: an old form template that punctuates the verb clause and the couple's
#: names as two separate clauses rather than running "CASAMENTO DE" together
#: (P2 corpus, 2026-09-28).
_CONJUGES_NARRATIVA_RE = re.compile(r"\b(?:MATRIMONIO|CASAMENTO(?:\s+RELIGIOSO)?),?\s+DE\s+")
#: The clause ends at the first of these — a real full name never contains
#: any of them.
_NARRATIVA_TERMINADORES = ("\n", ",", ".")
#: A pre-printed form's dotted blank-line filler ("de FULANO..........."),
#: three or more periods in a row — never real prose punctuation.
_FILLER_PONTILHADO_RE = re.compile(r"\.{3,}")

#: 🔴 THE MARRIED-NAME ADOPTION NOTE ON THIS SAME LAYOUT — real, measured
#: (P2 corpus, 2026-09-28): this narrative family also carries its own
#: "A/O contra(ente|tante|tente) passou a assinar ..." sentence, stating
#: whichever nubente changed their name on marriage (or, printed the same
#: way, that they did NOT — "... passou a assinar O MESMO NOME."). Read the
#: same way `_ler_bloco_estruturado` reads its own "Nome que o [...] cônjuge
#: passou a utilizar" line — into `nome`/`nome_anterior` — rather than a
#: second, disconnected concept: see `ConjugeLido.nome_anterior`'s own
#: comment for why the CURRENT name is primary. This layout carries no
#: per-nubente gender marker of its own (unlike the CNJ block's own
#: "NASCIDO"/"NASCIDA" qualification clause), so the adoption sentence's own
#: article ("A" feminine / "O" masculine) is routed to a name by POSITION —
#: every certidão in the P2 corpus lists the groom in the recital's clause
#: FIRST and the bride second, the universal Brazilian civil-registry
#: convention (also true of the CNJ narrative "O contratante" / "A
#: contratante" paragraph ORDER, and of `_ler_bloco_estruturado`'s own
#: PRIMEIRO/SEGUNDO ordinal convention).
_ADOCAO_VERBO = (
    r"(?:PASSOU|PASSAR[AÁ])\s+A\s+(?:USAR|ASSINAR)(?:-SE)?(?:\s+O\s+NOME\s+DE)?|"
    r"CONTINU(?:A|OU)\s+A\s+(?:USAR|ASSINAR)(?:\s+O\s+(?:MESMO\s+NOME|NOME\s+DE))?"
)
_ADOCAO_MASC_RE = re.compile(r"\bO\s+CONTRA(?:TANTE|TENTE|ENTE)\b\s*" + _ADOCAO_VERBO + r"\s*")
_ADOCAO_FEM_RE = re.compile(r"\bA\s+CONTRA(?:TANTE|TENTE|ENTE)\b\s*" + _ADOCAO_VERBO + r"\s*")
#: 🔴 THE SAME NOTE, WRITTEN BY ANAPHORA — real, measured (P2 corpus,
#: 2026-09-28): another certidão in this same narrative family states the
#: adoption INSIDE the nubente's own qualification paragraph, referring back
#: to them as "a qual" ("... filha de IRACI ..., a qual passou assinar-se
#: NOVO NOME") rather than repeating "A contratante". `_ADOCAO_FEM_RE` /
#: `_ADOCAO_MASC_RE` above require the article DIRECTLY before the verb, so
#: they do not see this; here the gender is instead read off the NEAREST
#: preceding "O/A contra(ente|tante|tente)" marker — whichever qualification
#: paragraph "a qual" is still inside.
_CONTRA_MARCADOR_RE = re.compile(r"\b([OA])\s+CONTRA(?:TANTE|TENTE|ENTE)\b")
_ADOCAO_QUAL_RE = re.compile(r"\bA\s+QUAL\s+(?:PASSOU|PASSAR[AÁ])\s+(?:A\s+)?ASSINAR(?:-SE)?\b\s*")
_MESMO_NOME_RE = re.compile(r"^(?:O\s+)?MESMO\s+NOME\b")
_SEPARADORES_LOCAIS = " :\t-–—.|*\"'"


def _valor_de_adocao(norm: str, fim: int) -> Optional[str]:
    """The adopted name right after an adoption-clause verb, or `None` when
    the clause states no change ("O MESMO NOME") or the tail is not itself
    name-shaped."""
    limites = [
        p
        for p in (norm.find("\n", fim), norm.find(",", fim), norm.find(".", fim))
        if p >= 0
    ]
    fim_frase = min(limites) if limites else min(len(norm), fim + _SEGMENTO_MAX)
    # Collapsed, not merely edge-trimmed — see `name.nomes_em_par`'s own note
    # on why a value spanning a PDF line-wrap must never keep a raw "\n".
    bruto = " ".join(norm[fim:fim_frase].strip(_SEPARADORES_LOCAIS).split())
    if not bruto or _MESMO_NOME_RE.match(bruto):
        return None
    return bruto if looks_like_a_name(bruto) else None


def _limites_candidatos(norm: str, inicio: int, teto: int) -> list[int]:
    """EVERY terminator occurrence between `inicio` and `teto`, ascending,
    `teto` itself last — the set of "clause ends here" hypotheses tried in
    order by `_ler_narrativa_matrimonio` below.

    Every occurrence, not just the first of each kind — real, measured (P2
    corpus, 2026-09-28): a title abbreviation ("Sr.", "MM.") between the two
    names carries its OWN period, which is a real terminator hit but the
    WRONG one (it lands mid-clause, well short of the second name). Only the
    first-of-each-kind position would get stuck there forever; every
    position lets the caller's loop move past a too-short false hit to the
    next one out.
    """
    posicoes = {
        m.start()
        for terminador in _NARRATIVA_TERMINADORES
        for m in re.finditer(re.escape(terminador), norm[inicio:teto])
    }
    posicoes = {inicio + p for p in posicoes}
    posicoes.add(teto)
    return sorted(posicoes)


def _ler_narrativa_matrimonio(text: str) -> tuple[ConjugeLido, ...]:
    """Both spouses named ONLY in the old-narrative opening recital — see
    the section header above. `()` unless the recital names exactly two
    name-shaped nubentes.

    🔴 THE TERMINATOR IS TRIED AT INCREASING DISTANCE, NOT TAKEN AT THE
    FIRST HIT — real, measured (P2 corpus, 2026-09-28): `normalized_with_offsets`
    (unlike this module's sibling functions' own `normalize()`) preserves the
    source text's OWN line breaks verbatim, and a PDF's line-wrap routinely
    falls mid-name, not at a clause boundary — "...do matrimônio de FULANO
    DE\\nTAL PAIEIS com CICRANA DA SILVA, contraído..." wraps between "DE"
    and "TAL". Stopping at that first "\\n" cuts the first name in half and
    the split below fails; stopping only at the comma/period risks running
    past a genuine one-line clause into the NEXT sentence for a document
    that happens not to wrap. Neither distance is right for every layout, so
    every terminator candidate (nearest first) is tried until one yields two
    genuinely well-formed names — `nomes_em_par`'s own strict word/character
    checks are what make a too-far guess self-rejecting, not a heuristic
    here about which candidate is "more likely" correct.
    """
    norm, _origem = normalized_with_offsets(text)
    # A pre-printed form's own dotted blank-lines ("de FULANO............
    # com CICRANA............") are page-layout filler, never prose — real,
    # measured (P2 corpus, 2026-09-28): unstripped, a run of them sits
    # between the two names and fails `looks_like_a_name`'s character check
    # on whichever candidate span still includes it, no matter how the
    # terminator search below is tuned. Collapsed to a single space,
    # LOCALLY, before this reader does anything else with the text.
    norm = _FILLER_PONTILHADO_RE.sub(" ", norm)
    m = _CONJUGES_NARRATIVA_RE.search(norm)
    if m is None:
        return ()

    teto = min(len(norm), m.end() + _SEGMENTO_MAX)
    par = None
    for fim in _limites_candidatos(norm, m.end(), teto):
        # "COM" first: found further right than an embedded "E" inside the
        # first name itself would be, so a genuine "NOME1 E MEIO com NOME2"
        # splits on the real separator instead of the name's own connector.
        par = nomes_em_par(norm[m.end() : fim], conectores=("COM", "E"))
        if par is not None:
            break
    if par is None:
        return ()

    adocoes: dict[int, Optional[str]] = {0: None, 1: None}
    m_masc = _ADOCAO_MASC_RE.search(norm)
    if m_masc is not None:
        adocoes[0] = _valor_de_adocao(norm, m_masc.end())
    m_fem = _ADOCAO_FEM_RE.search(norm)
    if m_fem is not None:
        adocoes[1] = _valor_de_adocao(norm, m_fem.end())
    for m_qual in _ADOCAO_QUAL_RE.finditer(norm):
        genero_letra = None
        for gm in _CONTRA_MARCADOR_RE.finditer(norm, 0, m_qual.start()):
            genero_letra = gm.group(1)
        if genero_letra is None:
            continue
        idx = 0 if genero_letra == "O" else 1
        if adocoes[idx] is None:
            adocoes[idx] = _valor_de_adocao(norm, m_qual.end())

    out: list[ConjugeLido] = []
    for idx, nome_recital in enumerate(par):
        nome_atual = adocoes[idx]
        nome_final = nome_atual if nome_atual else nome_recital
        nome_anterior = nome_recital if nome_atual and nome_atual != nome_recital else None
        out.append(ConjugeLido(nome=nome_final, nome_anterior=nome_anterior))
    return tuple(out)


def find_conjuges(text: str) -> tuple[ConjugeLido, ...]:
    """Both spouses of a certidão de casamento, in document order.

    `()` unless the document names exactly two equally-prominent holders.
    """
    bloco = _ler_bloco_estruturado(text or "")
    if bloco:
        return bloco

    narrativa = _ler_narrativa_matrimonio(text or "")
    if narrativa:
        return narrativa

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
        if is_valid(m.group(1)) and not _e_valor_de_matricula(norm, m.start())
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
