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
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
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
# - NUMBERS (CPF/CNPJ/CEP/R$/RG/matrícula/protocol/any digit run) and DATES are
#   compared as DISTINCT NORMALISED VALUES per section — EXACT on the fact (one
#   value present on one side and not the other, anywhere in the document,
#   fails the deal) but blind to format, layout and repetition: see
#   `pontuar`'s "HONEST COMPARISON" note for what is NOT a divergence;
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
    + r"|(?<![\d.,/\-])999(?!\d|[.,]\d)(?:\s*\(novecentos e noventa e nove\))?",  # not the `999` inside `9.999,00`
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
#: Lookarounds keep the bare-11-digit alternative from biting the first eleven
#: digits of a longer run — a certidão number printed `26071227382-22` is NOT a CPF.
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-\d{2}\b|(?<![\d.\-/])\d{11}(?![\d.\-/]\d)")
_CEP_RE = re.compile(r"\b\d{2}\.?\d{3}-\d{3}\b")
#: An RG as printed in a qualification (`RG 12.345.678-9-SSP-SP`, check digit
#: optional, issuing body after). Compared by its canonical form — the seed's
#: identifier registry completes the SP check digit — so a signed text that
#: omits the DV is the SAME identifier, while a different number is not.
_RG_RE = re.compile(
    r"\brg\s*(?:n[ºo°.]{0,2}\s*)?[:.]?\s*(\d[\d.]*\d(?:\s*-\s*[\dx]{1,2}(?![a-z\d]))?)(?![\d.])",
    re.I,
)
#: Alphanumeric control code (`B522.9C56.7777.FDCE`) — may START with a letter.
_CODIGO_RE = re.compile(r"\b(?:[0-9A-Z]{4}\.){3}[0-9A-Z]{4}\b", re.I)
#: Anything else with a digit: letters/dots/slashes/hyphens allowed inside
#: (`2026/000004604087`, `485E.1210.621C.0236`), the last char alphanumeric.
_GENERICO_RE = re.compile(r"\d[\w.,/\-]*\w|\d")
#: `Parcela 02: … R$ 400.000,00` — WHICH installment carries WHICH amount is a
#: fact of its own (two amounts swapped between installments pass a bare
#: set-of-values comparison), so the pair is a token too.
_PARCELA_RE = re.compile(r"(?m)^[ \t]*parcela[ \t]+0*(\d+)[ \t]*:[^\n]*?R\$[ \t]*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", re.I)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
#: A list enumerator at the start of a line (`1.10 –`, `3 -`, `2)`): layout, not a fact.
_ENUMERADOR_RE = re.compile(r"(?m)^[ \t]*\d+(?:\.\d+)*[ \t]*(?:[–\-—][ \t]+|\)[ \t]*)(?=[^\d\s])")
#: `R$ 470.000,00 (470.000,00 mil reais)` — a parenthesis that restates the
#: number right before it (a typo'd extenso) is the same fact, not a second one.
_PAREN_REPETE_RE = re.compile(r"(\d[\d.,]*\d)\s*\(\s*\1(?!\d)[^)]*\)")
_ITEM_NUMERADO_RE = re.compile(r"^\d+\.\d+\s*[–\-—]?\s*(.+)$")
#: kinds whose value is an IDENTIFIER of a person (compared in the signature
#: block only when BOTH texts print that kind — see `pontuar`).
_TIPOS_IDENTIFICADOR = ("cpf:", "rg:", "cnpj:")
_BANCARIO_GATE_RE = re.compile(r"ag[eê]ncia|conta corrente|chave pix")
_BANCARIO_SEGMENTO_RE = re.compile(r"(?:em favor d[oa]s?\s+[^:.;]{0,60}:|\bbanco\b).*?(?=operando-se|\.\s|\.$|$)")


#: A street-type word followed by a ROMAN numeral (`Rua I`, `Alameda III`, `quadra IV`):
#: the matrícula transcribes a numbered street in Roman, the signed contract in Arabic
#: (`Rua 1`) — one fact, two spellings (deal 867, 2026-10-06). ONLY after these words:
#: `Anexo I`, `Bloco I`, `Torre II`, `Fase I`, a bare pronoun-like `I` stay untouched
#: (a bloco/anexo number is the unit's identity and is compared as written). Roman
#: numerals I..XXXIX; case-insensitive because the comparison runs on folded text.
_ROMANO = r"(?:xxx|xx|x)?(?:ix|iv|v?i{0,3})"
_VIA_ROMANO_RE = re.compile(
    r"\b((?:rua|avenida|av\.?|alameda|travessa|estrada|pra[cç]a|via|viela|quadra|lote))(\s+)(" + _ROMANO + r")(?![\w])",
    re.I,
)
_ROMANOS = {"i": 1, "v": 5, "x": 10}


def _romano_para_int(r: str) -> int:
    total = 0
    r = r.lower()
    for i, c in enumerate(r):
        v = _ROMANOS[c]
        total += -v if i + 1 < len(r) and _ROMANOS[r[i + 1]] > v else v
    return total


def romanos_de_via_para_arabicos(texto: str) -> str:
    """`Rua I` → `Rua 1`, `Alameda III` → `Alameda 3` (see `_VIA_ROMANO_RE`)."""
    def _troca(m: re.Match) -> str:
        if not m.group(3):  # the optional-everything pattern can match empty
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{_romano_para_int(m.group(3))}"

    return _VIA_ROMANO_RE.sub(_troca, texto)


