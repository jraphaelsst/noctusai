"""The shared labelled-box matcher — `RÓTULO: valor` (or `RÓTULO valor`, no
colon) same-line/next-line resolution, common to every "printed as a
labelled box, not a table row" document reader in this package
(`cartao_cnpj.py`, `financiamento_imobiliario.py`, `guia_itbi.py`).

🔴 WHY THIS EXISTS — THE SAME MATCHER WAS HAND-COPIED 3 TIMES AND DRIFTED
-------------------------------------------------------------------------
`cartao_cnpj._campo`, `financiamento_imobiliario._campo` and
`guia_itbi._campo` all did the same job (find a box's label, cut its value
at the next known label, fall back to the box's own next line) with
independently hand-maintained copies — and the copies had ALREADY drifted
measurably (883, 2026-09-27/28) before this module existed:

- only `financiamento_imobiliario` had `_dentro_de_rotulo_maior` — a guard
  against a label that is a genuine SUBSTRING of a LONGER label belonging
  to a DIFFERENT field ("PRECO DE VENDA DO IMOVEL", `valor_compra_venda`,
  sits inside Itaú's "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO
  IMOVEL", `valor_financiado`) — `guia_itbi` had no such guard at all;
- all three used a bare `linha.find(rotulo)` to LOCATE the field's own
  label — only the FIRST occurrence on a line was ever considered, so a
  guarded (or otherwise inadmissible) first occurrence made the whole line
  a dead end even when a second, genuinely admissible, occurrence sat
  later on the SAME line;
- synonym try-order was hand-maintained data, and hand-maintained order
  drifts: `financiamento_imobiliario`'s own `data_documento` tuple listed
  the bare "DATA" BEFORE its own specific synonyms, so the specific ones
  were never reached once "DATA" matched first (`prazo_meses`'s bare
  "PRAZO" had already needed the identical reordering fix once);
- none of the three used WORD-BOUNDARY matching, for the label itself or
  for "cut the value at the next known label" — a bare label like "BANCO"
  matches literally INSIDE another word ("CREDOR: ITAÚ UNIBANCO" cuts the
  bank name at the "BANCO" sitting inside "UNIBANCO"), and the very same
  hole lets a bare cutoff label swallow a value whose own text merely
  CONTAINS that label glued to neighbouring text with no real separator
  (a vision-transcription artifact — whitespace between two words is not
  guaranteed to survive transcription).

This module is the ONE canonical implementation those three drifted
copies migrate onto. `campo` (the public entry point) folds in every fix
above: the other-field-longer-label guard, generalised to ANY field (not
just `financiamento_imobiliario`'s original one); scanning EVERY
occurrence on a line before giving up on it; trying synonyms
LONGEST-FIRST (so a bare label can never shadow a more specific one,
whatever order a caller happens to declare them in); and word-boundary
matching everywhere a label is located, including inside the "cut the
value here" cutoff search.

Masked-value tokens differ per document family (`cartao_cnpj`'s literal
`********`; `financiamento_imobiliario`/`guia_itbi`'s `[ILEGÍVEL]`/`[EM
BRANCO]`) — `valores_mascarados` takes the caller's own set rather than
this module guessing one. The document-title hazard
(`cartao_cnpj._TITULO_DOCUMENTO`, a label that is itself a substring of
the document's own printed title) is likewise opt-in via
`titulo_documento`; the other two document families have no such title
to guard against, so they simply never pass one.

`temperar_alta_por_fonte`, `data_br`, `percentual` and `pessoas_com_cpf`
are the sibling small parsers that had ALSO drifted into 2-3 identical
copies across these same three files — folded in here because their
semantics were already byte-identical (never silently changed; see each
function's own docstring for exactly what it preserves).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Callable, Optional, Sequence, TypeVar

from noctusai_lib.integrations.documents.cpf import format_cpf as _format_cpf, is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

T = TypeVar("T")

# ─── word-boundary primitives ──────────────────────────────────────────────


def _inicio_de_palavra(linha: str, pos: int) -> bool:
    """Is `pos` a genuine word START in `linha` — position 0, or the
    character immediately before it is not alphanumeric?"""
    return pos <= 0 or not linha[pos - 1].isalnum()


def _fim_de_palavra(linha: str, pos: int) -> bool:
    """Is `pos` a genuine word END in `linha` — end of string, or the
    character AT `pos` is not alphanumeric?"""
    return pos >= len(linha) or not linha[pos].isalnum()


def _proxima_ocorrencia_com_limite(linha: str, busca: int, alvo: str) -> Optional[int]:
    """The next position `>= busca` where `alvo` occurs in `linha` as a
    genuine WORD (or phrase) — never a match sitting INSIDE a longer word
    ("BANCO" inside "UNIBANCO"). `None` when no further such occurrence
    exists."""
    while True:
        achado = linha.find(alvo, busca)
        if achado < 0:
            return None
        if _inicio_de_palavra(linha, achado) and _fim_de_palavra(linha, achado + len(alvo)):
            return achado
        busca = achado + 1


def _comeca_com_rotulo(linha: str, rotulo: str) -> bool:
    """Does `linha` start with `rotulo` as a genuine word/phrase — never a
    prefix match that is really the start of a longer, different word?"""
    return linha.startswith(rotulo) and _fim_de_palavra(linha, len(rotulo))


# ─── the other-field-longer-label guard ────────────────────────────────────


def embutido_em_rotulo_maior(
    linha: str, pos: int, rotulo: str, maiores: Sequence[str]
) -> bool:
    """Is this occurrence of `rotulo` at `pos` actually covered by an
    occurrence of one of `maiores` — a LONGER label belonging to a
    DIFFERENT field — at ANY position, not just as a tail/prefix? Checked
    against every candidate in `maiores` so a shorter label never steals a
    longer sibling's own value regardless of where inside it sits. Both
    the outer and inner occurrences are word-boundary matched."""
    fim = pos + len(rotulo)
    for maior in maiores:
        busca = 0
        while True:
            p = _proxima_ocorrencia_com_limite(linha, busca, maior)
            if p is None:
                break
            if p <= pos and p + len(maior) >= fim:
                return True
            busca = p + 1
    return False


def embutido_no_titulo(linha: str, pos: int, titulo_documento: Optional[str]) -> bool:
    """Is this occurrence at `pos` actually sitting inside an occurrence of
    the document's own printed title (`titulo_documento`) — a title that
    happens to contain a real field's label as a literal substring? `None`
    (no title known for this document family) always answers `False`.
    Positional, plain-substring (never word-boundaried — a title is a
    long, specific phrase; requiring a boundary here would only weaken
    the check for no benefit)."""
    if not titulo_documento:
        return False
    inicio = 0
    while True:
        k = linha.find(titulo_documento, inicio)
        if k < 0:
            return False
        if k <= pos < k + len(titulo_documento):
            return True
        inicio = k + 1


# ─── the shared box matcher ─────────────────────────────────────────────────


def proxima_ocorrencia(
    linha: str,
    busca: int,
    rotulo: str,
    todos_rotulos: Sequence[str],
    sinonimos: Sequence[str] = (),
    *,
    titulo_documento: Optional[str] = None,
) -> Optional[int]:
    """The next position `>= busca` in `linha` where `rotulo` genuinely
    starts a box's OWN label — a word-boundaried match that is never a
    position sitting inside a longer label belonging to ANOTHER field
    (`embutido_em_rotulo_maior`, excluding every label in `sinonimos` —
    `rotulo`'s own synonym family — from the "another field" candidate
    set) or inside the document's own printed title
    (`embutido_no_titulo`). `None` when no further admissible occurrence
    exists on this line."""
    maiores = tuple(
        o
        for o in todos_rotulos
        if o != rotulo and o not in sinonimos and len(o) > len(rotulo) and rotulo in o
    )
    while True:
        achado = _proxima_ocorrencia_com_limite(linha, busca, rotulo)
        if achado is None:
            return None
        if not embutido_em_rotulo_maior(
            linha, achado, rotulo, maiores
        ) and not embutido_no_titulo(linha, achado, titulo_documento):
            return achado
        busca = achado + 1


def resolver_valor_caixa(
    linhas: list[str],
    i: int,
    linha: str,
    idx: int,
    rotulo: str,
    todos_rotulos: Sequence[str],
    *,
    valores_mascarados: Sequence[str] = (),
    titulo_documento: Optional[str] = None,
) -> tuple[Optional[str], bool]:
    """`(valor, mascarado)` for the box whose label starts at
    `linha[idx : idx + len(rotulo)]`. Tries, in order: same line (colon or
    not, cut off at the next KNOWN label — word-boundary matched, so a cut
    -candidate label glued to neighbouring text with no real separator
    never fires — so two concatenated boxes never bleed into each other),
    then the next non-blank line that does not itself start a DIFFERENT
    box (`_comeca_com_rotulo`) and is not the document's own title line.
    `mascarado` is `True` only when the box's own resolved text is one of
    `valores_mascarados` verbatim — distinct from "blank"/"never found"."""
    resto = linha[idx + len(rotulo) :].lstrip(" :").rstrip()
    corte = len(resto)
    for outro in todos_rotulos:
        if outro == rotulo:
            continue
        p = _proxima_ocorrencia_com_limite(resto, 0, outro)
        if p is not None:
            corte = min(corte, p)
    resto = resto[:corte].strip(" :")

    if resto in valores_mascarados:
        return (None, True)
    if resto:
        return (resto, False)

    for prox in linhas[i + 1 :]:
        if titulo_documento is not None and prox == titulo_documento:
            break
        if any(o != rotulo and _comeca_com_rotulo(prox, o) for o in todos_rotulos):
            break
        if prox in valores_mascarados:
            return (None, True)
        if prox:
            return (prox, False)
    return (None, False)


def campo(
    linhas: list[str],
    sinonimos: Sequence[str],
    *,
    todos_rotulos: Sequence[str],
    valores_mascarados: Sequence[str] = (),
    titulo_documento: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo encontrado, mascarado)` for the FIRST admissible
    occurrence (document order) of the first synonym — tried
    LONGEST-FIRST, never in `sinonimos`'s own declared order — that
    matches a box in `linhas`. A single-label field calls this with a
    one-element `sinonimos` (`(rotulo,)`); `cartao_cnpj`'s own
    `situacao_cadastral` field does NOT use this function — see
    `cartao_cnpj._campo_situacao_cadastral` for why a first-occurrence
    -wins contract is unsafe for that one field."""
    achado = localizar(
        linhas, sinonimos, todos_rotulos=todos_rotulos, titulo_documento=titulo_documento
    )
    if achado is None:
        return (None, None, False)
    i, idx, rotulo = achado
    valor, mascarado = resolver_valor_caixa(
        linhas,
        i,
        linhas[i],
        idx,
        rotulo,
        todos_rotulos,
        valores_mascarados=valores_mascarados,
        titulo_documento=titulo_documento,
    )
    return (valor, rotulo, mascarado)


