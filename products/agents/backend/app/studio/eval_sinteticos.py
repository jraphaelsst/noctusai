"""Synthetic identity tokens for mechanism-eval lead messages (Julia v2 A-EVAL; CONTRACT 0.4 + 10.3).

An eval fixture may never carry a CPF or an email (``eval_pii`` refuses them: Meta WhatsApp Business terms 4.7,
fixtures are synthetic). The identity flow still has to be exercised end to end -- the agent asks, the lead
answers, ``registrar_identificacao`` validates the check digits / the syntax. So a roteiro writes a TOKEN where
the lead would type the value, and the LIVE adapter substitutes it, per execution, right before the message
enters the turn path:

* ``[[cpf_sintetico_valido]]`` -- a CPF with valid check digits, GENERATED at random for each execution (never a
  fixed, real-looking constant that could point at one person). It lives only in the execution's in-memory world
  (Fake identity store, Fernet key generated per world) and is never logged or returned.
* ``[[email_sintetico]]`` -- ``lead.<random>@example.com``: ``example.com`` is reserved by RFC 2606, so it can
  never be anyone's mailbox.

The same token resolves to the same value for the whole execution (a lead repeating a CPF repeats the SAME one).
An unknown ``[[...]]`` token is refused (``TokenSinteticoDesconhecido``) at validation time and again at
substitution time -- it would otherwise reach the model verbatim, a silent fixture bug.

Pure apart from the random source (``secrets``); no IO.
"""
from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterable
from typing import Any

from noctusai_lib.primitives.identificador import cpf_dv_valido

__all__ = [
    "TOKENS",
    "TOKEN_RE",
    "TokenSinteticoDesconhecido",
    "Sinteticos",
    "gerar_cpf_sintetico",
    "gerar_email_sintetico",
    "tokens_de",
    "validar_tokens",
]

TOKEN_RE = re.compile(r"\[\[\s*([A-Za-z0-9_.-]+)\s*\]\]")

_RNG = secrets.SystemRandom()


class TokenSinteticoDesconhecido(ValueError):
    """A ``[[token]]`` that is not in :data:`TOKENS`. The message names the token (never a value)."""

    def __init__(self, token: str, onde: str = "") -> None:
        self.token = token
        super().__init__(f"token sintético desconhecido {token!r}" + (f" em {onde}" if onde else ""))


def gerar_cpf_sintetico(rng: Any = _RNG) -> str:
    """A random CPF (formatted ``000.000.000-00``) with valid check digits; never a repeated-digit one.

    The mod-11 weights live ONLY in the seed (``cpf_dv_valido``): the two check digits are the unique
    pair of the 100 candidates the seed accepts for the random 9-digit base.
    """
    while True:
        base = "".join(str(rng.randrange(10)) for _ in range(9))
        if len(set(base)) > 1:
            break
    for dv in range(100):
        s = f"{base}{dv:02d}"
        if cpf_dv_valido(s):
            return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    raise AssertionError("no valid CPF check-digit pair for a non-repdigit base")  # unreachable: mod-11 always yields one


def gerar_email_sintetico(rng: Any = _RNG) -> str:
    sufixo = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(12))
    return f"lead.{sufixo}@example.com"


#: token -> generator. Additive: a new token is a new entry here (and nothing else).
TOKENS: dict[str, Callable[..., str]] = {
    "cpf_sintetico_valido": gerar_cpf_sintetico,
    "email_sintetico": gerar_email_sintetico,
}


def tokens_de(texto: str | None) -> set[str]:
    return set(TOKEN_RE.findall(texto or ""))


def validar_tokens(textos: Iterable[tuple[str, str]]) -> None:
    """``(onde, texto)`` pairs: raise on the first unknown token."""
    for onde, texto in textos:
        for t in sorted(tokens_de(texto)):
            if t not in TOKENS:
                raise TokenSinteticoDesconhecido(t, onde)


class Sinteticos:
    """The synthetic values of ONE execution: each token is generated on first use and reused after."""

    def __init__(self, rng: Any = _RNG) -> None:
        self._rng = rng
        self._valores: dict[str, str] = {}

    def valor(self, token: str) -> str:
        if token not in TOKENS:
            raise TokenSinteticoDesconhecido(token)
        if token not in self._valores:
            self._valores[token] = TOKENS[token](self._rng)
        return self._valores[token]

    def substituir(self, texto: str) -> str:
        if "[[" not in texto:
            return texto
        return TOKEN_RE.sub(lambda m: self.valor(m.group(1)), texto)
