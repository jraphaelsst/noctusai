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
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

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


__all__ = [
    "Diferenca",
    "ResultadoDiff",
    "comparar",
    "paragrafos_de_arquivo",
    "paragrafos_de_lista",
]