def localizar(
    linhas: list[str],
    sinonimos: Sequence[str],
    *,
    todos_rotulos: Sequence[str],
    titulo_documento: Optional[str] = None,
) -> Optional[tuple[int, int, str]]:
    """`(índice da linha, posição na linha, rótulo)` of the box `campo`
    would read — same LONGEST-FIRST synonym order, same admissibility
    guards — without resolving its value. For a caller that needs the
    label's own POSITION (a columnar layout, see `valor_em_coluna`)."""
    for rotulo in sorted(sinonimos, key=len, reverse=True):
        for i, linha in enumerate(linhas):
            idx = proxima_ocorrencia(
                linha, 0, rotulo, todos_rotulos, sinonimos, titulo_documento=titulo_documento
            )
            if idx is not None:
                return (i, idx, rotulo)
    return None


def linhas_unidas(linhas: list[str]) -> list[str]:
    """Every pair of consecutive lines joined by one space — `linha[k] + " "
    + linha[k+1]`. A text layer wraps prose wherever the page width falls,
    so a label can be split across the break ("... E VALOR DA" /
    "TRANSAÇÃO: R$ ..."): no single line carries it, every joined pair
    that straddles the break does. A second-pass input for a label the
    line-by-line pass never found — never the first pass (a pair repeats
    each line twice, so its own document order is not the page's)."""
    return [f"{a} {b}" for a, b in zip(linhas, linhas[1:])]


