"""Mask identity-document numbers (CPF / RG / CNH) in free text -- the Julia lead path never carries one (GUARDRAILS B8.3).

A lead may SEND a document photo or voice note, but the text that goes on to agents (`midia.texto_extraido`) and into SW's stored
copy must not contain the numbers: the lead TYPES the values Julia needs (that is how `aparece_na_mensagem` works in agents), and a
transcription of an ID is exactly the data a prompt-injection or a leak would want.

What is masked (replaced by `***`, the label kept):
  * a formatted CPF (`123.456.789-09`) and an unformatted 11-digit run that passes the CPF check digits (an 11-digit phone with DDD
    does not, so it survives);
  * a formatted RG (`12.345.678-9`);
  * the number that follows a document label (`CPF`, `RG`, `CNH`, `identidade`, `registro`, `habilitação`, `passaporte`), whatever
    its shape -- a CNH has no public check-digit rule, the label is the signal.

`redigir_valores` is the storage counterpart (GUARDRAILS B8.4): once agents has registered an identification, the stored message
text is rewritten with the SAME masking, and with any explicit values the caller knows.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from noctusai_lib.primitives.identificador import cpf_dv_valido

MASCARA = "***"
_CPF_FORMATADO = re.compile(r"(?<![\d.])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d])")
_RG_FORMATADO = re.compile(r"(?<![\d.])\d{1,2}\.\d{3}\.\d{3}-?[0-9xX](?![\d])")
_ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
_ROTULADO = re.compile(
    r"(?i)\b(cpf|rg|cnh|identidade|registro(?:\s+geral)?|habilita[cç][aã]o|passaporte)\b"
    r"(?P<sep>[^\d\n]{0,16}?)(?P<num>\d[\d.\-/ ]{4,22}[\dxX]|\d{5,})"
)


def _onze(m: re.Match[str]) -> str:
    return MASCARA if cpf_dv_valido(m.group(0)) else m.group(0)


def mascarar_identificadores(texto: str) -> str:
    """`texto` with CPF / RG / CNH numbers replaced by `***` (see the module docstring)."""
    if not texto:
        return texto or ""
    out = _ROTULADO.sub(lambda m: f"{m.group(1)}{m.group('sep')}{MASCARA}", texto)
    out = _CPF_FORMATADO.sub(MASCARA, out)
    out = _RG_FORMATADO.sub(MASCARA, out)
    return _ONZE_DIGITOS.sub(_onze, out)


def redigir_valores(texto: str, valores: Iterable[str] = ()) -> str:
    """The storage redaction: the pattern masking above, plus every explicit `valor` (compared on digits/letters only, so
    `123.456.789-09` and `12345678909` are the same value)."""
    out = mascarar_identificadores(texto)
    for v in valores:
        chave = re.sub(r"[^0-9A-Za-z]", "", str(v or ""))
        if len(chave) < 5:
            continue
        padrao = r"[.\-/ ]?".join(re.escape(c) for c in chave)
        out = re.sub(padrao, MASCARA, out)
    return out


def ref(valor: str) -> str:
    """A log-safe reference for a number / chat id / LID: 10 hex chars of its SHA-256 (never the identifier). GUARDRAILS B10:
    the Julia / media modules log this, never the identifier."""
    return hashlib.sha256((valor or "").encode("utf-8")).hexdigest()[:10]


__all__ = ["MASCARA", "mascarar_identificadores", "redigir_valores", "ref"]
