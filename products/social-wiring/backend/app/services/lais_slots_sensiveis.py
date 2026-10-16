"""Sensitive slot protection (lais-build-contract section 17, wave 2).

CPF and renda are never stored as typed:

  cpf            -> `sha256:<hex>|final:NNN`   (salted hash + last 3 digits; the number cannot be rebuilt
                                                 from the row, the last 3 digits let a human recognise it)
  renda_familiar -> `faixa:<bucket>`           (ate_2k | 2k_5k | 5k_10k | 10k_20k | acima_20k)

`SENSIVEIS` mirrors the `sensivel` column of `lais_perguntas_catalogo` (migration 269; a test pins the
two together). Pure functions: no IO, so the actions ledger sanitiser and the `salvar_slots` handler
share one implementation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

SENSIVEIS: dict[str, str] = {"cpf": "hash", "renda_familiar": "faixa"}

_FAIXAS: tuple[tuple[float, str], ...] = (
    (2_000, "ate_2k"), (5_000, "2k_5k"), (10_000, "5k_10k"), (20_000, "10k_20k"),
)
FAIXA_MAIS = "acima_20k"


def proteger_cpf(valor: Any, sal: str = "") -> Optional[str]:
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) != 11:
        return None
    h = hashlib.sha256(f"{sal}:{digitos}".encode("utf-8")).hexdigest()
    return f"sha256:{h}|final:{digitos[-3:]}"


def _numero(valor: Any) -> Optional[float]:
    texto = str(valor).lower().replace("r$", "").strip()
    mult = 1.0
    if re.search(r"\bmil\b|\dk\b", texto):
        mult = 1000.0
        texto = re.sub(r"\bmil\b|k\b", "", texto)
    texto = re.sub(r"[^\d.,]", "", texto)
    if not texto:
        return None
    if "." in texto and "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    elif "." in texto and len(texto.rsplit(".", 1)[1]) == 3:
        texto = texto.replace(".", "")
    try:
        return float(texto) * mult
    except ValueError:
        return None


def numero(valor: Any) -> Optional[float]:
    """The numeric reading of a typed value ("R$ 1.500,50", "2 mil", "350000") -- the ONE parser the
    income buckets and the wave-3 send criteria share; None when it is not a number."""
    return _numero(valor)


def faixa_renda(valor: Any) -> Optional[str]:
    n = _numero(valor)
    if n is None or n < 0:
        return None
    for teto, nome in _FAIXAS:
        if n < teto:
            return f"faixa:{nome}"
    return f"faixa:{FAIXA_MAIS}"


def proteger(chave: str, valor: Any, sal: str = "") -> Optional[str]:
    """The protected form of a sensitive slot, or None when the value cannot be protected (unparseable:
    the caller drops it rather than store it raw). Non-sensitive keys are returned untouched."""
    modo = SENSIVEIS.get(chave)
    if modo == "hash":
        return proteger_cpf(valor, sal)
    if modo == "faixa":
        return faixa_renda(valor)
    return str(valor)