def _tem_digito(linha: str) -> bool:
    return any(c.isdigit() for c in linha)


def valor_em_coluna(
    linhas: list[str],
    i: int,
    *,
    eh_rotulo_do_tipo: Callable[[str], bool],
    eh_valor_do_tipo: Callable[[str], bool],
) -> tuple[Optional[str], bool]:
    """`(valor, em_coluna)` for the label on `linhas[i]` when the text layer dumped a
    ROW of boxes as a COLUMN: a run of digit-free label lines, then a run
    of value lines (every one carrying a digit), in the same order.

    The two runs rarely have the same length — a blank box prints nothing,
    a checkbox prints a bare "X", a free-text value carries no digit and
    reads as a label — so position-in-run is NOT trusted on its own.
    Instead only the labels of ONE TYPE (`eh_rotulo_do_tipo`, e.g. money
    labels) are paired, in order, with the values of that SAME type
    (`eh_valor_do_tipo`, e.g. an `R$` amount), and only when the two
    counts are EQUAL — any mismatch is ambiguity, answered with `None`,
    never a guess. `None` too when `linhas[i]` itself carries a digit
    (its value sits on its own line — not a columnar dump) or is not a
    label of the type.

    `em_coluna` is `True` whenever the label's run holds TWO OR MORE
    labels of the type — the row WAS dumped as a column, so the line right
    after the label belongs to the run's FIRST box, not this one: a caller
    must not fall back to a next-line read then, even when `valor` is
    `None`."""
    if i < 0 or i >= len(linhas) or _tem_digito(linhas[i]):
        return (None, False)
    inicio = i
    while inicio > 0 and linhas[inicio - 1] and not _tem_digito(linhas[inicio - 1]):
        inicio -= 1
    fim = i
    while fim + 1 < len(linhas) and linhas[fim + 1] and not _tem_digito(linhas[fim + 1]):
        fim += 1
    valores: list[str] = []
    k = fim + 1
    while k < len(linhas) and linhas[k] and _tem_digito(linhas[k]):
        valores.append(linhas[k])
        k += 1
    rotulos_tipo = [j for j in range(inicio, fim + 1) if eh_rotulo_do_tipo(linhas[j])]
    valores_tipo = [v for v in valores if eh_valor_do_tipo(v)]
    em_coluna = len(rotulos_tipo) >= 2
    if i not in rotulos_tipo or len(rotulos_tipo) != len(valores_tipo):
        return (None, em_coluna)
    return (valores_tipo[rotulos_tipo.index(i)], em_coluna)


