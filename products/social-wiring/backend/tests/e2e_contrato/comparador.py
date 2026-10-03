"""Generic paragraph-aligned contract comparator.

Ported (logic only — no fixture text) from a scratch investigation script
(`diff_contrato.py`) that hardcoded one reference file. This module knows
nothing about any specific contract; both paragraph lists are handed in by
the caller (`harness.py` reads them from a `.docx`/`.txt` path and from the
in-memory render).

ALGORITHM
---------
Both paragraph lists are reduced to a lowercase, accent-and-punctuation-
stripped "key" (`_chave`) and aligned with `difflib.SequenceMatcher` on the
KEYS — so a paragraph that is byte-identical in wording never shows up as a
difference just because of whitespace/capitalisation drift, and the opcode
blocks name exactly the paragraphs that differ in SUBSTANCE.

Each non-`equal` opcode block is then classified:

- `delete`  (only the reference has these paragraphs) -> `clausula_faltando`
- `insert`  (only the generated text has these)        -> `clausula_extra`
- `replace`:
    - if the blocks' normalised-whitespace CONCATENATION is identical on
      both sides, the same content was simply split across a different
      number of paragraphs -> `formatacao` (a rendering/line-break
      difference, not a content difference);
    - if it is a 1:1 pair and the two paragraphs are identical once every
      digit-run is masked -> `valor_errado` (same clause, a number/date/
      value differs — the class a contract-generation defect usually is);
    - if it is a 1:1 pair whose SequenceMatcher ratio (on the raw,
      normalised text) is still high (>= `_LIMIAR_MESMA_CLAUSULA`) -> also
      `valor_errado` (the wording drifted a little around the same value);
    - otherwise -> `clausula_faltando_e_extra` (the reference's clause(s)
      were replaced by GENUINELY different generated clause(s) — most
      often a reference-contract deviation the model doesn't express, or a
      missing clause paired with an unrelated one nearby).

This is a heuristic label on top of the raw REF/GEN paragraph text — the
raw text is always included in `Diferenca`, so a human reviewing the report
can override the label. Nothing here invents or discards data: unmatched
blocks are never dropped, only classified.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

#: Below this SequenceMatcher ratio (on normalised text, digits masked), a
#: 1:1 `replace` pair is treated as two unrelated clauses rather than "the
#: same clause with a different value".
_LIMIAR_MESMA_CLAUSULA = 0.55

_NUM_RE = re.compile(r"\d[\d.,]*")
_WS_RE = re.compile(r"\s+")


def _normalizar_espacos(texto: str) -> str:
    return _WS_RE.sub(" ", texto).strip()


def paragrafos_de_arquivo(caminho: Path) -> list[str]:
    """Non-empty, whitespace-normalised paragraphs of a `.docx` or plain
    text file. `.docx` paragraphs come from `python-docx` (already a
    backend dependency — `contrato_gerador.documento` uses it too)."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".docx":
        import docx

        texto = "\n".join(p.text for p in docx.Document(str(caminho)).paragraphs)
    else:
        texto = caminho.read_text(encoding="utf-8")
    return [_normalizar_espacos(p) for p in texto.split("\n") if p.strip()]


def paragrafos_de_lista(paragrafos: list[str]) -> list[str]:
    """Same normalisation as `paragrafos_de_arquivo`, for paragraphs
    already in memory (the in-memory render's `Renderizado.paragrafos`)."""
    return [_normalizar_espacos(p) for p in paragrafos if p.strip()]


def _chave(paragrafo: str) -> str:
    """Alignment key: lowercase, accent-stripped, non-alphanumeric
    removed, capped — digits are KEPT (a value change must still show as a
    difference, never silently align away)."""
    decomposto = unicodedata.normalize("NFKD", paragrafo)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())[:200]


def _mascarar_numeros(texto: str) -> str:
    return _NUM_RE.sub("#", texto.lower())


@dataclass
class Diferenca:
    tipo: str  # clausula_faltando | clausula_extra | valor_errado | formatacao | clausula_faltando_e_extra
    ref: list[str]
    gerado: list[str]


