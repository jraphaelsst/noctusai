"""Redact KNOWN identity values (a registered CPF / RG) out of text and JSON-like structures.

The storage counterpart of `identificador`: once a product has REGISTERED a lead's CPF / RG, every stored copy of the
number the lead typed is rewritten with :data:`MASCARA`. Lifted from two near-copies (agents `qualificacao.identificacao`
and social-wiring `identidade_mascara`, N=2).

Contract: values are compared on digits/letters only (``123.456.789-09`` and ``12345678909`` are the same value), a
separator (``. - / space``) may sit between any two characters, case-insensitive (an RG may end in ``X``), a value
shorter than :data:`MIN_CHAVE` characters is never masked (it would mangle unrelated text), only the given values are
touched, and the result is idempotent. Pattern-based masking (labelled numbers, unknown values) is NOT here: it is
product-specific policy.

Public API: ``MASCARA``, ``MIN_CHAVE``, ``redigir_valores``, ``redigir_estrutura``, ``contem_valores``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

MASCARA = "***"
MIN_CHAVE = 5
_SEPARADORES = r"[.\-/ ]?"


def _padroes(valores: Iterable[str]) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for v in valores:
        chave = re.sub(r"[^0-9A-Za-z]", "", str(v or ""))
        if len(chave) >= MIN_CHAVE:
            out.append(re.compile(_SEPARADORES.join(re.escape(c) for c in chave), re.IGNORECASE))
    return out


def redigir_valores(texto: str, valores: Iterable[str]) -> str:
    """``texto`` with every explicit identity ``valor`` replaced by :data:`MASCARA`. Idempotent."""
    out = texto
    for padrao in _padroes(valores):
        out = padrao.sub(MASCARA, out)
    return out


def redigir_estrutura(valor: Any, valores: Iterable[str]) -> Any:
    """:func:`redigir_valores` over every string of a JSON-like value (dict keys are kept); returns a new value."""
    padroes = _padroes(valores)
    if not padroes:
        return valor

    def _walk(x: Any) -> Any:
        if isinstance(x, str):
            for p in padroes:
                x = p.sub(MASCARA, x)
            return x
        if isinstance(x, dict):
            return {k: _walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_walk(v) for v in x]
        return x

    return _walk(valor)


def contem_valores(valor: Any, valores: Iterable[str]) -> bool:
    """True when masking ``valores`` would change ``valor`` (a string or JSON-like structure)."""
    return redigir_estrutura(valor, list(valores)) != valor


__all__ = ["MASCARA", "MIN_CHAVE", "contem_valores", "redigir_estrutura", "redigir_valores"]