# ─── shared small parsers (identical across the 3 callers — see the module
# header) ────────────────────────────────────────────────────────────────


def temperar_alta_por_fonte(
    confidence: ExtractionConfidence, source: TextSource
) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — the shared
    "not a text layer ⇒ not alta" tempering every reader in this family
    applies to every field except money ones (which use their own,
    document-specific confidence rule instead)."""
    if confidence is ExtractionConfidence.ALTA and source is not TextSource.TEXT_LAYER:
        return ExtractionConfidence.BAIXA
    return confidence


_DATA_BR_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def data_br(txt: Optional[str]) -> Optional[date]:
    """A `dd/mm/yyyy` date, wherever it sits inside `txt` — `None` for a
    blank/missing/out-of-range input, never a raised exception."""
    if not txt:
        return None
    m = _DATA_BR_RE.search(txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


_PERCENTUAL_RE = re.compile(r"(\d+(?:,\d+)?)\s*%")


def percentual(txt: Optional[str]) -> Optional[Decimal]:
    """A `NN,N%`-shaped percentage, wherever it sits inside `txt` — `None`
    for a blank/missing/unparseable input."""
    if not txt:
        return None
    m = _PERCENTUAL_RE.search(txt)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", "."))
    except Exception:  # noqa: BLE001 - a malformed number is simply unreadable
        return None


_NOME_CPF_RE = re.compile(
    r"([^;]+?)\s*[-–—:]\s*CPF\s*[:\-]?\s*(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})",
    re.IGNORECASE,
)


def pessoas_com_cpf(
    valor: Optional[str], criar: Callable[[Optional[str], str, bool], T]
) -> tuple[T, ...]:
    """`valor`'s `;`-separated "Nome - CPF: 000.000.000-00" entries →
    `criar(nome, cpf_formatado, cpf_valido)` for each one whose CPF
    formats cleanly (an unformattable CPF drops that ENTRY, never the
    whole read). `criar` is each caller's OWN dataclass constructor
    (`financiamento_imobiliario.PessoaFinanciamento`,
    `guia_itbi.PessoaItbi`, ...) — this function's job is only the shared
    parsing, never which type the result carries."""
    if not valor:
        return ()
    pessoas: list[T] = []
    for parte in valor.split(";"):
        # EVERY "Nome - CPF" pair in the part, not only the first: a text
        # layer (no prompt to obey) joins two people with " E " — "FULANO
        # - CPF: ... E BELTRANA - CPF: ..." (Embu das Artes guide,
        # measured 2026-10-03). The connector is dropped off the NEXT
        # name's front; a real name never starts with a bare "E".
        for m in _NOME_CPF_RE.finditer(parte):
            nome = re.sub(r"^(?:E|AND)\s+", "", m.group(1).strip(" ,."), flags=re.IGNORECASE)
            nome = nome.strip(" ,.") or None
            cpf_bruto = m.group(2)
            cpf_fmt = _format_cpf(cpf_bruto)
            if cpf_fmt is None:
                continue
            pessoas.append(criar(nome, cpf_fmt, _cpf_is_valid(cpf_bruto)))
    return tuple(pessoas)


# ─── names ↔ CPFs printed apart (2026-10-03, measured) ────────────────────
# A bank proposta letter and a vision-read Guia de ITBI often print the
# people's NAMES on one line and their CPFs on another ("CONTRIBUINTE: A e
# B" / "CPF/CNPJ: x / y"), or a name beside a BLANK CPF ("ADQUIRENTE: A -
# CPF/CNPJ: [EM BRANCO]") — shapes `pessoas_com_cpf`'s "Nome - CPF: ..."
# parser never sees. These helpers are the one pairing rule both readers
# use: a name is paired with a CPF only when the two lists have the SAME
# length; otherwise the names stand alone (a caller matches them strictly).

#: A CPF token — formatted or bare 11 digits — never part of a CNPJ
#: ("12.345.678/0001-90") or a longer digit run.
_CPF_TOKEN_RE = re.compile(r"(?<![\d./-])(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?![\d./-])")


def limpar_nome(nome: Optional[str]) -> Optional[str]:
    """Trim punctuation off both ends and collapse whitespace — `None` for
    a blank or a masked-value token."""
    limpo = " ".join((nome or "").strip(" .,;:!-–—").split())
    if not limpo or limpo.startswith("["):
        return None
    return limpo


def cpfs_em(texto: Optional[str]) -> list[str]:
    """Every CPF-shaped token in `texto`, in order. A masked CPF
    ("***.456.789-**") or a CNPJ is no CPF."""
    return _CPF_TOKEN_RE.findall(texto or "")


def separar_nomes(texto: Optional[str], n_cpfs: int) -> list[str]:
    """The names in one printed list. `;` always separates; " E " (the
    Portuguese "and") separates when that yields exactly one name per CPF,
    or when every part still has at least two words (a bare " E " also
    occurs inside names) — then a CPF count that disagrees leaves the names
    UNPAIRED (`parear_nomes_cpfs`), never one CPF glued to two people."""
    nomes = [n for parte in (texto or "").split(";") if (n := limpar_nome(parte))]
    if len(nomes) != 1:
        return nomes
    partes = [n for p in nomes[0].split(" E ") if (n := limpar_nome(p))]
    if len(partes) < 2:
        return nomes
    if n_cpfs and len(partes) == n_cpfs:
        return partes
    return partes if all(len(p.split()) >= 2 for p in partes) else nomes


def parear_nomes_cpfs(
    nomes: Sequence[str],
    cpfs: Sequence[str],
    criar: Callable[[Optional[str], str, bool], T],
) -> tuple[T, ...]:
    """`criar(nome, cpf_formatado, cpf_valido)` per name↔CPF, in order —
    ONLY when the two lists have the same length (never a guess at which
    CPF is whose). `()` otherwise."""
    if not cpfs or len(nomes) != len(cpfs):
        return ()
    pessoas: list[T] = []
    for nome, cpf_bruto in zip(nomes, cpfs):
        cpf_fmt = _format_cpf(cpf_bruto)
        if cpf_fmt is None:
            return ()
        pessoas.append(criar(nome, cpf_fmt, _cpf_is_valid(cpf_bruto)))
    return tuple(pessoas)