def _dobrar(texto: str) -> str:
    """Lowercase + accent-free — a comparison form, never a stored value."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def _chave_titulo(titulo: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _dobrar(titulo)).strip()


# ─── thresholds ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Limiares:
    """Pass bars, in TWO LAYERS (owner directive 2026-10-06: contracts need
    not be alike byte for byte — they must be similar enough to be acceptable
    on that deal's terms).

    MATERIAL layer (the only hard fail): any divergence in a material FACT
    (`max_numeros_divergentes` / `max_datas_divergentes`, zero tolerance),
    a missing material clause, a material clause that shares (almost) no
    wording with its reference (`secao_material_min`).

    OBSERVATION layer (never fails, reported): wording similarity below
    `redacao_min` / `secao_min` / `qualificacao_min` / `matricula_min` /
    `certidoes_min` / `estrutura_min`, clauses missing/extra that are not
    material, and non-material numbers. A deal with only observations reads
    `aprovado_com_observacoes`."""

    # ── material layer ──
    max_numeros_divergentes: int = 0  #: MATERIAL numbers (CPF/CNPJ/RG/CEP/R$/areas/prazos/…)
    max_datas_divergentes: int = 0  #: MATERIAL dates
    secao_material_min: float = 0.10  #: a MATERIAL clause below this shares no wording with its reference: a different clause
    # ── observation layer (informative) ──
    redacao_min: float = 0.70  #: mean wording similarity over aligned sections
    secao_min: float = 0.50  #: a single aligned section below this is reported
    qualificacao_min: float = 0.80  #: preamble (party qualification) wording
    matricula_min: float = 0.60  #: the `IMÓVEL:` matrícula quote wording
    certidoes_min: float = 0.80  #: certidão item labels (share of printed kinds the signed text lists)
    estrutura_min: float = 0.85  #: share of reference clauses present (by title)
    falhar_em_clausula_extra: bool = False  #: strict mode: an extra clause is a failure (default: an observation)

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
    #: A synthetic counterpart built from SEVERAL generated clauses: a reference
    #: clause whose content the render folded into other clauses (merged/split).
    fundida: bool = False


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
    return _reparear_por_conteudo(pares, faltando, extras)


def _corpo(sec: Secao) -> list[str]:
    return sec.paragrafos[1:] or sec.paragrafos


def _contencao(a: list[str], b: list[str]) -> float:
    """Share of the smaller word list found, in order, in the larger one."""
    wa, wb = _palavras(" ".join(a)), _palavras(" ".join(b))
    if not wa or not wb:
        return 0.0
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    return sum(blk.size for blk in sm.get_matching_blocks()) / min(len(wa), len(wb))


def _reparear_por_conteudo(
    pares: list[tuple[Secao, Secao]], faltando: list[Secao], extras: list[Secao]
) -> tuple[list[tuple[Secao, Secao]], list[Secao], list[Secao]]:
    """Order and heading wording are not structure the contract depends on
    (owner directive 2026-10-06). A reference clause the title alignment left
    unpaired is matched, in this order, to (1) a generated clause with the same
    or a near title wherever it sits (REORDERED), (2) the generated clause
    whose body reads like it (RENAMED heading), (3) the pool of unpaired
    generated clauses that contains its content (MERGED/split). Only what none
    of these finds stays missing."""
    faltando, extras = list(faltando), list(extras)
    por_conteudo: list[Secao] = []
    restantes: list[Secao] = []
    for r in faltando:
        melhor, nota = None, 0.0
        for g in extras:
            n = difflib.SequenceMatcher(None, r.chave, g.chave).ratio()
            if n > nota:
                melhor, nota = g, n
        if melhor is not None and nota >= 0.8:
            pares.append((r, melhor))
            extras.remove(melhor)
            continue
        restantes.append(r)
    faltando = []
    for r in restantes:
        melhor, nota = None, 0.0
        for g in extras:
            n = _similaridade_palavras(" ".join(_corpo(r)), " ".join(_corpo(g)))[0]
            if n > nota:
                melhor, nota = g, n
        if melhor is not None and nota >= 0.45:
            pares.append((r, melhor))
            extras.remove(melhor)
            por_conteudo.append(melhor)
        else:
            faltando.append(r)
    ainda: list[Secao] = []
    pool = extras + por_conteudo  # a clause matched by content may ALSO be the one that folded another in
    for r in faltando:
        corpo = _corpo(r)
        if pool and len(_palavras(" ".join(corpo))) >= 6 and _contencao(corpo, [p for g in pool for p in _corpo(g)]) >= 0.7:
            pares.append((r, Secao(pool[0].chave, [p for g in pool for p in g.paragrafos], fundida=True)))
        else:
            ainda.append(r)
    return pares, ainda, extras


# ─── tokens ─────────────────────────────────────────────────────────────


def _data_iso(d: str, m: str, a: str) -> Optional[str]:
    try:
        ano = int(a) + (2000 if len(a) == 2 else 0)
        return date(ano, int(m), int(d)).isoformat()
    except ValueError:
        return None


def _rg_canonico(bruto: str) -> str:
    """Canonical digits of an RG — the seed's identifier registry completes the
    SP check digit, so `12.345.678` and `12.345.678-9` are one identifier.
    Falls back to the raw alphanumerics when the registry does not know it."""
    alnum = re.sub(r"[^0-9Xx]", "", bruto).upper()
    try:
        from noctusai_lib.primitives import identificador

        canonico = identificador.canonico("rg", alnum)
    except Exception:  # noqa: BLE001 — comparison form only; the raw digits still compare exactly
        canonico = None
    return re.sub(r"[^0-9X]", "", canonico or alnum)


def _canon_generico(token: str) -> Optional[str]:
    """One canonical form for a digit-bearing token: `170,00`/`170,000`/
    `170,0` → the same decimal; `86.743` → `86743`; leading zeros of every
    digit run dropped (`04`, `0430`, `000055` ≡ `4`, `430`, `55`); a 4+-group
    registry number reads the same whatever its separators (`23253.41.85.0055.0000`
    ≡ `23253-41-85-0055-0000`). `None` for an outline reference (`1.10`,
    `2.9` — a position in the document's own numbering, not a fact)."""
    token = token.rstrip(".,;-/")
    if re.fullmatch(r"\d{1,2}\.\d{1,2}", token):
        return None
    if re.search(r"[A-Za-z]", token):  # alphanumeric control code: compared verbatim
        return "cod:" + token.upper()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+", token):
        try:
            valor = Decimal(token.replace(".", "").replace(",", ".")).normalize()
            return "dec:" + format(valor, "f")
        except InvalidOperation:
            pass
    if re.fullmatch(r"\d+\.(?:\d{1,2}|\d{4,})", token):  # dot-decimal (`153.9356`): the same number as `153,9356`
        return "dec:" + format(Decimal(token).normalize(), "f")
    if "/" not in token and len(re.split(r"[.\-]", token)) >= 4:
        # a registry number (cadastral inscription): its separators are layout and
        # a `.000` group is a group, never a thousands dot — decided BEFORE the
        # thousands-dot strip below, which would fuse `.00.000` into `.00000`.
        token = ".".join(re.split(r"[.\-]", token))
    else:
        token = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", token)
    return "num:" + re.sub(r"\d+", lambda m: m.group(0).lstrip("0") or "0", token)


def _preparar_para_numeros(texto: str) -> str:
    """Layout/format noise that is never a fact, removed BEFORE tokenising:
    e-mail addresses (their digits are not numbers), list enumerators,
    whitespace broken inside a number (`06706- 165`, `449220 / 2026`), ordinal
    indicators and area units glued to a digit, and a parenthesis that merely
    repeats the number before it."""
    texto = romanos_de_via_para_arabicos(texto)
    texto = _EMAIL_RE.sub(" ", texto)
    texto = _ENUMERADOR_RE.sub("", texto)
    texto = re.sub(r"(?<=\d)[ \t]*/[ \t]*(?=\d)", "/", texto)
    texto = re.sub(r"(?<=\d)-[ \t]+(?=\d)", "-", texto)
    texto = re.sub(r"(?<=\d)[ \t]+-(?=\d)", "-", texto)
    texto = re.sub(r"(?<=\d)[ \t]*[ªº°]", "", texto)
    texto = re.sub(r"(?<=\d)[ao](?![a-z0-9])", "", texto)  # the same ordinal after case/accent folding (`2º` → `2o`)
    texto = re.sub(r"\b(\d{1,3})((?: \d{3}){2,})\b", lambda m: m.group(1) + m.group(2).replace(" ", ""), texto)  # `59 884 041`
    texto = re.sub(r"_+", " ", texto)  # fill-in blanks (`__31__`) are layout, never part of a number
    texto = re.sub(r"(?<=\d)[ \t]*m[²2]?(?![\w²])", "", texto, flags=re.I)  # `7,07m`, `126,0m2`, `85 m²`
    return _PAREN_REPETE_RE.sub(r"\1", texto)


def extrair_numeros(texto: str) -> tuple[Counter, Counter]:
    """`(datas, numeros)` — multisets of NORMALISED tokens. Dates (numeric or
    "14 de setembro de 2026") become ISO; R$ values a canonical decimal;
    CPF/CNPJ/CEP digits only; RG its canonical form; any other digit run its
    canonical literal (decimals unified, zero-padding and thousand dots
    dropped). Each token is prefixed with its kind so a value that moved
    between kinds still differs."""
    datas: Counter = Counter()
    numeros: Counter = Counter()
    resto = _preparar_para_numeros(texto)

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
            numeros.update(t for t in (_canon_generico(m.group(1)), _canon_generico(m.group(3))) if t)

    for m in _PARCELA_RE.finditer(resto):
        numeros["parcela:" + m.group(1) + "=" + m.group(2).replace(".", "").replace(",", ".")] += 1
    _tira(_DATA_NUM_RE, _data_num)
    _tira(_DATA_EXT_RE, _data_ext)
    _tira(_VALOR_RE, lambda m: numeros.update(["valor:" + m.group(1).replace(".", "").replace(",", ".")]))
    _tira(_RG_RE, lambda m: numeros.update(["rg:" + _rg_canonico(m.group(1))]))
    _tira(_CODIGO_RE, lambda m: numeros.update(["cod:" + m.group(0).upper()]))
    _tira(_CNPJ_RE, lambda m: numeros.update(["cnpj:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_CPF_RE, lambda m: numeros.update(["cpf:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_CEP_RE, lambda m: numeros.update(["cep:" + re.sub(r"\D", "", m.group(0))]))
    _tira(_GENERICO_RE, lambda m: numeros.update(t for t in [_canon_generico(m.group(0))] if t))
    return datas, numeros


def _palavras(texto: str) -> list[str]:
    """Wording tokens: accent-free lowercase words, every digit run masked
    to `#` (numbers are judged exactly elsewhere), the gap marker kept as a
    single recognisable token."""
    texto = _LACUNA_RE.sub(f" {_TOKEN_LACUNA} ", texto)
    texto = _EMAIL_RE.sub(" ", texto)  # an address is data (test cards carry stand-ins), not wording
    texto = re.sub(r"\d[\d.,/\-]*", "#", _dobrar(texto))
    return re.findall(r"[a-z_#]+", texto)


def _contar_palavras(ref: str, gen: str) -> tuple[int, int, int]:
    """`(iguais, total, palavras_em_lacuna)` — SequenceMatcher over word lists,
    EXCLUDING every non-equal block whose generated side contains the gap
    marker (what the marker stands in for is a gap, not a wording diff).
    `total` is already net of the excluded words."""
    a, b = _palavras(ref), _palavras(gen)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    iguais = 0
    em_lacuna = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            iguais += i2 - i1
        elif _TOKEN_LACUNA in b[j1:j2]:
            em_lacuna += (i2 - i1) + (j2 - j1)
    return iguais, len(a) + len(b) - em_lacuna, em_lacuna


def _similaridade_palavras(ref: str, gen: str) -> tuple[float, int]:
    """`(ratio, palavras_em_lacuna)` — the Dice ratio of `_contar_palavras`."""
    iguais, total, em_lacuna = _contar_palavras(ref, gen)
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
    #: Tokens that differ in THIS section but whose value is present on the other
    #: side elsewhere in the document (a mention moved/repeated, not a wrong fact).
    numeros_alinhados: int = 0
    datas_alinhadas: int = 0
    #: Reference tokens the owner cannot supply in this test (favorecido bank
    #: details) and the generated text therefore lacks — an expected gap.
    dados_indisponiveis: int = 0
    #: Signature-block identifiers / signing date left out of the comparison
    #: (the generated block prints other identifier kinds / the render date).
    assinatura_excluidos: int = 0
    #: Reference certidão items the generated text has no counterpart for (the
    #: card carries no such certidão — it can only print what it has).
    certidoes_lacuna: int = 0
    #: Generated certidão items the signed text does not list (the other half of
    #: the certidões check — what the generator INVENTED rather than lacked).
    certidoes_extras: int = 0
    #: Paired items whose identifier AND emission date both differ — a newer
    #: certidão than the one the signed text lists (expected, never a failure).
    certidoes_reemitidas: int = 0
    #: Non-material number/date differences in this section (statutory
    #: citations, registry-act quotes, standard-clause numerals, certidão
    #: identifiers/dates): informative only — never a failure.
    obs_numeros: int = 0
    obs_datas: int = 0
    #: Whether the section carries a MATERIAL term (see `_SECOES_MATERIAIS_RE`).
    material: bool = False


@dataclass
class Scorecard:
    limiares: Limiares
    secoes_ref: int
    secoes_gerado: int
    resultados: list[ResultadoSecao] = field(default_factory=list)
    clausulas_faltando: list[str] = field(default_factory=list)  #: unexplained MATERIAL clauses missing, title keys
    #: Unexplained reference clauses that are not material (optional/standard/
    #: deal-specific wording): an observation, never a failure.
    clausulas_faltando_opcionais: list[str] = field(default_factory=list)
    clausulas_extras: list[str] = field(default_factory=list)
    clausulas_faltando_explicadas: list[str] = field(default_factory=list)
    #: Reference clauses the generator SWITCHED OFF for this card (a data gap:
    #: the switch is false because the card lacks the data, e.g. intermediação
    #: with no corretagem) — reported apart, never a missing-clause failure.
    clausulas_desligadas: list[str] = field(default_factory=list)
    clausulas_extras_explicadas: list[str] = field(default_factory=list)
    categorias: dict[str, Optional[float]] = field(default_factory=dict)
    allowlist_aplicadas: dict[str, int] = field(default_factory=dict)
    allowlist_pendentes: list[str] = field(default_factory=list)  #: present but not owner-approved
    #: certidão items: printed by the generator · of those, with a reference
    #: counterpart of the same label · printed by the reference.
    certidoes_itens_gerado: int = 0
    certidoes_itens_pareados: int = 0
    certidoes_itens_ref: int = 0
    #: Document-level MATERIAL checks beyond tokens (code → count): matrícula
    #: number, cartório, party names, estado civil, party street, certidões of a
    #: party the reference lists and the render omits entirely.
    materiais_documento: dict[str, int] = field(default_factory=dict)
    #: Parties with certidões in the reference and none in the render, when the
    #: card DECLARED the certidão data missing (a gap) — not a failure.
    certidoes_partes_lacuna: int = 0

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

    @property
    def numeros_alinhados(self) -> int:
        return sum(r.numeros_alinhados for r in self.resultados)

    @property
    def datas_alinhadas(self) -> int:
        return sum(r.datas_alinhadas for r in self.resultados)

    @property
    def dados_indisponiveis(self) -> int:
        return sum(r.dados_indisponiveis for r in self.resultados)

    @property
    def assinatura_excluidos(self) -> int:
        return sum(r.assinatura_excluidos for r in self.resultados)

    @property
    def certidoes_lacuna(self) -> int:
        return sum(r.certidoes_lacuna for r in self.resultados)

    @property
    def certidoes_extras(self) -> int:
        return sum(r.certidoes_extras for r in self.resultados)

    @property
    def certidoes_reemitidas(self) -> int:
        return sum(r.certidoes_reemitidas for r in self.resultados)

    @property
    def lacunas_de_dado(self) -> int:
        """Every kind of GAP (a card that is not complete yet) — none of it is
        a divergence, all of it keeps the verdict from reading `aprovado`."""
        return self.lacunas + self.dados_indisponiveis + self.certidoes_lacuna + self.certidoes_partes_lacuna + len(self.clausulas_desligadas)

    @property
    def secoes_material_ilegiveis(self) -> list[ResultadoSecao]:
        return [r for r in self.resultados if r.material and r.redacao + 1e-9 < self.limiares.secao_material_min]

    @property
    def obs_numeros(self) -> int:
        return sum(r.obs_numeros for r in self.resultados)

    @property
    def obs_datas(self) -> int:
        return sum(r.obs_datas for r in self.resultados)

    def motivos(self) -> list[str]:
        """Every failed MATERIAL term, as `code` or `code:count` — no values.
        Wording and structure never appear here (see `observacoes`)."""
        lim = self.limiares
        m: list[str] = []
        if self.clausulas_faltando:
            m.append(f"clausula_material_faltando:{len(self.clausulas_faltando)}")
        if self.clausulas_extras and lim.falhar_em_clausula_extra:
            m.append(f"clausula_extra:{len(self.clausulas_extras)}")
        if self.numeros_divergentes > lim.max_numeros_divergentes:
            m.append(f"numeros_divergentes:{self.numeros_divergentes}")
        if self.datas_divergentes > lim.max_datas_divergentes:
            m.append(f"datas_divergentes:{self.datas_divergentes}")
        for codigo, n in sorted(self.materiais_documento.items()):
            if n > 0:
                m.append(f"{codigo}:{n}")
        ilegiveis = self.secoes_material_ilegiveis
        if ilegiveis:
            m.append(f"secao_material_sem_correspondencia:{len(ilegiveis)}")
        return m

    def observacoes(self) -> list[str]:
        """Everything that differs but is NOT a material term: wording and
        structure below their floors, optional/extra clauses, non-material
        numbers. Informative; never fails a deal."""
        lim = self.limiares
        o: list[str] = []
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
                o.append(f"{cat}_abaixo_do_limiar")
        baixas = [r for r in self.resultados if r.redacao + 1e-9 < lim.secao_min]
        if baixas:
            o.append(f"secoes_redacao_baixa:{len(baixas)}")
        if self.clausulas_faltando_opcionais:
            o.append(f"clausulas_opcionais_faltando:{len(self.clausulas_faltando_opcionais)}")
        if self.clausulas_extras and not lim.falhar_em_clausula_extra:
            o.append(f"clausulas_extras:{len(self.clausulas_extras)}")
        if self.obs_numeros:
            o.append(f"numeros_nao_materiais:{self.obs_numeros}")
        if self.obs_datas:
            o.append(f"datas_nao_materiais:{self.obs_datas}")
        if self.certidoes_extras:
            o.append(f"certidoes_extras:{self.certidoes_extras}")
        return o

    @property
    def veredito(self) -> str:
        """`reprovado` (a MATERIAL term diverges) · `incompleto` (no material
        failure, but gaps — the card is not complete yet) ·
        `aprovado_com_observacoes` (material terms match; wording/structure
        differ) · `aprovado` (nothing to report)."""
        if self.motivos():
            return "reprovado"
        if self.lacunas_de_dado:
            return "incompleto"
        if self.observacoes():
            return "aprovado_com_observacoes"
        return "aprovado"

    @property
    def aceito(self) -> bool:
        """The deal's material terms match and nothing is missing."""
        return self.veredito in ("aprovado", "aprovado_com_observacoes")

    @property
    def aprovado(self) -> bool:
        return self.aceito

    def resumo(self) -> dict[str, Any]:
        """VERDICT-LEVEL ONLY — counts, ratios, codes. Safe to print/return."""
        return {
            "veredito": self.veredito,
            "motivos": self.motivos(),
            "observacoes": self.observacoes(),
            "categorias": {k: (round(v, 4) if v is not None else None) for k, v in self.categorias.items()},
            "secoes_ref": self.secoes_ref,
            "secoes_gerado": self.secoes_gerado,
            "secoes_alinhadas": len(self.resultados),
            "clausulas_faltando": len(self.clausulas_faltando),
            "clausulas_faltando_opcionais": len(self.clausulas_faltando_opcionais),
            "clausulas_extras": len(self.clausulas_extras),
            "clausulas_desligadas": len(self.clausulas_desligadas),
            "secoes_material_sem_correspondencia": len(self.secoes_material_ilegiveis),
            "obs_numeros": self.obs_numeros,
            "obs_datas": self.obs_datas,
            "certidoes_partes_lacuna": self.certidoes_partes_lacuna,
            "materiais_documento": dict(self.materiais_documento),
            "numeros_materiais_por_tipo": dict(
                Counter(t.split(":", 1)[0] for r in self.resultados for t in r.numeros_faltando + r.numeros_extras)
            ),
            "clausulas_explicadas_allowlist": len(self.clausulas_faltando_explicadas) + len(self.clausulas_extras_explicadas),
            "numeros_divergentes": self.numeros_divergentes,
            "datas_divergentes": self.datas_divergentes,
            "lacunas": self.lacunas,
            "numeros_em_lacuna": sum(r.numeros_em_lacuna for r in self.resultados),
            "numeros_alinhados": self.numeros_alinhados,
            "datas_alinhadas": self.datas_alinhadas,
            "dados_indisponiveis": self.dados_indisponiveis,
            "assinatura_excluidos": self.assinatura_excluidos,
            "certidoes_lacuna": self.certidoes_lacuna,
            "certidoes_extras": self.certidoes_extras,
            "certidoes_reemitidas": self.certidoes_reemitidas,
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
            "clausulas_desligadas_chaves": self.clausulas_desligadas,
            "allowlist_aplicadas_por_id": self.allowlist_aplicadas,
            "allowlist_pendentes_ids": self.allowlist_pendentes,
        }


def _diferenca_multiset(a: Counter, b: Counter) -> tuple[list[str], list[str]]:
    return sorted((a - b).elements()), sorted((b - a).elements())


def _rotulo_certidao(texto: str) -> Optional[str]:
    """The certidão KIND of one list item (`1.2 – Certidão Negativa … – nº …`):
    its label with identifiers/dates removed. An ordinal (`1ª`/`2ª Instância`)
    is part of the kind and survives."""
    m = _ITEM_NUMERADO_RE.match(texto)
    if not m:
        return None
    bruto = re.sub(r"(\d)\s*[ªº°]", lambda o: "ord" + chr(ord("a") + int(o.group(1))), m.group(1))
    bruto = _dobrar(bruto)
    bruto = re.split(r"\s[–\-—]\s*(?:n[ºo°]|protocolo)|\bn[ºo°]\s|,?\s*emitid|,?\s*expedid", bruto)[0]
    bruto = re.sub(r"\d[\d.,/\-]*", "#", bruto)
    return re.sub(r"[^a-z#]+", " ", bruto).strip() or None


_PESSOA_RE = re.compile(r"^\d+\s*[–\-—]\s*em nome de\s+(.+)$|^\d+\s*[–\-—]\s*(em rela[cç][aã]o ao im[oó]vel)", re.I)


def _chave_pessoa(texto: str) -> Optional[str]:
    """The person a certidão group is `Em nome de …` — letters of the first
    three words only (a trailing CPF/`Baixada` note differs between texts)."""
    m = _PESSOA_RE.match(_dobrar(texto))
    if not m:
        return None
    if m.group(2):
        return "imovel"
    return " ".join(re.findall(r"[a-z]+", m.group(1))[:3])


def _separar_itens(paragrafos: list[str]) -> tuple[list[tuple[int, str, str]], list[int]]:
    """`([(índice, rótulo, pessoa)], [índices dos demais])` — certidão list
    items (`n.m – …`, with the person heading they sit under) vs every other
    paragraph of the section."""
    itens: list[tuple[int, str, str]] = []
    resto: list[int] = []
    pessoa = ""
    for i, p in enumerate(paragrafos):
        chave = _chave_pessoa(p)
        if chave is not None:
            pessoa = chave
        rotulo = _rotulo_certidao(p)
        if rotulo:
            itens.append((i, rotulo, pessoa))
        else:
            resto.append(i)
    return itens, resto


def _tokens_de(texto_dobrado: str) -> tuple[set, set]:
    """DISTINCT `(numeros, datas)` of a folded text, gap sentinels removed."""
    datas, numeros = extrair_numeros(_LACUNA_RE.sub(" ", texto_dobrado))
    return set(numeros), set(datas)


def _parear_itens(
    ref_itens: list[tuple[int, str, str]],
    ref_textos: list[str],
    gen_itens: list[tuple[int, str, str]],
    gen_textos: list[str],
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair reference and generated certidão items by KIND within the SAME
    PERSON (a generated person name within ratio 0.75 of a reference one is
    that person): identical identifier/date sets first, then in order. What is
    left over pairs only on identical identifier/date sets (the same certidão
    filed under another heading); the rest has no counterpart. A generated
    label within 0.85 of a reference label counts as that kind. Returns
    `(pares, ref_sem_par, gen_sem_par)` as paragraph indices."""
    rotulos_ref = list(dict.fromkeys(r for _, r, _ in ref_itens))
    pessoas_ref = list(dict.fromkeys(pe for _, _, pe in ref_itens))

    def _mais_proximo(valor: str, candidatos: list[str], minimo: float) -> str:
        if valor in candidatos:
            return valor
        melhor = max(candidatos, key=lambda x: difflib.SequenceMatcher(None, valor, x).ratio(), default=None)
        if melhor and difflib.SequenceMatcher(None, valor, melhor).ratio() >= minimo:
            return melhor
        return valor

    grupos_ref: dict[tuple[str, str], list[int]] = defaultdict(list)
    grupos_gen: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r, pe in ref_itens:
        grupos_ref[(pe, r)].append(i)
    for i, r, pe in gen_itens:
        grupos_gen[(_mais_proximo(pe, pessoas_ref, 0.75), _mais_proximo(r, rotulos_ref, 0.85))].append(i)

    pares: list[tuple[int, int]] = []

    def _identicos(R: list[int], G: list[int]) -> None:
        for i in list(R):
            for j in list(G):
                if _tokens_de(ref_textos[i]) == _tokens_de(gen_textos[j]):
                    pares.append((i, j))
                    R.remove(i)
                    G.remove(j)
                    break

    sobras_ref: dict[str, list[int]] = defaultdict(list)
    sobras_gen: dict[str, list[int]] = defaultdict(list)
    for chave in list(grupos_ref) + [k for k in grupos_gen if k not in grupos_ref]:
        R, G = list(grupos_ref.get(chave, [])), list(grupos_gen.get(chave, []))
        _identicos(R, G)
        while R and G:
            pares.append((R.pop(0), G.pop(0)))
        sobras_ref[chave[1]].extend(R)
        sobras_gen[chave[1]].extend(G)
    ref_livres: list[int] = []
    gen_livres: list[int] = []
    for rotulo in list(sobras_ref) + [k for k in sobras_gen if k not in sobras_ref]:
        R, G = sobras_ref.get(rotulo, []), sobras_gen.get(rotulo, [])
        _identicos(R, G)
        ref_livres.extend(R)
        gen_livres.extend(G)
    return pares, ref_livres, gen_livres


def _segmentos_bancarios(texto_dobrado: str) -> list[str]:
    """The `em favor do VENDEDOR: <name>, CPF …, Banco …, Agência …, Conta …`
    segments of a folded text — the favorecido's bank details."""
    segmentos: list[str] = []
    for linha in texto_dobrado.split("\n"):
        if _BANCARIO_GATE_RE.search(linha):
            segmentos.extend(m.group(0) for m in _BANCARIO_SEGMENTO_RE.finditer(linha))
    return segmentos


def _sem_segmentos(texto_dobrado: str, segmentos: list[str]) -> str:
    for seg in segmentos:
        texto_dobrado = texto_dobrado.replace(seg, " ")
    return texto_dobrado


def _tira_tipos(tokens: list[str], prefixos: tuple[str, ...]) -> tuple[list[str], int]:
    mantidos = [t for t in tokens if not t.startswith(prefixos)]
    return mantidos, len(tokens) - len(mantidos)


def _retira_um(lista: list[str], prefixos: tuple[str, ...] = ()) -> bool:
    """Remove ONE token (preferring `prefixos`) — a gap stands in for it."""
    for i in range(len(lista) - 1, -1, -1):
        if not prefixos or lista[i].startswith(prefixos):
            lista.pop(i)
            return True
    return False


_PREFIXOS_GENERICOS = ("num:", "dec:", "cod:")


def _marcadores_tipados(texto: str) -> list[tuple[str, tuple[str, ...]]]:
    """`[(marcador, prefixos de token que ele pode substituir)]`. A sentinel
    names its kind (`R$ 0,01` → a value, `1900` → a date, `999` → a number);
    the generic `[[LACUNA]]` takes it from the words right before it
    (`CPF/MF [[LACUNA]]` → a CPF, `RG` → an RG, `CEP:` → a CEP, `emitida em` →
    a date) and otherwise stands for a plain number — never for an identifier
    the generated text printed (a WRONG printed RG is not a gap)."""
    saida: list[tuple[str, tuple[str, ...]]] = []
    for m in _LACUNA_RE.finditer(texto):
        marcador = m.group(0).lower()
        if "r$" in marcador:
            saida.append((marcador, ("valor:",)))
        elif "1900" in marcador:
            saida.append((marcador, ("data:",)))
        elif "999" in marcador:
            saida.append((marcador, ("num:",)))
        else:
            antes = _dobrar(texto[max(0, m.start() - 24) : m.start()])
            if re.search(r"\bcpf", antes):
                saida.append((marcador, ("cpf:",)))
            elif re.search(r"\brg\b", antes):
                # `RG [[LACUNA]]-[[LACUNA]]`: the marker after the hyphen is the
                # ISSUER, not a second RG number — it stands for words only.
                saida.append((marcador, () if antes.rstrip().endswith("-") else ("rg:",)))
            elif re.search(r"\bcep", antes):
                saida.append((marcador, ("cep:",)))
            elif re.search(r"\bcnpj", antes):
                saida.append((marcador, ("cnpj:",)))
            elif re.search(r"emitid|\bdata\b|\bem\s*$|datad", antes):
                saida.append((marcador, ("data:",)))
            else:
                saida.append((marcador, _PREFIXOS_GENERICOS))
    return saida


def _absorver_lacunas(n_falt: list[str], d_falt: list[str], marcadores: list[tuple[str, tuple[str, ...]]]) -> int:
    """Attribute each gap marker to ONE missing reference token of the kind it
    stands for. A marker with no missing token of its kind absorbs nothing (it
    stood for words). Returns how many were absorbed."""
    absorvidos = 0
    for marcador, prefixos in marcadores:
        if not prefixos:  # stands for words (an RG issuer, …), never a token
            continue
        lista = d_falt if prefixos == ("data:",) else n_falt
        if _retira_um(lista, prefixos):
            absorvidos += 1
        elif "999" in marcador and _retira_um(d_falt, ("data:",)):
            # the day-count sentinel is the posse TIMING field: the reference may
            # state it as a fixed date instead of a prazo — the same gap
            absorvidos += 1
    return absorvidos


def _realinhavel(token: str) -> bool:
    """A token is specific enough to say "the same value is stated elsewhere":
    anything but a bare small number (`1`, `02`, `10`)."""
    if token.startswith("num:"):
        return len(re.sub(r"\D", "", token)) >= 3
    return True


def _desmembrar_itens(paragrafos: list[str]) -> list[str]:
    """A PDF text layer sometimes glues two list items into one paragraph
    (`…11/08/2026; 1.10 - Pesquisa …`, or a person heading followed by its
    first item): cut them back apart."""
    saida: list[str] = []
    for p in paragrafos:
        saida.extend(x for x in re.split(r"\s+(?=\d+\.\d+\s*[–\-—]\s+[A-ZÀ-Ý])", p) if x.strip())
    return saida


# ─── material vs observation ────────────────────────────────────────────

#: Sections that carry a MATERIAL term (parties, property, price/payment,
#: posse/prazos, financing, ônus, the signing block). Everything else
#: (irretratabilidade, e-signature, foro, vistoria, mora, …) is standard
#: wording whose numerals are observations when the render adds them.
_SECOES_MATERIAIS_RE = re.compile(r"^(?:preambulo|encerramento|clausula:.*(?:objeto|preco|pagamento|posse|onus|financi))")
#: Clauses whose ABSENCE is a material failure (object, price/payment, posse,
#: ônus, the signature/parties block). Any other missing clause is optional.
#: Sections whose TERMS a render can add to: a generic number/date the render
#: states there and the reference does not is material. (In the preamble and
#: the signing block an added numeral is address/format data — a WRONG one
#: always shows as the reference's own value going missing.)
_SECOES_TERMOS_RE = re.compile(r"^clausula:.*(?:objeto|preco|pagamento|posse|onus|financi)")
_CLAUSULAS_MATERIAIS_RE = re.compile(r"^(?:encerramento|clausula:.*(?:objeto|preco|pagamento|posse|onus))")
#: Token kinds that are ALWAYS facts, in any section, on either side.
_TOKENS_ESTRITOS = ("cpf:", "rg:", "cnpj:", "cep:", "valor:", "parcela:", "dec:")
#: A statutory/clause citation (`art. 1.245`, `§ 2º`, `Lei 6.015/73`, `MP 2.200-2`,
#: `Cláusula 5`): a pointer to a norm, not a fact of the deal.
_CITACAO_LEGAL_RE = re.compile(
    # norm / clause / registry-act / title-instrument pointers
    r"(?:\blei|\bdecreto|medida provisoria|\bmp|\bart(?:igos?|s)?\b\.?|§+|\binciso|\binc\.|codigo civil|\bcpc|\bclausula"
    r"|\bcontrato|\blivro|\bfls?\b\.?|\bfolhas?|\bprotocolo|\bprenotad[oa])"
    r"\s*(?:n[o.]{0,2}\s*)?\d[\d.,/\-]*(?:\s*(?:,|e)\s*\d+)*"
    r"|\b(?:av|r)(?:\.|-)\s?\d+|\breg\.\s?\d+"  # `R-12`, `AV.10`, `Reg. 03`: a registry act of the matrícula
    # `parcelas 02 e 03` / `parcelas 1 (um), 2 (dois), e 3 (três)` in prose (the `Parcela 02:` list items are tokens of their own)
    r"|\bparcelas?\s+\d+(?:\s*\([a-z ]+\))?(?:\s*(?:,\s*e|e|,)\s*\d+(?:\s*\([a-z ]+\))?)*(?!\d)(?!\s*:)"
    # `1 (um), 2 (dois) e 3 (três) do Parágrafo …`: an enumeration of provisions
    r"|\d+\s*\([a-z ]+\)(?=(?:[,\s]|\be\b)*(?:\d+\s*\([a-z ]+\)(?:[,\s]|\be\b)*)*d[oa]s?\s+(?:paragrafo|clausula|artigo|inciso|item))"
)
_IMOVEL_F_RE = re.compile(r"^imovel\s*:")
#: A bare 1-2 digit integer (no decimals/percent/area unit/separators) and the
#: words right before it that make it part of the unit's IDENTITY.
_NUM_DESCRITIVO_RE = re.compile(r"(?<![\w.,/\-])\d{1,2}(?![\w.,/\-%]|\s*(?:%|m\b|m2|metros))")
_IDENT_ANTES_RE = re.compile(
    r"(?:\bn[o.°º]{0,2}|\bbloco|\bapto?\.?|\bapartamento|\bcasa|\blote|\bquadra|\bunidade|\bandar|\bgleba"
    r"|\bsala|\bloja|\bconjunto|\btorre)\s*[\"“”']?\s*$"
)
#: A canonical registry/cadastral number token (4+ dot-joined groups).
_REGISTRO_NUM_RE = re.compile(r"^num:\d+(?:\.\d+){3,}$")
#: Where the `IMÓVEL:` quote turns into registry-act quotes (`Conforme AV.10 …`):
#: act numbers, protocols, dates and costs after this point describe the
#: register's history — informative; areas stay material.
_CAUDA_ATOS_RE = re.compile(r"\b(?:conforme(?:\s+verifica-se)?(?:\s+n[ao])?\s+av\b|av\.?\s?\d|r-\s?\d)")
_MAT_NUM_RE = re.compile(r"matricula\s*(?:n[o.]{0,2}\s*)?[:\-]?\s*(\d[\d.]*)")
_CARTORIO_RE = re.compile(
    r"registro de imoveis d[aeo]s?\s+([a-z][a-z ]{2,40}?)(?=[,.;:)\d\-]|\s+(?:sob|em|desta|deste|ou|e)\b|$)"
)
_NOME_RE = re.compile(r"\b((?:[A-ZÀ-Ý]{2,}(?:\s+(?:[A-ZÀ-Ý]{2,}|D[AEO]S?|E)\b)+))(?=,)")
_NAO_NOME_RE = re.compile(r"^(?:RUA|AVENIDA|AV|ESTRADA|ALAMEDA|TRAVESSA|RODOVIA|PRACA|LOTE|QUADRA|CASA|APTO|BLOCO)\b")
_ESTADO_CIVIL_RE = re.compile(r"\b(solteir|casad|divorciad|viuv|separad|uniao estavel)")
_LOGRADOURO_RE = re.compile(
    r"\b(?:rua|avenida|av|alameda|travessa|estrada|rodovia|praca)\.?\s+([a-z0-9][a-z0-9 ]{2,40}?)(?=\s*,|\s+n[o.]|\s+-|\s*\d|$)"
)
_MARCADOR_NOME_RE = re.compile(r"\[\[lacuna\]\](?=,\s*(?:(?:brasileir|estrangeir)[oa]\b|\[\[))", re.I)


def _token_material(tok: str, chave: str, secao_termos: bool, lado: str) -> bool:
    """Is a differing token a MATERIAL fact? Identifiers, money, areas, CEPs and
    installments always are. A generic number/date is material when the
    reference states it and the render lacks it (a term of the deal went
    missing) — and, when the RENDER adds it, only inside a material section
    (elsewhere it is standard-clause numbering). Certidão identifiers/dates
    are observations (a newer emission is expected)."""
    if tok.startswith(_TOKENS_ESTRITOS):
        return True
    if "certid" in chave:
        return False
    return lado == "falt" or secao_termos


def _separar_observacao(texto: str, chave: str) -> tuple[str, str]:
    """`(texto_material, texto_observacao)` of a FOLDED section text: statutory
    citations and the registry-act tail of the `IMÓVEL:` quote move to the
    observation text."""
    obs: list[str] = []
    linhas: list[str] = []
    texto = romanos_de_via_para_arabicos(texto)
    texto = re.sub(r"(?<=\d)[ \t]*/[ \t]*(?=\d)", "/", texto)  # `449220 / 2026` reads as one number, like `_preparar_para_numeros`
    for linha in texto.split("\n"):
        if "objeto" in chave and _IMOVEL_F_RE.match(linha):
            m = _CAUDA_ATOS_RE.search(linha)
            if m:
                obs.append(linha[m.start():])
                linha = linha[: m.start()]
            # the descriptive text (room counts, boundary street/lot names, a
            # fixture's own number) is the registry's wording — informative; the
            # unit's identity (`casa nº 54`, `bloco 2`), areas and fractions stay material
            def _descritivo(mm: re.Match) -> str:
                if _IDENT_ANTES_RE.search(linha[max(0, mm.start() - 20) : mm.start()]):
                    return mm.group(0)
                obs.append(mm.group(0))
                return " "

            linha = _NUM_DESCRITIVO_RE.sub(_descritivo, linha)
        linhas.append(linha)

    def _tira(m: re.Match) -> str:
        obs.append(m.group(0))
        return " "

    return _CITACAO_LEGAL_RE.sub(_tira, "\n".join(linhas)), "\n".join(obs)


def _substituicoes(faltando: list[str], extras: list[str], lacunas: int) -> int:
    """Material count of a set-comparison: every missing item that has a
    DIFFERENT item printed in its place, plus every missing item with nothing
    in its place that no declared gap marker accounts for."""
    troca = min(len(faltando), len(extras))
    sem_par = len(faltando) - troca
    return troca + max(0, sem_par - lacunas)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _ausentes(ref: set[str], gen: set[str], minimo: float) -> tuple[list[str], list[str]]:
    """`(ref sem correspondente, gen sem correspondente)` by fuzzy ratio."""
    falt = [r for r in sorted(ref) if not any(_ratio(r, g) >= minimo for g in gen)]
    extra = [g for g in sorted(gen) if not any(_ratio(r, g) >= minimo for r in ref)]
    return falt, extra


#: The título-aquisitivo sentence: `A VENDEDORA, por Escritura … lavrada em
#: 04/04/2024 no 1º Tabelião de Notas de X, Livro 569, fls. 071/076, registrada
#: sob o R-12, tornou-se legítima proprietária`. Located (folded text) as the
#: stretch of a paragraph from `por <instrumento>` up to `tornou-se`.
_TITULO_FRASE_RE = re.compile(
    r"\bpor\s+(?:instrumento|escritura|formal|carta|contrato|sentenca|mandado|adjudicacao|arrematacao|permuta|termo|ato)"
    r"[^\n]*?(?=,?\s*tornou-se)"
)
_TITULO_LIVRO_RE = re.compile(r"\blivro\s*(?:n[o.]{0,2}\s*)?(\d[\w./-]*?)(?=[\s,;]|\.(?:\s|$)|$)")
_TITULO_FOLHAS_RE = re.compile(r"\b(?:fls?|folhas?)\b\.?\s*(?:n[o.]{0,2}\s*)?(\d+(?:\s*(?:/|-|a|e)\s*\d+)?)")
_TITULO_REGISTRO_RE = re.compile(r"\b(r|av)\s*[-.]?\s*(\d+)\b")
_TITULO_TABELIONATO_RE = re.compile(r"(?:(\d+)\s*o?\s*)?tabeli(?:ao|onato)")


def _canon_digitos(valor: str) -> str:
    """`071/076` == `71/76` — leading zeros are not a different folha."""
    return re.sub(r"\d+", lambda m: str(int(m.group())), re.sub(r"\s+", "", valor))


def _fatos_frase_titulo(doc: str) -> Optional[dict[str, set[str]]]:
    """Each fact of the título sentence of a FOLDED document, as its own set of
    canonical values (`None` when the document has no such sentence). Facts are
    extracted independently so one wrong fact never hides or fails another."""
    m = _TITULO_FRASE_RE.search(doc)
    if not m:
        return None
    frase = m.group()
    out: dict[str, set[str]] = {}
    out["data"] = {_canon_digitos(d) for d in re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", frase)}
    out["registro"] = {f"{a}-{int(n)}" for a, n in _TITULO_REGISTRO_RE.findall(frase)}
    out["livro"] = {_canon_digitos(x.rstrip(".,;")) for x in _TITULO_LIVRO_RE.findall(frase)}
    out["folhas"] = {_canon_digitos(x) for x in _TITULO_FOLHAS_RE.findall(frase)}
    out["tabelionato"] = {f"{n or ''} tabelionato".strip() for n in _TITULO_TABELIONATO_RE.findall(frase)}
    return {k: v for k, v in out.items() if v}


def _verificacoes_titulo(ref_doc: str, gen_doc: str) -> dict[str, int]:
    """INDIVIDUAL material checks of the título sentence (owner 2026-10-06 —
    "one check doesn't fail others when others are ok"): `mat_titulo_<fato>`
    for livro, folhas, data, registro and tabelionato, each 0/1 on its own.
    A fact counts only when BOTH sides state it and the values differ; a fact
    the render lacks (or leaves as a gap marker) is a typed gap handled by the
    gap counters, and one only the generator states is not a reference
    divergence."""
    out = {f"mat_titulo_{f}": 0 for f in ("livro", "folhas", "data", "registro", "tabelionato")}
    ref, gen = _fatos_frase_titulo(ref_doc), _fatos_frase_titulo(gen_doc)
    if ref is None or gen is None:
        return out
    for fato, valores in ref.items():
        if fato in gen and gen[fato] != valores:
            out[f"mat_titulo_{fato}"] = 1
    return out


def _verificacoes_documento(
    ref_s: list[Secao], gen_s: list[Secao], ref_doc: str, gen_doc: str, ref_orig_pre: str, gen_orig_pre: str
) -> dict[str, int]:
    """Material facts beyond number tokens. Each is a count (0 = ok)."""
    out: dict[str, int] = {}
    ref_pre, gen_pre = _dobrar(ref_orig_pre), _dobrar(gen_orig_pre)
    marc_pre = len(_LACUNA_RE.findall(gen_orig_pre))

    # matrícula number
    mr = {re.sub(r"\D", "", m).lstrip("0") for m in _MAT_NUM_RE.findall(ref_doc)} - {""}
    mg = {re.sub(r"\D", "", m).lstrip("0") for m in _MAT_NUM_RE.findall(gen_doc)} - {""}
    falt = mr - mg
    out["mat_matricula_numero"] = len(falt) if falt and (mg or not marc_pre and not _LACUNA_RE.search(gen_doc)) else 0

    # cartório (registry office city)
    cr = {c.strip() for c in _CARTORIO_RE.findall(ref_doc)}
    cg = {c.strip() for c in _CARTORIO_RE.findall(gen_doc)}
    falt_c, _ = _ausentes(cr, cg, 0.8)
    out["mat_cartorio"] = len(falt_c) if falt_c and (cg or not _LACUNA_RE.search(gen_doc)) else 0

    # party names (qualification)
    nr = {_chave_titulo(n) for n in _NOME_RE.findall(ref_orig_pre) if not _NAO_NOME_RE.match(_dobrar(n).upper())}
    ng = {_chave_titulo(n) for n in _NOME_RE.findall(gen_orig_pre) if not _NAO_NOME_RE.match(_dobrar(n).upper())}
    falt_n, _ = _ausentes(nr, ng, 0.85)
    out["mat_parte_nome"] = max(0, len(falt_n) - len(_MARCADOR_NOME_RE.findall(gen_orig_pre)))

    # estado civil
    ec_r, ec_g = Counter(_ESTADO_CIVIL_RE.findall(ref_pre)), Counter(_ESTADO_CIVIL_RE.findall(gen_pre))
    out["mat_estado_civil"] = _substituicoes(
        sorted((ec_r - ec_g).elements()), sorted((ec_g - ec_r).elements()), marc_pre
    )

    # party street
    lr = {x.strip() for x in _LOGRADOURO_RE.findall(ref_pre)}
    lg = {x.strip() for x in _LOGRADOURO_RE.findall(gen_pre)}
    falt_l, extra_l = _ausentes(lr, lg, 0.8)
    out["mat_logradouro"] = _substituicoes(falt_l, extra_l, marc_pre)

    # título-aquisitivo sentence — one check PER FACT
    out.update(_verificacoes_titulo(ref_doc, gen_doc))
    return out


def pontuar(
    ref_paragrafos: list[str],
    gerado_paragrafos: list[str],
    *,
    allowlist: Optional[list[EntradaAllowlist]] = None,
    limiares: Optional[Limiares] = None,
    clausulas_desligadas: Optional[list[str]] = None,
    certidoes_ausentes_sao_lacuna: bool = False,
) -> Scorecard:
    """The measured verdict for one deal. Pure: no IO, no mutation.

    `clausulas_desligadas`: heading TITLES of the conditional clauses the
    generator's switches turned OFF for this card (`harness.
    clausulas_desligadas`). A reference clause absent from the render whose
    title matches one of them is a DATA gap (`Scorecard.clausulas_desligadas`
    → `incompleto`), not a missing clause.

    TWO LAYERS (2026-10-06): only MATERIAL terms fail a deal (see `Limiares`
    and `_SECOES_MATERIAIS_RE` / `_token_material`); wording, structure and
    non-material numerals are `observacoes` → `aprovado_com_observacoes`.
    `certidoes_ausentes_sao_lacuna`: the card DECLARED its certidão data
    missing, so a party the reference lists certidões for and the render omits
    entirely is a gap (`incompleto`), not a failure.

    HONEST COMPARISON (2026-10-05 audit — the divergence-email lesson: ~56 %
    of "divergences" were formatting/alignment noise). A token counts as a
    DIVERGENCE only when the generated text states a different FACT. Not a
    divergence, each reported apart: format (normalised away before
    comparing), a mention present elsewhere in the document (`alinhado`), a
    gap marker/sentinel (`lacuna`), bank details the owner cannot supply
    (`dados_indisponiveis`), a certidão the card does not carry
    (`certidoes_lacuna`), and the signature block's render-time date /
    identifier kinds only one side prints (`assinatura_excluidos`)."""
    limiares = limiares or Limiares()
    allowlist = allowlist or []
    aprovadas = [e for e in allowlist if e.aprovado_pelo_dono]
    ref_paragrafos = _desmembrar_itens(paragrafos_de_lista(ref_paragrafos))
    gerado_paragrafos = _desmembrar_itens(paragrafos_de_lista(gerado_paragrafos))
    ref_s = secoes(ref_paragrafos)
    gen_s = secoes(gerado_paragrafos)
    card = Scorecard(limiares=limiares, secoes_ref=len(ref_s), secoes_gerado=len(gen_s))
    card.allowlist_pendentes = sorted(e.id for e in allowlist if not e.aprovado_pelo_dono)
    aplicadas: Counter = Counter()

    pares, faltando, extras = _alinhar_secoes(ref_s, gen_s)

    desligadas = [_chave_titulo(t) for t in clausulas_desligadas or []]

    def _desligada(chave: str) -> bool:
        titulo = chave.split(":", 1)[-1]
        return any(
            d and (titulo.startswith(d) or d in titulo or difflib.SequenceMatcher(None, d, titulo).ratio() >= 0.8)
            for d in desligadas
        )

    for s in faltando:
        if _desligada(s.chave):
            card.clausulas_desligadas.append(s.chave)
            continue
        hit = next(
            (e for e in aprovadas if e.categoria == "clausula_faltando" and re.search(e.padrao_ref or "", s.chave)),
            None,
        )
        if hit:
            card.clausulas_faltando_explicadas.append(s.chave)
            aplicadas[hit.id] += 1
        elif _CLAUSULAS_MATERIAIS_RE.match(s.chave):
            card.clausulas_faltando.append(s.chave)
        else:
            card.clausulas_faltando_opcionais.append(s.chave)
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

    def _dobrado_com_allowlist(texto: str, r_chave: str, lado: str, contar: bool) -> str:
        dobrado = _dobrar(texto)
        for e in aprovadas:
            if e.categoria not in ("redacao", "numero") or not e.aplica_a_secao(r_chave):
                continue
            dobrado, n = _aplicar_allowlist(dobrado, e.padrao_ref if lado == "ref" else e.padrao_gerado)
            if contar and n:
                aplicadas[e.id] += n
        return dobrado

    # Document-level pools: a token the OTHER side states anywhere is not a wrong
    # fact for the section it moved out of (a mention moved or repeated — an
    # alignment effect, counted apart as `alinhado`).
    n_ref_doc, d_ref_doc = _tokens_de(_dobrar("\n".join(ref_paragrafos)))
    n_gen_doc, d_gen_doc = _tokens_de(_dobrar("\n".join(gerado_paragrafos)))

    def _realinhar(lista: list[str], pool: set) -> tuple[list[str], int]:
        mantidos = [t for t in lista if not (t in pool and _realinhavel(t))]
        return mantidos, len(lista) - len(mantidos)

    notas: dict[str, float] = {}
    pesos: dict[str, int] = {}
    for r, g in pares:
        ref_par, gen_par = list(r.paragrafos), list(g.paragrafos)
        # ── certidão list items: paired by kind; their identifiers/dates are
        #    judged per PAIR, never against the whole section's pool ─────────
        ref_ign: set[int] = set()  # reference paragraphs excluded from wording AND numbers
        itens_num_ref: list[int] = []
        itens_num_gen: list[int] = []
        pares_itens: list[tuple[int, int]] = []
        gen_livres: list[int] = []
        ref_livres: list[int] = []
        if "certid" in r.chave:
            ref_it, _ = _separar_itens(ref_par)
            gen_it, _ = _separar_itens(gen_par)
            ref_tx = [_dobrar(p) for p in ref_par]
            gen_tx = [_dobrar(p) for p in gen_par]
            pares_itens, ref_livres, gen_livres = _parear_itens(ref_it, ref_tx, gen_it, gen_tx)
            itens_num_ref = [i for i, _, _ in ref_it]
            itens_num_gen = [i for i, _, _ in gen_it]
            ref_pessoas = {pe for _, _, pe in ref_it if pe}
            gen_pessoas = {pe for _, _, pe in gen_it if pe}
            sem_parte = [
                pr for pr in sorted(ref_pessoas)
                if not any(pr == g or _ratio(pr, g) >= 0.75 for g in gen_pessoas)
            ]
            # a person heading whose NAME is a gap marker stands in for a missing party
            marcados = sum(1 for p in gen_par if _chave_pessoa(p) == "lacuna")
            sem_parte = sem_parte[: max(0, len(sem_parte) - marcados)]
            if certidoes_ausentes_sao_lacuna:
                card.certidoes_partes_lacuna += len(sem_parte)
            elif sem_parte:
                card.materiais_documento["mat_certidoes_parte_ausente"] = (
                    card.materiais_documento.get("mat_certidoes_parte_ausente", 0) + len(sem_parte)
                )
            card.certidoes_itens_ref += len(ref_it)
            card.certidoes_itens_gerado += len(gen_it)
            card.certidoes_itens_pareados += len(pares_itens)
            ref_ign = set(ref_livres)  # the card carries no such certidão: a gap, not wording
        ref_resto = [p for i, p in enumerate(ref_par) if i not in ref_ign and i not in set(itens_num_ref)]
        gen_resto = [p for i, p in enumerate(gen_par) if i not in set(itens_num_gen)]
        ref_txt = "\n".join(ref_resto)
        gen_txt = "\n".join(gen_resto)
        gen_txt_total = "\n".join(gen_par)
        ref_f = _dobrado_com_allowlist(ref_txt, r.chave, "ref", True)
        gen_f = _dobrado_com_allowlist(gen_txt, r.chave, "gen", True)

        # ── favorecido bank details the owner cannot supply ─────────────────
        dados_indisp = 0
        bancarios_ref = _segmentos_bancarios(ref_f)
        if bancarios_ref and not _segmentos_bancarios(gen_f):
            ref_f = _sem_segmentos(ref_f, bancarios_ref)
            n_b, d_b = _tokens_de(" ".join(bancarios_ref))
            dados_indisp = len(n_b) + len(d_b)

        # ── wording: the section body, then each paired certidão item against
        #    ITS counterpart (a certidão list is a set — comparing it by
        #    position would score the card's person order, not its wording).
        #    A reference item with no counterpart is a gap, never wording; a
        #    generated item the signed text does not list scores 0 ─────────────
        grupos = [(ref_f, gen_f)]
        for i, j in pares_itens:
            grupos.append((_dobrado_com_allowlist(ref_par[i], r.chave, "ref", True), _dobrado_com_allowlist(gen_par[j], r.chave, "gen", True)))
        for j in gen_livres:
            grupos.append(("", _dobrado_com_allowlist(gen_par[j], r.chave, "gen", True)))
        iguais_t = total_t = 0
        for rf, gf in grupos:
            ig, tot, _ = _contar_palavras(rf, gf)
            iguais_t += ig
            total_t += tot
        ratio = 1.0 if total_t <= 0 else (2.0 * iguais_t) / total_t
        if g.fundida:  # the content lives inside other clauses: judge it by containment
            ratio = _contencao(ref_resto, gen_resto) if ref_resto else 1.0
        lacunas = len(_LACUNA_RE.findall(gen_txt_total))
        marcadores = _marcadores_tipados(gen_txt_total)

        # ── numbers/dates: DISTINCT values of the non-item paragraphs ───────
        assinatura_excl = 0
        if r.chave == "encerramento" and ref_par and gen_par:
            # the signing-date line carries the RENDER date on the generated side
            datas_ref = _tokens_de(_dobrar(ref_par[0]))[1]
            datas_gen = _tokens_de(_dobrar(gen_par[0]))[1]
            assinatura_excl += len(datas_ref | datas_gen)
            ref_corpo = [p for i, p in enumerate(ref_par) if i not in ref_ign and i != 0]
            gen_corpo = [p for i, p in enumerate(gen_par) if i != 0]
        else:
            ref_corpo = [p for i, p in enumerate(ref_par) if i not in ref_ign and i not in set(itens_num_ref)]
            gen_corpo = [p for i, p in enumerate(gen_par) if i not in set(itens_num_gen)]
        ref_num_f = _dobrado_com_allowlist("\n".join(ref_corpo), r.chave, "ref", False)
        gen_num_f = _dobrado_com_allowlist("\n".join(gen_corpo), r.chave, "gen", False)
        if bancarios_ref and dados_indisp:
            ref_num_f = _sem_segmentos(ref_num_f, bancarios_ref)
        # statutory citations + the registry-act tail leave the material text
        ref_num_f, ref_obs = _separar_observacao(ref_num_f, r.chave)
        gen_num_f, gen_obs = _separar_observacao(gen_num_f, r.chave)
        n_ref, d_ref = _tokens_de(ref_num_f)
        n_gen, d_gen = _tokens_de(gen_num_f)
        n_ref_o, d_ref_o = _tokens_de(ref_obs)
        n_gen_o, d_gen_o = _tokens_de(gen_obs)
        # areas/fractions stay material even inside a quoted act
        n_ref |= {t for t in n_ref_o if t.startswith("dec:")}
        n_gen |= {t for t in n_gen_o if t.startswith("dec:")}
        obs_n = len({t for t in n_ref_o if not t.startswith("dec:")} ^ {t for t in n_gen_o if not t.startswith("dec:")})
        obs_d = len(d_ref_o ^ d_gen_o)
        if r.chave == "encerramento":
            # identifier kinds are compared only when BOTH blocks print them
            # (the signed block lists witness RGs, the render lists CPFs)
            for pref in _TIPOS_IDENTIFICADOR:
                tem_ref = any(t.startswith(pref) for t in n_ref)
                tem_gen = any(t.startswith(pref) for t in n_gen)
                if tem_ref != tem_gen:
                    assinatura_excl += sum(1 for t in n_ref | n_gen if t.startswith(pref))
                    n_ref = {t for t in n_ref if not t.startswith(pref)}
                    n_gen = {t for t in n_gen if not t.startswith(pref)}
        n_falt, n_extra = sorted(n_ref - n_gen), sorted(n_gen - n_ref)
        d_falt, d_extra = sorted(d_ref - d_gen), sorted(d_gen - d_ref)
        n_falt, a1 = _realinhar(n_falt, n_gen_doc)
        n_extra, a2 = _realinhar(n_extra, n_ref_doc)
        d_falt, a3 = _realinhar(d_falt, d_gen_doc)
        d_extra, a4 = _realinhar(d_extra, d_ref_doc)

        # ── certidão pairs (positional by construction: never realigned): same kind, a different identifier/date is a FACT ─
        reemitidas = 0
        for i, j in pares_itens:
            ni, di = _tokens_de(_dobrar(ref_par[i]))
            nj, dj = _tokens_de(_dobrar(gen_par[j]))
            if di and dj and di != dj and ni != nj:
                # same kind, same person, another identifier AND another emission
                # date: the card holds a NEWER certidão than the one the signed
                # text listed — the render is right to print it. Counted, not failed.
                reemitidas += 1
                continue
            n_falt += sorted(ni - nj)
            n_extra += sorted(nj - ni)
            d_falt += sorted(di - dj)
            d_extra += sorted(dj - di)
        # A generated certidão the signed text does not list (nor under that
        # person) is a fact of its own: it lowers the certidões ratio and is
        # counted (`certidoes_extras`) — not inflated into one number/date
        # divergence per identifier it prints.

        if g.fundida:  # what the pooled clauses add belongs to the OTHER reference clauses
            n_extra, d_extra = [], []
        em_lacuna = _absorver_lacunas(n_falt, d_falt, marcadores)
        # ── material vs observation ────────────────────────────────────────
        mat_sec = bool(_SECOES_MATERIAIS_RE.match(r.chave))

        def _divide(tokens: list[str], lado: str) -> tuple[list[str], int]:
            mat = [t for t in tokens if _token_material(t, r.chave, bool(_SECOES_TERMOS_RE.match(r.chave)), lado)]
            return mat, len(tokens) - len(mat)

        n_falt, o1 = _divide(n_falt, "falt")
        n_extra, o2 = _divide(n_extra, "extra")
        # An identifier the render ADDS beyond those the reference states (no
        # missing identifier of the same kind in the section) is extra data,
        # not a wrong fact: a WRONG identifier always shows as a missing+extra pair.
        for pref in _TIPOS_IDENTIFICADOR + ("cep:",):
            do_tipo = [t for t in n_extra if t.startswith(pref)]
            sobra = len(do_tipo) - sum(1 for t in n_falt if t.startswith(pref))
            if sobra > 0:
                for t in do_tipo[-sobra:]:
                    n_extra.remove(t)
                o2 += sobra
        # Likewise a SECOND cadastral inscription the render prints beside the one
        # both sides state (the matrícula's own, labelled `(área maior)`): extra
        # data from the registry, not a wrong fact — a wrong inscription always
        # shows as the reference's own going missing.
        reg_extra = [t for t in n_extra if _REGISTRO_NUM_RE.match(t)]
        sobra_reg = len(reg_extra) - sum(1 for t in n_falt if _REGISTRO_NUM_RE.match(t))
        if sobra_reg > 0:
            for t in reg_extra[-sobra_reg:]:
                n_extra.remove(t)
            o2 += sobra_reg
        d_falt, o3 = _divide(d_falt, "falt")
        d_extra, o4 = _divide(d_extra, "extra")
        obs_n += o1 + o2
        obs_d += o3 + o4
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
                numeros_alinhados=a1 + a2,
                datas_alinhadas=a3 + a4,
                dados_indisponiveis=dados_indisp,
                assinatura_excluidos=assinatura_excl,
                certidoes_lacuna=len(ref_livres),
                certidoes_extras=len(gen_livres),
                certidoes_reemitidas=reemitidas,
                obs_numeros=obs_n,
                obs_datas=obs_d,
                material=mat_sec,
            )
        )
        peso = max(1, sum(len(_palavras(rf)) for rf, _ in grupos))
        notas[r.chave] = ratio
        pesos[r.chave] = peso

    total_peso = sum(pesos.values())
    card.categorias["redacao"] = (
        sum(notas[k] * pesos[k] for k in notas) / total_peso if total_peso else None
    )
    card.categorias["qualificacao"] = notas.get("preambulo") if any(s.chave == "preambulo" for s in ref_s) else None
    ref_clausulas = [s for s in ref_s if s.chave.startswith("clausula:")]
    # A switched-off clause is a data gap: out of the structure denominator.
    avaliaveis = len(ref_clausulas) - len(card.clausulas_desligadas)
    presentes = avaliaveis - len(card.clausulas_faltando) - len(card.clausulas_faltando_opcionais)
    card.categorias["estrutura"] = presentes / avaliaveis if avaliaveis > 0 else None

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

    # certidões: of what the generator PRINTED, the share whose kind the signed
    # text lists too. A reference certidão the card does not carry is a GAP
    # (counted above), never a drag on this ratio; nothing printed → not scored.
    card.categorias["certidoes"] = (
        card.certidoes_itens_pareados / card.certidoes_itens_gerado if card.certidoes_itens_gerado else None
    )
    card.allowlist_aplicadas = dict(aplicadas)
    ref_doc = _dobrar("\n".join(ref_paragrafos))
    gen_doc = _dobrar("\n".join(gerado_paragrafos))
    pre_ref = next((s.paragrafos for s in ref_s if s.chave == "preambulo"), [])
    pre_gen = next((s.paragrafos for s in gen_s if s.chave == "preambulo"), [])
    for codigo, n in _verificacoes_documento(
        ref_s, gen_s, ref_doc, gen_doc, "\n".join(pre_ref), "\n".join(pre_gen)
    ).items():
        if n:
            card.materiais_documento[codigo] = card.materiais_documento.get(codigo, 0) + n
    return card


# ─── CLI ─────────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    """`comparador.py --ref REF --gerado GEN [--allowlist F] [--limiares F]`
    — prints the VERDICT-LEVEL scorecard; exit 0 when `aprovado` or `aprovado_com_observacoes`
    (1 = reprovado, 2 = incompleto; `aprovado_com_observacoes` exits 0)."""
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
    return {"aprovado": 0, "aprovado_com_observacoes": 0, "reprovado": 1, "incompleto": 2}[card.veredito]


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
