"""Read the cartório and the inscrição municipal off a certidão de matrícula.

Sibling of `matricula.py` (the número de matrícula), same contract: pure,
label-anchored, import-light, returning `(value, confidence, matched_label)`
with confidence as a plain string (`"alta"` / `"baixa"` / `"nenhuma"`).

WHAT A CONTRACT NEEDS FROM HERE
-------------------------------
The promessa de compra e venda prints "caracterizado na Matrícula Nº X do
<cartório>" and "cadastrado pela Prefeitura Municipal sob nº <inscrição>".
Both values sit on page 1 of every certidão:

- the CARTÓRIO in the heading, before the abertura's first labelled block
  (`1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA`, `OFICIAL DE REGISTRO DE
  IMÓVEIS / DA COMARCA DE SÃO PAULO/SP` — often split over two lines);
- the INSCRIÇÃO inside the abertura's `CADASTRO MUNICIPAL:` block
  (`matricula_abertura.segmentar_abertura` finds the block; this module reads
  the number out of it).

🔴 THE HEADING ONLY, NEVER THE BODY
-----------------------------------
A matrícula's body names OTHER registries all the time — "REGISTRO
ANTERIOR: R-5/M-12.345 do Registro de Imóveis de Osasco/SP" is a different
cartório (where the property was registered BEFORE). So the cartório is
read only from the lines before the first abertura label / act header, and
ridigital page furniture ("Documento gerado oficialmente pelo Registro de
Imóveis via www.ridigital.org.br") is discarded outright — it names no
cartório at all.

🔴 DISAGREEMENT IS ABSENCE
--------------------------
Two different cartórios in the heading means the layout was misread; picking
one would attach the wrong registry to a deed. Same rule `find_matricula`
holds for two different heading numbers.

The value is returned LITERALLY (original casing and accents, whitespace
collapsed, trailing punctuation dropped) — it is printed into a deed, and a
human validates it before generation (owner decision D2, 2026-09-22).
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.integrations.documents.text import strip_accents_upper

_WS = re.compile(r"\s+")

#: A heading line naming the registry. `REGISTRO DE IMOVEIS` (accent-folded)
#: is the one phrase every layout seen so far shares; `REGISTRO IMOBILIARIO`
#: is the rarer spelling some cartórios print.
_CARTORIO = re.compile(r"\bREGISTRO\s+(?:DE\s+IMOVEIS|IMOBILIARIO)\b")

#: Page furniture that mentions "Registro de Imóveis" without naming one.
_MOBILIA = re.compile(
    r"RIDIGITAL|WWW\.|HTTP|VALIDE|DOCUMENTO GERADO|TODOS OS REGISTROS|"
    r"ASSINAD[OA] DIGITALMENTE|ONR\b"
)

#: The heading ends where the abertura's labelled blocks or the first act
#: begin. Line-start anchored, like `matricula_abertura._ROTULO`.
_FIM_CABECALHO = re.compile(
    r"^\s*(?:\*\*|<U>)*\s*(?:"
    r"IMOVEL\b|CADASTRO\s+MUNICIPAL|PROPRIETARI[OA]S?\b|REGISTRO\s+ANTERIOR|"
    r"(?:R|AV)\s*[-.]?\s*0*\d+\s*[-/.]"
    r")"
)

#: A continuation line that completes a split heading ("DA COMARCA DE SÃO
#: PAULO/SP", "DE COTIA - SP").
_CONTINUACAO = re.compile(r"^(?:DA|DE|DO|DOS|DAS)\s+[A-Z]")

#: A registry cell that names NO locality — the generic "SERVENTIA DO
#: REGISTRO DE IMÓVEIS" heading whose city sits on a LATER line (live prod,
#: 2026-10-01: 6/6 Cotia certidões print it, then a blank line, then
#: "de Cotia - CNS: 11991-7" — sometimes in the 3rd cell of a two-column
#: scan, sometimes with the abertura date glued on).
_SEM_LOCALIDADE = re.compile(r"\bREGISTRO\s+(?:DE\s+IMOVEIS|IMOBILIARIO)$")

#: How many non-blank heading lines below a locality-less registry cell may
#: still complete it.
_JANELA_LOCALIDADE = 3

#: Two-column scans join cells with runs of spaces; a cell is a column.
_CELULA = re.compile(r"\s{3,}|\t+")

#: Tails glued onto a locality continuation that are not the cartório's
#: name: the national registry code (CNS), and anything after a comma (the
#: abertura's own date — a city name never carries a comma).
_CAUDA_LOCALIDADE = re.compile(r"\s*(?:,.*|[-–—]\s*CNS\b.*)$", re.IGNORECASE)

#: A line that ENDS a split heading from above ("1º OFICIAL DE").
_PREFIXO = re.compile(
    r"^(?:\d{1,2}\s*[OA°]?\s*)?(?:OFICIAL|CARTORIO|SERVICO|OFICIO)\b.*\b(?:DE|DO)$"
)

#: How far into the document the heading may reach, when no abertura label
#: or act header is found to end it. Generous for a two-column scan whose
#: stamps land first; small enough never to reach deep body text.
_MAX_CABECALHO = 1500

_PONTUACAO_FINAL = " \t.,;:-–—"
_MARCAS = re.compile(r"\*\*|</?u>", re.IGNORECASE)


def _limpar(linha: str) -> str:
    return _WS.sub(" ", _MARCAS.sub("", linha)).strip().rstrip(_PONTUACAO_FINAL).strip()


def _linhas_do_cabecalho(text: str) -> list[str]:
    linhas: list[str] = []
    consumido = 0
    for bruta in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if consumido > _MAX_CABECALHO:
            break
        consumido += len(bruta) + 1
        norm = strip_accents_upper(bruta)
        if _FIM_CABECALHO.match(norm):
            break
        linhas.append(bruta)
    return linhas


def _norm(texto: str) -> str:
    return _WS.sub(" ", strip_accents_upper(_MARCAS.sub("", texto))).strip()


def _localidade_abaixo(linhas: list[str], i: int) -> Optional[str]:
    """The locality cell ("de Cotia") completing a locality-less registry
    heading at line `i`: the first cell starting `DE/DA/DO…` within the next
    `_JANELA_LOCALIDADE` non-blank heading lines, its CNS/date tail cut."""
    vistos = 0
    for bruta in linhas[i + 1:]:
        if not bruta.strip():
            continue
        vistos += 1
        if vistos > _JANELA_LOCALIDADE:
            return None
        for celula in _CELULA.split(bruta.strip()):
            n = _norm(celula)
            if _CONTINUACAO.match(n) and not _MOBILIA.search(n) and not _CARTORIO.search(n):
                cortada = _CAUDA_LOCALIDADE.sub("", celula).strip()
                return cortada or None
    return None


def find_cartorio(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """This certidão's own cartório de registro de imóveis.

    Returns `(value, confidence, matched_label)`:

    - **alta** — exactly one registry named in the heading (after joining a
      heading split across two lines).
    - **nenhuma** — none found, or two DIFFERENT ones (see module docstring).

    There is no `baixa`: the heading either names the cartório or it does
    not, and a body mention is never this document's own registry.
    """
    linhas = _linhas_do_cabecalho(text)
    normais = [_WS.sub(" ", strip_accents_upper(_MARCAS.sub("", l))).strip() for l in linhas]
    achados: list[str] = []
    for i, norm in enumerate(normais):
        if not _CARTORIO.search(norm) or _MOBILIA.search(norm):
            continue
        # A two-column scan puts the registry in one CELL of a wider line
        # ("LIVRO Nº 2 - REGISTRO GERAL     SERVENTIA DO REGISTRO DE IMÓVEIS")
        # — the neighbouring cell is another heading item, not its name.
        celulas = [c for c in _CELULA.split(linhas[i].strip()) if c.strip()]
        propria = next(
            (c for c in celulas if _CARTORIO.search(_norm(c)) and not _MOBILIA.search(_norm(c))),
            linhas[i],
        ) if len(celulas) > 1 else linhas[i]
        partes = [propria]
        if i > 0 and _PREFIXO.match(normais[i - 1]) and not _CARTORIO.search(normais[i - 1]):
            partes.insert(0, linhas[i - 1])
        if i + 1 < len(normais) and _CONTINUACAO.match(normais[i + 1]) and not _MOBILIA.search(
            normais[i + 1]
        ):
            partes.append(linhas[i + 1])
        elif _SEM_LOCALIDADE.search(_norm(_limpar(propria))):
            localidade = _localidade_abaixo(linhas, i)
            if localidade:
                partes.append(localidade)
        valor = _limpar(" ".join(partes))
        if valor:
            achados.append(valor)

    distintos = {_WS.sub(" ", strip_accents_upper(v)) for v in achados}
    if len(distintos) != 1:
        return (None, "nenhuma", None)
    return (achados[0], "alta", "REGISTRO DE IMOVEIS")


#: A cadastral number: digits joined by `.`/`-`/`/`/space, e.g. `123.456.7-8`,
#: `23222.44.55.0100.00.000`, `012.345.0067-1`.
_NUMERO = re.compile(r"\d[\d.\-/]*\d")

#: Fewer digits than this is a lote/quadra/area number, not an inscrição.
_MIN_DIGITOS = 5

#: The block says the inscrição covers MORE than this property.
_AREA_MAIOR = re.compile(r"AREA\s+MAIOR|MAIOR\s+PORCAO|EM\s+MAIOR\s+AREA")


def find_inscricao_municipal(bloco: str) -> tuple[Optional[str], str]:
    """The inscrição out of a `CADASTRO MUNICIPAL:` block's text.

    Returns `(value, confidence)`:

    - **alta** — exactly one cadastral-shaped number in the block.
    - **baixa** — several distinct numbers (the first is returned), or the
      block says the inscrição is of an "área maior" (the number is real but
      does not identify only this unit).
    - **nenhuma** — no cadastral-shaped number ("não consta", "a cadastrar").
    """
    norm = strip_accents_upper(bloco or "")
    candidatos: list[str] = []
    for m in _NUMERO.finditer(bloco or ""):
        valor = m.group().strip(".-/ ")
        if sum(c.isdigit() for c in valor) < _MIN_DIGITOS:
            continue
        if valor not in candidatos:
            candidatos.append(valor)
    if not candidatos:
        return (None, "nenhuma")
    if len(candidatos) > 1 or _AREA_MAIOR.search(norm):
        return (candidatos[0], "baixa")
    return (candidatos[0], "alta")


__all__ = ["find_cartorio", "find_inscricao_municipal"]
