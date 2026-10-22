"""RG + CPF stated in a matrícula averbação, used to complete a CNH's RG.

A CNH prints the RG WITHOUT its check digit (`29790659 SSP/SP`); a matrícula
averbação often states the owner's full numbers: "O número do RG de FULANO é
29.790.659-8 e o do CPF é 219.671.678-26". Pure text reading, no I/O.

* :func:`find_rg_cpf_averbacao` -> every `(nome, rg, cpf)` pair stated.
* :func:`completar_rg_cnh` -> the full RG when ONE pair has the same CPF as the
  party AND its RG minus the check digit equals the CNH number; else `None`
  (never a guess — a CPF mismatch or a different prefix completes nothing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_valido
from noctusai_lib.integrations.documents.cpf import only_digits as _digitos

_NUM = r"(?:n[ºo°.]{0,2}\s*)?"
_ELO = r"(?:é|e|era|:|-|sob\s+o?\s*)?\s*" + _NUM
_RG_RE = re.compile(
    r"\bRG\b\s*(?:de\s+(?P<nome>[^,;:\n]{3,90}?)\s+)?" + _ELO
    + r"(?P<rg>\d{1,3}(?:\.\d{3})+\s*-?\s*[\dXx]?|\d{5,11}\s*-?\s*[\dXx]?)"
    r"(?P<orgao>\s*[A-Z]{2,6}\s*/\s*[A-Z]{2})?"
    r"[\s,;]*(?:e|and)?\s*(?:o\s+|do\s+|da\s+)*(?:n[úu]mero\s+)?(?:do\s+)?(?:\bCPF\b)(?:/MF)?\s*"
    r"(?:de\s+[^,;:\n]{3,90}?\s+)?" + _ELO
    + r"(?P<cpf>\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RgCpfAverbado:
    nome: Optional[str]
    rg: str  # as stated, digits + optional DV (punctuation stripped)
    cpf: str  # 11 digits, check digit valid


def _limpa_rg(bruto: str) -> str:
    return re.sub(r"[^0-9Xx]", "", bruto).upper()


def find_rg_cpf_averbacao(text: str) -> tuple[RgCpfAverbado, ...]:
    """All `(nome, rg, cpf)` pairs an averbação states; CPFs must be valid."""
    achados: list[RgCpfAverbado] = []
    vistos: set[tuple[str, str]] = set()
    for m in _RG_RE.finditer(text or ""):
        cpf = _digitos(m.group("cpf"))
        if not _cpf_valido(cpf):
            continue
        rg = _limpa_rg(m.group("rg"))
        if len(rg) < 5 or (rg, cpf) in vistos:
            continue
        vistos.add((rg, cpf))
        nome = m.group("nome")
        nome = re.sub(r"\s+", " ", nome).strip().upper() if nome else None
        achados.append(RgCpfAverbado(nome=nome, rg=rg, cpf=cpf))
    return tuple(achados)


def completar_rg_cnh(
    rg_cnh: Optional[str], cpf: Optional[str], pares: Iterable[RgCpfAverbado]
) -> Optional[str]:
    """Full RG (digits + DV, no punctuation) completing the CNH's `rg_cnh`.

    Only when exactly one distinct RG among the pairs carrying THIS `cpf` has
    its prefix (everything before the final DV character) equal to `rg_cnh`.
    A CNH number already equal to the stated RG completes nothing new -> that
    RG is returned only if it is longer (carries a DV).
    """
    base = _limpa_rg(rg_cnh or "")
    alvo = _digitos(cpf or "")
    if len(base) < 5 or len(alvo) != 11:
        return None
    candidatos = {
        p.rg
        for p in pares
        if p.cpf == alvo and len(p.rg) == len(base) + 1 and p.rg[:-1] == base
    }
    return next(iter(candidatos)) if len(candidatos) == 1 else None


__all__ = ["RgCpfAverbado", "completar_rg_cnh", "find_rg_cpf_averbacao"]
