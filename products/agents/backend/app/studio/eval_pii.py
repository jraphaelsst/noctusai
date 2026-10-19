"""PII guard for eval fixtures (Julia v2 A-EVAL; CONTRACT 0.4).

Meta WhatsApp Business terms 4.7: WhatsApp data is never used to train or fine-tune models, and eval
fixtures are synthetic. A case that carries a phone, CPF, CNPJ or email is therefore REFUSED at the
store boundary, not scrubbed: a real transcript smuggled in as a fixture must fail loudly.

A tiny port of ``mcp/noctusai/tools/noctus/dev/_pii_guard.py`` (a product cannot import the MCP toolkit).
Only KINDS and FIELD PATHS are ever reported -- never the matched value.
"""
from __future__ import annotations

import re
from typing import Any, Iterator

__all__ = ["EvalFixtureComPii", "achar_pii", "recusar_pii"]

_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_CNPJ = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
_PHONE = re.compile(
    r"(?<![\w.])(?:"
    r"\+55[\s-]?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}"
    r"|\(\d{2}\)\s?9?\d{4}-?\d{4}"
    r"|55[1-9]\d9\d{8}"
    r"|(?<!\d)[1-9]\d9\d{8}(?!\d)"
    r")(?!\d)"
)
_EMAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class EvalFixtureComPii(ValueError):
    """The fixture carries personal data. ``tipo`` and ``campo`` are safe to log; the value is not kept."""

    def __init__(self, tipo: str, campo: str) -> None:
        self.tipo = tipo
        self.campo = campo
        super().__init__(
            f"fixture recusada: {tipo} detectado em {campo!r}; fixtures de eval são sintéticas (Meta 4.7) - "
            "nunca use transcrições reais"
        )


def _cpf_valido(raw: str) -> bool:
    d = [int(c) for c in raw if c.isdigit()]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(v * w for v, w in zip(d[:n], range(n + 1, 1, -1)))
        if d[n] != (s * 10 % 11) % 10:
            return False
    return True


def _cnpj_valido(raw: str) -> bool:
    d = [int(c) for c in raw if c.isdigit()]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)), (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        s = sum(v * w for v, w in zip(d[:n], pesos))
        r = s % 11
        if d[n] != (0 if r < 2 else 11 - r):
            return False
    return True


def _strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k, f"{path}.<chave>")
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def achar_pii(texto: str) -> list[str]:
    """Kinds of PII found in one string (a CPF/CNPJ only counts with valid check digits)."""
    tipos: list[str] = []
    if _EMAIL.search(texto):
        tipos.append("email")
    if _PHONE.search(texto):
        tipos.append("telefone")
    if any(_cpf_valido(m) for m in _CPF.findall(texto)):
        tipos.append("cpf")
    if any(_cnpj_valido(m) for m in _CNPJ.findall(texto)):
        tipos.append("cnpj")
    return tipos


def recusar_pii(**campos: Any) -> None:
    """Raise :class:`EvalFixtureComPii` on the first personal datum in any string of ``campos`` (recursive)."""
    for nome, valor in campos.items():
        for caminho, texto in _strings(valor, nome):
            tipos = achar_pii(texto)
            if tipos:
                raise EvalFixtureComPii(tipos[0], caminho)
