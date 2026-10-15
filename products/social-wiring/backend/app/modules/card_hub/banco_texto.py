"""Guard for a `banco` value that carries agência/conta typed as free text.

Legacy card rows had e.g. "Itaú (341) Ag. 1234 CC 56789-0" in `banco` with
`agencia`/`conta` NULL; the migration-251 backfill copied it to the registry.
The bank NAME/code is public; the agência/conta digits are financial PII.

`separar_banco` moves them into agencia/conta when the whole value is exactly
"<bank> Ag. <agência> CC <conta>" (owner rule 2026-10-15: data the user
already typed is relocated, never re-asked — see KB § CONTEXT/PATTERNS/backend/
data-in-the-wrong-field.md). Anything that does not match the full shape is
left alone and still blocks, so nothing is guessed or invented.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

_PADRAO_CONTA = re.compile(
    r"(\bag\b\.?|ag[eê]ncia|\bc/c\b|\bcc\b|\bconta\b|\bc\.c\.?|\d{4,})",
    re.IGNORECASE,
)


def banco_tem_dados_de_conta(banco: Any) -> bool:
    return bool(_PADRAO_CONTA.search(str(banco or "")))


def banco_saneado(banco: Any) -> Optional[str]:
    """Only the bank name/code: text before the first agência/conta token."""
    texto = str(banco or "").strip()
    if not texto:
        return None
    m = _PADRAO_CONTA.search(texto)
    if m:
        texto = texto[: m.start()]
    return texto.strip(" \t-,;:/.") or None


_SEPARAVEL = re.compile(
    r"^\s*(?P<banco>.*?)[\s,;/-]*"
    r"\bag(?:\.|[eê]ncia)?\s*:?\s*(?P<agencia>\d{1,5}(?:-[\dxX])?)[\s,;/-]*"
    r"(?:c/c|\bcc\b|\bc\.c\.?|\bconta(?:\s+corrente)?\b)\.?\s*:?\s*"
    r"(?P<conta>\d{1,13}(?:-[\dxX])?)\s*$",
    re.IGNORECASE,
)


def separar_banco(banco: Any) -> Optional[Tuple[Optional[str], str, str]]:
    """(bank name, agência, conta) when `banco` is exactly that triple typed as
    one string; None for any other shape. The regex is anchored end to end, so
    every character is accounted for — a partial match never splits."""
    m = _SEPARAVEL.match(str(banco or ""))
    if m is None:
        return None
    nome = m.group("banco").strip(" \t-,;:/.") or None
    return nome, m.group("agencia"), m.group("conta")


def com_banco_separado(valores: dict) -> dict:
    """`valores` with agência/conta moved out of `banco` when they are there and
    the agencia/conta fields are empty; unchanged otherwise."""
    if valores.get("agencia") or valores.get("conta"):
        return valores
    partes = separar_banco(valores.get("banco"))
    if partes is None:
        return valores
    nome, agencia, conta = partes
    return {**valores, "banco": nome, "agencia": agencia, "conta": conta}
