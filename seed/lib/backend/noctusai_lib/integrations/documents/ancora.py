"""Transcription ANCHOR: a self-checking number inside a vision transcription
tells us whether the model copied digits faithfully.

A generative vision model that mis-copies one check-digit-bearing number on a
page (a CPF, the 32-digit RCPN certidão matrícula) has shown it is not
reading that page faithfully — and the same page's NAME, ESTADO CIVIL or
dates carry no check digit to catch the same slip. So a transcription
containing a number whose check digit FAILS is marked `ancora_falhou`
(`IdentityFields.ancora_falhou`) and its readings never count toward the
two-read agreement gate (`releitura.mesclar`).

Pure and deterministic. Only formatted/labelled CPFs and 32-digit runs are
inspected: a bare 11-digit run is as likely a CNH registro or an RG as a CPF.
"""
from __future__ import annotations

import re

from noctusai_lib.primitives import identificador as _idf

#: The dash form, and the SLASH form the São Paulo RG prints its CPF in
#: (`NNN.NNN.NNN/DD`, `NNNNNNNNN/DD` — same shapes `cpf.find_cpf` reads, so a
#: mis-copied slash CPF fails the anchor exactly like a mis-copied dash one).
_CPF_FORMATADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}[-/]\d{2}(?!\d)")
_CPF_ROTULADO = re.compile(r"\bCPF\b\D{0,12}?(\d{11}|\d{9}/\d{2})(?![\d/])", re.IGNORECASE)
_MATRICULA_32 = re.compile(r"(?<!\d)(?:\d[ .\-]?){31}\d(?!\d)")


def cpfs_com_dv_falho(texto: str) -> tuple[str, ...]:
    achados = [m.group(0) for m in _CPF_FORMATADO.finditer(texto or "")]
    achados += [m.group(1) for m in _CPF_ROTULADO.finditer(texto or "")]
    return tuple(
        a for a in achados if not _idf.cpf_dv_valido(re.sub(r"\D", "", a))
    )


def matriculas_com_dv_falho(texto: str) -> tuple[str, ...]:
    ruins: list[str] = []
    for m in _MATRICULA_32.finditer(texto or ""):
        digitos = re.sub(r"\D", "", m.group(0))
        if len(digitos) != 32:
            continue
        r = _idf.validar_matricula_rcpn(digitos)
        if not r.valido or r.avisos:
            ruins.append(digitos)
    return tuple(ruins)


def ancora_falhou(texto: str) -> bool:
    """True when the transcription holds a CPF or a 32-digit certidão
    matrícula whose check digit (or structure) fails."""
    return bool(cpfs_com_dv_falho(texto) or matriculas_com_dv_falho(texto))


__all__ = ["ancora_falhou", "cpfs_com_dv_falho", "matriculas_com_dv_falho"]
