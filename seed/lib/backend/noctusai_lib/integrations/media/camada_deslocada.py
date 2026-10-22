"""Detect (and undo) a font-shifted PDF text layer.

Some form PDFs (bank "Ficha Proposta") embed a font whose glyph codes are
shifted by a constant: extraction returns ``3UHoR`` for ``Preço`` and
``'$'26`` for ``DADOS``. Classification and extraction then run over
gibberish. A constant code-point shift is a Caesar cipher: when ONE shift
turns a layer with almost no Portuguese words into one with many, decode it;
when the layer is gibberish and no shift fixes it, report it so the page is
routed to OCR instead of being trusted.
"""

from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.primitives.accents import fold_accents

_PALAVRAS = frozenset(
    """a o os as de da do das dos em no na nos nas um uma uns umas e ou que se com por para
    sem sob sobre ao aos ate entre ser foi sao tem nao sim mais menos data nome cpf rg
    endereco telefone email valor preco dados proposta ficha cliente conta banco agencia
    numero estado civil renda cidade bairro cep rua avenida complemento nascimento mae pai
    profissao empresa imovel financiamento prazo parcela taxa assinatura documento tipo
    codigo sexo masculino feminino casado solteiro divorciado viuvo residencial comercial
    total mensal anual primeiro segundo participante proponente conjuge titular""".split()
)

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
MIN_TOKENS = 12
RAW_MAX_RATIO = 0.08
DECODED_MIN_RATIO = 0.35
GIBBERISH_MIN_TOKENS = 40
MIN_DISTINTOS = 10
MIN_PALAVRAS_DECODIFICADAS = 6
GIBBERISH_MAX_RATIO = 0.05


def _fold(token: str) -> str:
    return fold_accents(token).lower()


def razao_palavras(text: str) -> tuple[float, int]:
    """(ratio of pt-BR dictionary words among alphabetic tokens, token count)."""
    tokens = _TOKEN.findall(text or "")
    if not tokens:
        return (0.0, 0)
    hits = sum(1 for t in tokens if _fold(t) in _PALAVRAS)
    return (hits / len(tokens), len(tokens))


def _palavras_distintas(text: str) -> int:
    return len({_fold(t) for t in _TOKEN.findall(text or "") if _fold(t) in _PALAVRAS})


def _frac_alfa(text: str) -> float:
    sem = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in sem) / len(sem) if sem else 0.0


def _tokens_distintos(text: str) -> int:
    return len({t.lower() for t in _TOKEN.findall(text or "")})


def _deslocar(text: str, shift: int) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if 33 <= o <= 126 and 32 <= o + shift <= 0x24F:
            out.append(chr(o + shift))
        else:
            out.append(ch)
    return "".join(out)


def decifrar_camada_deslocada(text: str) -> tuple[str, Optional[int], bool]:
    """Return ``(text, shift, precisa_ocr)``.

    * clean layer -> ``(text, None, False)``
    * a single shift decodes it -> ``(decoded, shift, False)``
    * gibberish no shift fixes -> ``(text, None, True)`` (route to OCR)
    """
    raw_ratio, n = razao_palavras(text)
    # Repetitive text ("LIVRO 2. LIVRO 2. ...") is not evidence of a cipher.
    if n < MIN_TOKENS or raw_ratio > RAW_MAX_RATIO or _tokens_distintos(text) < MIN_DISTINTOS:
        return (text, None, False)
    melhor: tuple[tuple[float, float], int, str] = ((0.0, 0.0), 0, text)
    for shift in range(-96, 97):
        if shift == 0:
            continue
        cand = _deslocar(text, shift)
        ratio, _ = razao_palavras(cand)
        chave = (ratio, _frac_alfa(cand))
        if chave > melhor[0]:
            melhor = (chave, shift, cand)
    if melhor[0][0] >= DECODED_MIN_RATIO and _palavras_distintas(melhor[2]) >= MIN_PALAVRAS_DECODIFICADAS:
        return (melhor[2], melhor[1], False)
    if n >= GIBBERISH_MIN_TOKENS and raw_ratio <= GIBBERISH_MAX_RATIO:
        return (text, None, True)
    return (text, None, False)


__all__ = ["decifrar_camada_deslocada", "razao_palavras"]
