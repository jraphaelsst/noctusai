"""A company's Receita `situação cadastral` — ONE closed vocabulary, shared
by every reader that can produce this field.

Extracted out of `cartao_cnpj.py` (2026-09-30) at the moment a SECOND
independent source started needing it: `cnpj_registry` (a public-CNPJ-API
lookup, `noctusai_lib.integrations.cnpj_registry`) reads the exact same
five-word Receita vocabulary off a JSON field instead of a scanned document
box, but must normalise to the SAME snake_case strings — social-wiring's
`empresas.situacao_cadastral` CHECK-adjacent vocabulary (migration 167
§A.1: `'ativa' | 'baixada' | 'inapta' | 'suspensa' | 'nula'`, mirrored in
`contrato_gerador.politica.SITUACOES_CADASTRAIS`) has exactly one meaning
regardless of which document/API produced the reading. Two independent
normalisers would only ever be a bug waiting to happen the day one of them
drifts from the DB's own vocabulary; this module is the one place both
`cartao_cnpj.parse_cartao_cnpj` and `cnpj_registry`'s mappers defer to.
"""
from __future__ import annotations

import re
from typing import Optional

#: Keys are how the Receita prints it (upper-case, unaccented — every one
#: of these five words happens to carry no accent, so no accent-stripping
#: is needed here); values are the closed snake_case vocabulary the DB
#: column (and every consumer of `situacao_cadastral`) actually stores.
VOCABULARIO: dict[str, str] = {
    "ATIVA": "ativa",
    "BAIXADA": "baixada",
    "INAPTA": "inapta",
    "SUSPENSA": "suspensa",
    "NULA": "nula",
}

#: Whole-word match of any `VOCABULARIO` key, wherever it sits inside a
#: candidate string — used where a caller only needs to know "does this
#: text contain a recognisable situação word at all", not which one
#: (`cartao_cnpj._campo_situacao_cadastral`'s per-occurrence scan).
VOCABULARIO_RE = re.compile(r"\b(?:" + "|".join(VOCABULARIO) + r")\b")


def normalizar(texto: Optional[str]) -> Optional[str]:
    """`texto` -> the closed vocabulary's snake_case value, or `None` when
    blank or when nothing in `texto` matches one of the five whole words.
    Never a guess: a value normalising to `None` here is meant to travel
    to a human-readable "raw text" field alongside it (`cartao_cnpj.
    CartaoCnpjFields.rotulos["situacao_cadastral"]`, `cnpj_registry.
    CnpjRegistryFields.situacao_cadastral_bruta`), never silently dropped."""
    if not texto:
        return None
    bruto = texto.strip().upper()
    return next(
        (v for k, v in VOCABULARIO.items() if re.search(rf"\b{k}\b", bruto)),
        None,
    )


__all__ = ["VOCABULARIO", "VOCABULARIO_RE", "normalizar"]