@dataclass
class ResultadoDiff:
    paragrafos_ref: int
    paragrafos_gerado: int
    similaridade: float
    diferencas: list[Diferenca] = field(default_factory=list)

    @property
    def identico(self) -> bool:
        return not self.diferencas

    def contagem_por_tipo(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.diferencas:
            out[d.tipo] = out.get(d.tipo, 0) + 1
        return out


def _classificar_replace(ref_bloco: list[str], gen_bloco: list[str]) -> str:
    ref_concat = _normalizar_espacos(" ".join(ref_bloco)).lower()
    gen_concat = _normalizar_espacos(" ".join(gen_bloco)).lower()
    if ref_concat == gen_concat:
        return "formatacao"
    if len(ref_bloco) == 1 and len(gen_bloco) == 1:
        a, b = ref_bloco[0], gen_bloco[0]
        if _mascarar_numeros(a) == _mascarar_numeros(b) and a != b:
            return "valor_errado"
        ratio = difflib.SequenceMatcher(None, _mascarar_numeros(a), _mascarar_numeros(b)).ratio()
        if ratio >= _LIMIAR_MESMA_CLAUSULA:
            return "valor_errado"
    return "clausula_faltando_e_extra"


def comparar(ref_paragrafos: list[str], gerado_paragrafos: list[str]) -> ResultadoDiff:
    """Paragraph-aligned diff. Never mutates its inputs; never drops a
    differing block — every non-`equal` opcode becomes exactly one
    `Diferenca`."""
    chaves_ref = [_chave(p) for p in ref_paragrafos]
    chaves_gen = [_chave(p) for p in gerado_paragrafos]
    sm = difflib.SequenceMatcher(None, chaves_ref, chaves_gen)
    resultado = ResultadoDiff(
        paragrafos_ref=len(ref_paragrafos),
        paragrafos_gerado=len(gerado_paragrafos),
        similaridade=sm.ratio(),
    )
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        ref_bloco = ref_paragrafos[i1:i2]
        gen_bloco = gerado_paragrafos[j1:j2]
        if tag == "delete":
            tipo = "clausula_faltando"
        elif tag == "insert":
            tipo = "clausula_extra"
        else:
            tipo = _classificar_replace(ref_bloco, gen_bloco)
        resultado.diferencas.append(Diferenca(tipo=tipo, ref=ref_bloco, gerado=gen_bloco))
    return resultado




# ═══════════════════════════════════════════════════════════════════════
# SCORECARD — the enforced, measured verdict (2026-10-03)
# ═══════════════════════════════════════════════════════════════════════
#
# `comparar` above is a heuristic paragraph diff that never fails. The
# scorecard below turns the same two paragraph lists into a PER-DEAL verdict
# with an exit code:
#
# - both texts are cut into SECTIONS (preamble · one per `CLÁUSULA <ord> –
#   <título>` keyed by the TITLE, not the ordinal, so a renumbering is not a
#   missing clause · the closing block from the signing-date line on) and the
#   sections are aligned by title;
# - every aligned section is scored on WORDING (word-level similarity, digits
#   masked — numbers are judged separately and exactly);
# - NUMBERS (CPF/CNPJ/CEP/R$/matrícula/protocol/any digit run) and DATES are
#   compared as multisets per section — EXACT: one unexplained number that is
#   present on one side and not the other fails the deal;
# - categories: estrutura (clauses present, by title) · qualificacao
#   (preamble wording) · matricula (the `IMÓVEL:` quote) · certidoes (the
#   certidão item labels) · redacao (every aligned section) · numeros · datas;
# - an ALLOWLIST (`allowlist.json`, versioned, PATTERNS only — never a real
#   value) names each deliberate template-vs-reference difference with a
#   reason; only entries with `aprovado_pelo_dono: true` explain anything;
# - a generated text may carry `MARCADOR_LACUNA` where the card has no value
#   yet (a not-`pronto` card rendered with explicit gap markers): whatever
#   the marker stands in for is a GAP, counted apart from wording/number
#   diffs, and the verdict is `incompleto` rather than `aprovado`.
#
# Nothing here ever returns a real value in `Scorecard.resumo()`; the
# detailed `Scorecard.detalhe()` masks digits and capitalised tokens.


#: Written into a not-`pronto` render in place of a missing printable value
#: (`harness.dados_com_marcadores`). ASCII on purpose — survives the docx
#: render and `python-docx` read-back untouched.
MARCADOR_LACUNA = "[[LACUNA]]"
#: The money sentinel a not-`pronto` render carries where a REQUIRED amount is
#: missing (the context builder refuses a `None` price — `harness.
#: dados_com_marcadores` fills it with `VALOR_LACUNA`). One centavo never
#: appears in a real instrument, so its printed form is a gap marker too.
VALOR_LACUNA = "0.01"
#: Same idea for a REQUIRED date the render cannot go without (a certidão's
#: `emitida_em`): 01/01/1900 never appears in a real instrument.
DATA_LACUNA = "1900-01-01"
#: …and for a REQUIRED day count (`termos.posse_prazo_dias` and kin).
INTEIRO_LACUNA = 999
_TOKEN_LACUNA = "lacuna_marcador"
_LACUNA_RE = re.compile(
    re.escape(MARCADOR_LACUNA)
    + r"|R\$\s*0,01(?:\s*\(um centavo\))?"
    + r"|\b0?1/0?1/1900\b|\b1º?\s+de\s+janeiro\s+de\s+1900\b"
    + r"|\b999\b(?:\s*\(novecentos e noventa e nove\))?",
    re.I,
)

_DIR = Path(__file__).resolve().parent
ALLOWLIST_PADRAO = _DIR / "allowlist.json"
LIMIARES_PADRAO = _DIR / "limiares.json"

_CABECALHO_RE = re.compile(r"^CL[ÁA]USULA\s+(.+?)\s*[–\-—:]\s*(.+)$")
_CABECALHO_SEM_TITULO_RE = re.compile(r"^CL[ÁA]USULA\s+(.+)$")
_DATA_ASSINATURA_RE = re.compile(
    r"^[A-ZÀ-Ý][\wÀ-ÿ' ]+?(?:\s*[/\-–]\s*[A-Z]{2})?,\s*\d{1,2}º?\s+de\s+[A-Za-zçÇ]+\s+de\s+\d{4}\.?$"
)
_MATRICULA_RE = re.compile(r"^IM[ÓO]VEL\s*:", re.I)
_ITEM_CERTIDAO_RE = re.compile(r"^(?:\d+\.\d+\s*[–\-—]?|[a-z]\s*-?\))\s*(.+)$")

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_DATA_NUM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_DATA_EXT_RE = re.compile(r"\b(\d{1,2})º?\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})\b", re.I)
_VALOR_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", re.I)
_CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-\d{2}\b|\b\d{11}\b")
_CEP_RE = re.compile(r"\b\d{2}\.?\d{3}-\d{3}\b")
_GENERICO_RE = re.compile(r"\d[\w.,/\-]*\d|\d")


def _dobrar(texto: str) -> str:
    """Lowercase + accent-free — a comparison form, never a stored value."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def _chave_titulo(titulo: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _dobrar(titulo)).strip()


# ─── thresholds ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Limiares:
    """Configurable pass bars. Numbers/dates default to ZERO tolerance —
    any unexplained difference fails (owner requirement)."""

    redacao_min: float = 0.90  #: mean wording similarity over aligned sections
    secao_min: float = 0.60  #: every single aligned section must reach this
    qualificacao_min: float = 0.85  #: preamble (party qualification) wording
    matricula_min: float = 0.95  #: the `IMÓVEL:` matrícula quote
    certidoes_min: float = 1.0  #: certidão item labels (multiset overlap)
    estrutura_min: float = 1.0  #: share of reference clauses present (by title)
    max_numeros_divergentes: int = 0
    max_datas_divergentes: int = 0
    falhar_em_clausula_extra: bool = True

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "Limiares":
        conhecidos = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        desconhecidos = set(dados) - conhecidos - {"_comentario"}
        if desconhecidos:
            raise ValueError(f"limiares: chaves desconhecidas {sorted(desconhecidos)}")
        return cls(**{k: v for k, v in dados.items() if k in conhecidos})

    @classmethod
    def de_arquivo(cls, caminho: Optional[Path] = None) -> "Limiares":
        caminho = Path(caminho) if caminho else LIMIARES_PADRAO
        if not caminho.is_file():
            return cls()
        return cls.de_dict(json.loads(caminho.read_text(encoding="utf-8")))


# ─── allowlist ──────────────────────────────────────────────────────────

CATEGORIAS_ALLOWLIST = ("redacao", "numero", "clausula_faltando", "clausula_extra")
_CAMPOS_OBRIGATORIOS = ("id", "categoria", "motivo", "aprovado_pelo_dono")


@dataclass(frozen=True)
class EntradaAllowlist:
    """One deliberate template-vs-reference difference.

    - `redacao` / `numero`: inside every aligned section whose title key
      matches `secao` (regex, optional), spans matching `padrao_ref` are
      removed from the reference and spans matching `padrao_gerado` from the
      generated text before scoring — the deliberate difference stops
      counting, everything around it still does.
    - `clausula_faltando`: a reference clause whose title key matches
      `padrao_ref` may be absent from the generated text.
    - `clausula_extra`: a generated clause whose title key matches
      `padrao_gerado` may be absent from the reference.

    Patterns are matched against the ACCENT-FREE LOWERCASE form of the text
    (`_dobrar`), so an entry never needs to spell a real accent/case — and
    must never carry a real name/CPF/value (`validar_allowlist` refuses
    digit runs that look like personal identifiers)."""

    id: str
    categoria: str
    motivo: str
    aprovado_pelo_dono: bool
    padrao_ref: Optional[str] = None
    padrao_gerado: Optional[str] = None
    secao: Optional[str] = None

    def aplica_a_secao(self, chave: str) -> bool:
        return self.secao is None or re.search(self.secao, chave) is not None


_PII_EM_PADRAO_RE = re.compile(r"\d{4,}|\d{3}\.\d{3}|@")


def validar_allowlist(entradas: list[dict[str, Any]]) -> list[EntradaAllowlist]:
    """Parse + validate the allowlist. Refuses (ValueError) a malformed entry
    and any pattern carrying what looks like a real identifier — the file is
    committed to a PUBLIC repo."""
    saida: list[EntradaAllowlist] = []
    ids: set[str] = set()
    for bruto in entradas:
        faltam = [c for c in _CAMPOS_OBRIGATORIOS if c not in bruto]
        if faltam:
            raise ValueError(f"allowlist: entrada {bruto.get('id')!r} sem {faltam}")
        if bruto["categoria"] not in CATEGORIAS_ALLOWLIST:
            raise ValueError(f"allowlist: categoria inválida {bruto['categoria']!r} em {bruto['id']!r}")
        if bruto["id"] in ids:
            raise ValueError(f"allowlist: id duplicado {bruto['id']!r}")
        ids.add(bruto["id"])
        if not str(bruto["motivo"]).strip():
            raise ValueError(f"allowlist: {bruto['id']!r} sem motivo")
        for campo in ("padrao_ref", "padrao_gerado", "secao"):
            valor = bruto.get(campo)
            if valor is None:
                continue
            re.compile(valor)  # a broken regex fails here, loudly
            if _PII_EM_PADRAO_RE.search(valor):
                raise ValueError(
                    f"allowlist: {bruto['id']!r}.{campo} parece conter um valor real "
                    "(sequência de dígitos/e-mail) — use um padrão (ex.: \\d+)"
                )
        if bruto["categoria"] in ("redacao", "numero") and not (bruto.get("padrao_ref") or bruto.get("padrao_gerado")):
            raise ValueError(f"allowlist: {bruto['id']!r} precisa de padrao_ref e/ou padrao_gerado")
        if bruto["categoria"] == "clausula_faltando" and not bruto.get("padrao_ref"):
            raise ValueError(f"allowlist: {bruto['id']!r} (clausula_faltando) precisa de padrao_ref")
        if bruto["categoria"] == "clausula_extra" and not bruto.get("padrao_gerado"):
            raise ValueError(f"allowlist: {bruto['id']!r} (clausula_extra) precisa de padrao_gerado")
        saida.append(
            EntradaAllowlist(
                id=bruto["id"],
                categoria=bruto["categoria"],
                motivo=bruto["motivo"],
                aprovado_pelo_dono=bool(bruto["aprovado_pelo_dono"]),
                padrao_ref=bruto.get("padrao_ref"),
                padrao_gerado=bruto.get("padrao_gerado"),
                secao=bruto.get("secao"),
            )
        )
    return saida


def carregar_allowlist(caminho: Optional[Path] = None) -> list[EntradaAllowlist]:
    caminho = Path(caminho) if caminho else ALLOWLIST_PADRAO
    if not caminho.is_file():
        return []
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return validar_allowlist(dados.get("entradas", []))


# ─── sections ───────────────────────────────────────────────────────────


@dataclass
class Secao:
    chave: str  #: "preambulo" | "clausula:<título dobrado>" | "encerramento"
    paragrafos: list[str]


def secoes(paragrafos: list[str]) -> list[Secao]:
    """Preamble · one section per clause heading · closing block (from the
    signing-date line on). A clause is keyed by its TITLE so a renumbered
    clause still aligns with its reference counterpart."""
    out: list[Secao] = [Secao("preambulo", [])]
    for p in paragrafos:
        m = _CABECALHO_RE.match(p) or _CABECALHO_SEM_TITULO_RE.match(p)
        if m and out[-1].chave != "encerramento":
            titulo = m.group(2) if m.re is _CABECALHO_RE else m.group(1)
            out.append(Secao("clausula:" + _chave_titulo(titulo), [p]))
            continue
        if _DATA_ASSINATURA_RE.match(p) and out[-1].chave != "encerramento" and len(out) > 1:
            out.append(Secao("encerramento", [p]))
            continue
        out[-1].paragrafos.append(p)
    return [s for s in out if s.paragrafos]


def _alinhar_secoes(ref: list[Secao], gen: list[Secao]) -> tuple[list[tuple[Secao, Secao]], list[Secao], list[Secao]]:
    """(pares, faltando_no_gerado, extras_no_gerado). Exact title match via
    SequenceMatcher; inside a `replace` block, titles with ratio ≥ 0.8 still
    pair (a reworded heading is a wording diff, not a missing clause)."""
    sm = difflib.SequenceMatcher(None, [s.chave for s in ref], [s.chave for s in gen], autojunk=False)
    pares: list[tuple[Secao, Secao]] = []
    faltando: list[Secao] = []
    extras: list[Secao] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pares.extend(zip(ref[i1:i2], gen[j1:j2]))
            continue
        livres = list(gen[j1:j2])
        for r in ref[i1:i2]:
            melhor, nota = None, 0.0
            for g in livres:
                n = difflib.SequenceMatcher(None, r.chave, g.chave).ratio()
                if n > nota:
                    melhor, nota = g, n
            if melhor is not None and nota >= 0.8:
                pares.append((r, melhor))
                livres.remove(melhor)
            else:
                faltando.append(r)
        extras.extend(livres)
    return pares, faltando, extras


# ─── tokens ─────────────────────────────────────────────────────────────


def _data_iso(d: str, m: str, a: str) -> Optional[str]:
    try:
        ano = int(a) + (2000 if len(a) == 2 else 0)
        return date(ano, int(m), int(d)).isoformat()
    except ValueError:
        return None


def extrair_numeros(texto: str) -> tuple[Counter, Counter]:
    """`(datas, numeros)` — multisets of NORMALISED tokens. Dates (numeric or
    "14 de setembro de 2026") become ISO; R$ values a canonical decimal;
    CPF/CNPJ/CEP digits only; any other digit run its literal form minus
    trailing punctuation. Each token is prefixed with its kind so a value
    that moved between kinds still differs."""
    datas: Counter = Counter()
    numeros: Counter = Counter()
    resto = texto

    def _tira(regex: re.Pattern, fn) -> None:
        nonlocal resto
        partes: list[str] = []
        ultimo = 0
        for m in regex.finditer(resto):
            fn(m)
            partes.append(resto[ultimo:m.start()])
            partes.append(" ")
            ultimo = m.end()
        partes.append(resto[ultimo:])
        resto = "".join(partes)

    def _data_num(m: re.Match) -> None:
        iso = _data_iso(m.group(1), m.group(2), m.group(3))
        datas["data:" + (iso or m.group(0))] += 1

    def _data_ext(m: re.Match) -> None:
        mes = _MESES.get(_dobrar(m.group(2)))
        iso = _data_iso(m.group(1), str(mes), m.group(3)) if mes else None
        if iso:
            datas["data:" + iso] += 1
        else:
            numeros["num:" + m.group(1)] += 1
            numeros["num:" + m.group(3)] += 1

    _tira(_DATA_NUM_RE, _data_num)
    _tira(_DATA_EXT_RE, _data_ext)
    _tira(_VALOR_RE, lambda m: numeros.update(["valor:" + m.group(1).replace(".", "").replace(",", ".")]))
    _tira(_CNPJ_RE, lambda m: numeros.update(["cnpj:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_CPF_RE, lambda m: numeros.update(["cpf:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_CEP_RE, lambda m: numeros.update(["cep:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_GENERICO_RE, lambda m: numeros.update(["num:" + m.group(0).rstrip(".,;-/")]))
    return datas, numeros


def _palavras(texto: str) -> list[str]:
    """Wording tokens: accent-free lowercase words, every digit run masked
    to `#` (numbers are judged exactly elsewhere), the gap marker kept as a
    single recognisable token."""
    texto = _LACUNA_RE.sub(f" {_TOKEN_LACUNA} ", texto)
    texto = re.sub(r"\d[\d.,/\-]*", "#", _dobrar(texto))
    return re.findall(r"[a-z_#]+", texto)


def _similaridade_palavras(ref: str, gen: str) -> tuple[float, int]:
    """`(ratio, palavras_em_lacuna)` — SequenceMatcher ratio over word lists,
    EXCLUDING every non-equal block whose generated side contains the gap
    marker (what the marker stands in for is a gap, not a wording diff)."""
    a, b = _palavras(ref), _palavras(gen)
    if not a and not b:
        return 1.0, 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    iguais = 0
    total = len(a) + len(b)
    em_lacuna = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            iguais += i2 - i1
        elif _TOKEN_LACUNA in b[j1:j2]:
            em_lacuna += (i2 - i1) + (j2 - j1)
    total -= em_lacuna
    if total <= 0:
        return 1.0, em_lacuna
    return (2.0 * iguais) / total, em_lacuna


def _aplicar_allowlist(texto: str, padrao: Optional[str]) -> tuple[str, int]:
    """Remove every match of `padrao` (matched on the folded form) from
    `texto`, returning the folded remainder + the hit count."""
    dobrado = _dobrar(texto)
    if not padrao:
        return dobrado, 0
    novo, n = re.subn(padrao, " ", dobrado)
    return novo, n


# ─── scorecard ──────────────────────────────────────────────────────────


@dataclass
class ResultadoSecao:
    chave: str
    redacao: float
    numeros_faltando: list[str] = field(default_factory=list)  #: tokens (kind:value) — PRIVATE
    numeros_extras: list[str] = field(default_factory=list)
    datas_faltando: list[str] = field(default_factory=list)
    datas_extras: list[str] = field(default_factory=list)
    lacunas: int = 0  #: marker occurrences in the generated section
    numeros_em_lacuna: int = 0


@dataclass
class Scorecard:
    limiares: Limiares
    secoes_ref: int
    secoes_gerado: int
    resultados: list[ResultadoSecao] = field(default_factory=list)
    clausulas_faltando: list[str] = field(default_factory=list)  #: unexplained, title keys
    clausulas_extras: list[str] = field(default_factory=list)
    clausulas_faltando_explicadas: list[str] = field(default_factory=list)
    clausulas_extras_explicadas: list[str] = field(default_factory=list)
    categorias: dict[str, Optional[float]] = field(default_factory=dict)
    allowlist_aplicadas: dict[str, int] = field(default_factory=dict)
    allowlist_pendentes: list[str] = field(default_factory=list)  #: present but not owner-approved

    # ── derived ─────────────────────────────────────────────────────────

    @property
    def numeros_divergentes(self) -> int:
        return sum(len(r.numeros_faltando) + len(r.numeros_extras) for r in self.resultados)

    @property
    def datas_divergentes(self) -> int:
        return sum(len(r.datas_faltando) + len(r.datas_extras) for r in self.resultados)

    @property
    def lacunas(self) -> int:
        return sum(r.lacunas for r in self.resultados)

    def motivos(self) -> list[str]:
        """Every failed bar, as `code` or `code:count` — no values."""
        lim = self.limiares
        m: list[str] = []
        if self.clausulas_faltando:
            m.append(f"clausula_faltando:{len(self.clausulas_faltando)}")
        if self.clausulas_extras and lim.falhar_em_clausula_extra:
            m.append(f"clausula_extra:{len(self.clausulas_extras)}")
        if self.numeros_divergentes > lim.max_numeros_divergentes:
            m.append(f"numeros_divergentes:{self.numeros_divergentes}")
        if self.datas_divergentes > lim.max_datas_divergentes:
            m.append(f"datas_divergentes:{self.datas_divergentes}")
        barras = {
            "redacao": lim.redacao_min,
            "qualificacao": lim.qualificacao_min,
            "matricula": lim.matricula_min,
            "certidoes": lim.certidoes_min,
            "estrutura": lim.estrutura_min,
        }
        for cat, minimo in barras.items():
            nota = self.categorias.get(cat)
            if nota is not None and nota + 1e-9 < minimo:
                m.append(f"{cat}_abaixo_do_limiar")
        abaixo = [r for r in self.resultados if r.redacao + 1e-9 < lim.secao_min]
        if abaixo:
            m.append(f"secoes_abaixo_do_limiar:{len(abaixo)}")
        return m

    @property
    def veredito(self) -> str:
        """`aprovado` · `reprovado` (a measured failure) · `incompleto` (no
        failure, but gaps — the card is not complete yet)."""
        if self.motivos():
            return "reprovado"
        if self.lacunas:
            return "incompleto"
        return "aprovado"

    @property
    def aprovado(self) -> bool:
        return self.veredito == "aprovado"

    def resumo(self) -> dict[str, Any]:
        """VERDICT-LEVEL ONLY — counts, ratios, codes. Safe to print/return."""
        return {
            "veredito": self.veredito,
            "motivos": self.motivos(),
            "categorias": {k: (round(v, 4) if v is not None else None) for k, v in self.categorias.items()},
            "secoes_ref": self.secoes_ref,
            "secoes_gerado": self.secoes_gerado,
            "secoes_alinhadas": len(self.resultados),
            "clausulas_faltando": len(self.clausulas_faltando),
            "clausulas_extras": len(self.clausulas_extras),
            "clausulas_explicadas_allowlist": len(self.clausulas_faltando_explicadas) + len(self.clausulas_extras_explicadas),
            "numeros_divergentes": self.numeros_divergentes,
            "datas_divergentes": self.datas_divergentes,
            "lacunas": self.lacunas,
            "numeros_em_lacuna": sum(r.numeros_em_lacuna for r in self.resultados),
            "allowlist_aplicadas": sum(self.allowlist_aplicadas.values()),
            "allowlist_pendentes": len(self.allowlist_pendentes),
        }

    def detalhe(self) -> dict[str, Any]:
        """Per-section detail for the PRIVATE scorecard file: clause title
        keys (template vocabulary), per-section ratios, and number diffs by
        KIND + count only (never the value)."""

        def _tipos(tokens: list[str]) -> dict[str, int]:
            return dict(Counter(t.split(":", 1)[0] for t in tokens))

        return {
            **self.resumo(),
            "limiares": asdict(self.limiares),
            "secoes": [
                {
                    "chave": r.chave,
                    "redacao": round(r.redacao, 4),
                    "numeros_faltando_por_tipo": _tipos(r.numeros_faltando),
                    "numeros_extras_por_tipo": _tipos(r.numeros_extras),
                    "datas_faltando": len(r.datas_faltando),
                    "datas_extras": len(r.datas_extras),
                    "lacunas": r.lacunas,
                }
                for r in self.resultados
            ],
            "clausulas_faltando_chaves": self.clausulas_faltando,
            "clausulas_extras_chaves": self.clausulas_extras,
            "allowlist_aplicadas_por_id": self.allowlist_aplicadas,
            "allowlist_pendentes_ids": self.allowlist_pendentes,
        }


def _diferenca_multiset(a: Counter, b: Counter) -> tuple[list[str], list[str]]:
    return sorted((a - b).elements()), sorted((b - a).elements())


def _item_certidao(p: str) -> Optional[str]:
    m = _ITEM_CERTIDAO_RE.match(p)
    if not m:
        return None
    texto = _dobrar(m.group(1))
    texto = re.split(r"\s[–\-—]\s*(?:n[ºo°]|protocolo)|\bn[ºo°]\s|,?\s*emitid|,?\s*expedid", texto)[0]
    texto = re.sub(r"\d[\d.,/\-]*", "#", texto)
    return re.sub(r"[^a-z#]+", " ", texto).strip() or None


def _sobreposicao(a: Counter, b: Counter) -> Optional[float]:
    if not a and not b:
        return None
    return sum((a & b).values()) / max(1, sum((a | b).values()))


def pontuar(
    ref_paragrafos: list[str],
    gerado_paragrafos: list[str],
    *,
    allowlist: Optional[list[EntradaAllowlist]] = None,
    limiares: Optional[Limiares] = None,
) -> Scorecard:
    """The measured verdict for one deal. Pure: no IO, no mutation."""
    limiares = limiares or Limiares()
    allowlist = allowlist or []
    aprovadas = [e for e in allowlist if e.aprovado_pelo_dono]
    ref_s = secoes(paragrafos_de_lista(ref_paragrafos))
    gen_s = secoes(paragrafos_de_lista(gerado_paragrafos))
    card = Scorecard(limiares=limiares, secoes_ref=len(ref_s), secoes_gerado=len(gen_s))
    card.allowlist_pendentes = sorted(e.id for e in allowlist if not e.aprovado_pelo_dono)
    aplicadas: Counter = Counter()

    pares, faltando, extras = _alinhar_secoes(ref_s, gen_s)

    for s in faltando:
        hit = next(
            (e for e in aprovadas if e.categoria == "clausula_faltando" and re.search(e.padrao_ref or "", s.chave)),
            None,
        )
        if hit:
            card.clausulas_faltando_explicadas.append(s.chave)
            aplicadas[hit.id] += 1
        else:
            card.clausulas_faltando.append(s.chave)
    for s in extras:
        hit = next(
            (e for e in aprovadas if e.categoria == "clausula_extra" and re.search(e.padrao_gerado or "", s.chave)),
            None,
        )
        if hit:
            card.clausulas_extras_explicadas.append(s.chave)
            aplicadas[hit.id] += 1
        else:
            card.clausulas_extras.append(s.chave)

    notas: dict[str, float] = {}
    pesos: dict[str, int] = {}
    for r, g in pares:
        ref_txt = " \n ".join(r.paragrafos)
        gen_txt = " \n ".join(g.paragrafos)
        ref_f, gen_f = _dobrar(ref_txt), _dobrar(gen_txt)
        for e in aprovadas:
            if e.categoria not in ("redacao", "numero") or not e.aplica_a_secao(r.chave):
                continue
            ref_f, n1 = _aplicar_allowlist(ref_f, e.padrao_ref)
            gen_f, n2 = _aplicar_allowlist(gen_f, e.padrao_gerado)
            if n1 or n2:
                aplicadas[e.id] += n1 + n2
        # `_dobrar` is idempotent, so the folded+allowlisted forms feed both
        # the wording and the number comparison.
        ratio, _ = _similaridade_palavras(ref_f, gen_f)
        lacunas = len(_LACUNA_RE.findall(gen_txt))
        d_ref, n_ref = extrair_numeros(ref_f)
        d_gen, n_gen = extrair_numeros(_LACUNA_RE.sub(" ", gen_f))
        n_falt, n_extra = _diferenca_multiset(n_ref, n_gen)
        d_falt, d_extra = _diferenca_multiset(d_ref, d_gen)
        # A gap stands in for a value: as many missing reference tokens as
        # there are markers in this section are attributed to the gaps
        # (numbers first, then dates) instead of counting as diffs.
        em_lacuna = 0
        orcamento = lacunas
        while orcamento and n_falt:
            n_falt.pop()
            orcamento -= 1
            em_lacuna += 1
        while orcamento and d_falt:
            d_falt.pop()
            orcamento -= 1
            em_lacuna += 1
        card.resultados.append(
            ResultadoSecao(
                chave=r.chave,
                redacao=ratio,
                numeros_faltando=n_falt,
                numeros_extras=n_extra,
                datas_faltando=d_falt,
                datas_extras=d_extra,
                lacunas=lacunas,
                numeros_em_lacuna=em_lacuna,
            )
        )
        peso = max(1, len(_palavras(ref_f)))
        notas[r.chave] = ratio
        pesos[r.chave] = peso

    total_peso = sum(pesos.values())
    card.categorias["redacao"] = (
        sum(notas[k] * pesos[k] for k in notas) / total_peso if total_peso else None
    )
    card.categorias["qualificacao"] = notas.get("preambulo") if any(s.chave == "preambulo" for s in ref_s) else None
    ref_clausulas = [s for s in ref_s if s.chave.startswith("clausula:")]
    presentes = len(ref_clausulas) - len(card.clausulas_faltando)
    card.categorias["estrutura"] = presentes / len(ref_clausulas) if ref_clausulas else None

    def _matricula(ss: list[Secao]) -> Optional[str]:
        for s in ss:
            for p in s.paragrafos:
                if _MATRICULA_RE.match(p):
                    return p
        return None

    m_ref, m_gen = _matricula(ref_s), _matricula(gen_s)
    if m_ref is None:
        card.categorias["matricula"] = None
    elif m_gen is None:
        card.categorias["matricula"] = 0.0
    else:
        card.categorias["matricula"] = _similaridade_palavras(m_ref, m_gen)[0]

    def _certidoes(ss: list[Secao]) -> Counter:
        itens: Counter = Counter()
        for s in ss:
            if "certid" in s.chave:
                for p in s.paragrafos:
                    rotulo = _item_certidao(p)
                    if rotulo:
                        itens[rotulo] += 1
        return itens

    card.categorias["certidoes"] = _sobreposicao(_certidoes(ref_s), _certidoes(gen_s))
    card.allowlist_aplicadas = dict(aplicadas)
    return card


# ─── CLI ─────────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    """`comparador.py --ref REF --gerado GEN [--allowlist F] [--limiares F]`
    — prints the VERDICT-LEVEL scorecard; exit 0 only when `aprovado`
    (1 = reprovado, 2 = incompleto)."""
    import argparse

    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument("--ref", type=Path, required=True, help="reference .docx/.txt")
    p.add_argument("--gerado", type=Path, required=True, help="generated .docx/.txt")
    p.add_argument("--allowlist", type=Path, default=None)
    p.add_argument("--limiares", type=Path, default=None)
    args = p.parse_args(argv)
    card = pontuar(
        paragrafos_de_arquivo(args.ref),
        paragrafos_de_arquivo(args.gerado),
        allowlist=carregar_allowlist(args.allowlist),
        limiares=Limiares.de_arquivo(args.limiares),
    )
    print(json.dumps(card.resumo(), indent=2, ensure_ascii=False))
    return {"aprovado": 0, "reprovado": 1, "incompleto": 2}[card.veredito]


__all__ = [
    "MARCADOR_LACUNA",
    "VALOR_LACUNA",
    "DATA_LACUNA",
    "INTEIRO_LACUNA",
    "Diferenca",
    "EntradaAllowlist",
    "Limiares",
    "ResultadoDiff",
    "Scorecard",
    "carregar_allowlist",
    "comparar",
    "extrair_numeros",
    "paragrafos_de_arquivo",
    "paragrafos_de_lista",
    "pontuar",
    "secoes",
    "validar_allowlist",
]


if __name__ == "__main__":
    raise SystemExit(main())
