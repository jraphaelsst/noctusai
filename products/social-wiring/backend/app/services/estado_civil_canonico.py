"""Canonical tokens for `clientes.estado_civil` / `clientes.regime_bens`.

Both columns are unconstrained TEXT (migration 097), and the contract generator
branches on the TOKEN (`derivacao.py` raises for a regime not in
`frases.REGIME_EXTENSO` and compares the spouses' regimes literally). The
"Dados pessoais" form used to submit its display LABELS ("Casado(a)",
"Comunhão parcial de bens"), so a saved cônjuge poisoned the contract (2026-10-21).

This module is the ONE write-side normaliser: a known label maps to its token,
a token passes, anything else is refused. The vocabularies are the seed's
(`ESTADO_CIVIL_VALORES` / `REGIME_BENS_VALORES`) and the generator's own
regime wording (`REGIME_EXTENSO`) — no second list.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.integrations.documents import ESTADO_CIVIL_VALORES, REGIME_BENS_VALORES

from app.modules.card_hub.contrato_gerador.frases import REGIME_EXTENSO


def _chave(texto: str) -> str:
    return " ".join(fold_accents_ascii(texto).casefold().replace("_", " ").split())


#: Spellings that are NOT a token's own form: gendered / "(a)" labels the form
#: and older paths wrote. Keyed by `_chave`.
_ESTADO_CIVIL_ROTULOS: dict[str, str] = {
    "solteiro(a)": "solteiro", "solteira": "solteiro",
    "casado(a)": "casado", "casada": "casado",
    "divorciado(a)": "divorciado", "divorciada": "divorciado",
    "viuvo(a)": "viuvo", "viuva": "viuvo",
    "separado": "separado_judicialmente", "separado(a)": "separado_judicialmente",
    "separada": "separado_judicialmente",
    "separado(a) judicialmente": "separado_judicialmente",
    "separado judicialmente": "separado_judicialmente",
    "separada judicialmente": "separado_judicialmente",
    "uniao estavel": "uniao_estavel",
}

_ESTADO_CIVIL: dict[str, str] = {
    **{_chave(t): t for t in ESTADO_CIVIL_VALORES},
    **_ESTADO_CIVIL_ROTULOS,
}

_REGIME: dict[str, str] = {
    **{_chave(t): t for t in REGIME_BENS_VALORES},
    **{_chave(rotulo): t for t, rotulo in REGIME_EXTENSO.items()},
}


def _canonico(valor: Optional[str], tabela: dict[str, str], campo: str) -> Optional[str]:
    if valor is None:
        return None
    if not isinstance(valor, str) or not valor.strip():
        # An empty string is a clear, as the form's `""` -> null mapping sends.
        return None
    token = tabela.get(_chave(valor))
    if token is None:
        raise ValueError(f"{campo} desconhecido: {valor!r}")
    return token


def estado_civil_canonico(valor: Optional[str]) -> Optional[str]:
    """Token for a known `estado_civil` (label or token); None clears; else ValueError."""
    return _canonico(valor, _ESTADO_CIVIL, "estado_civil")


def regime_bens_canonico(valor: Optional[str]) -> Optional[str]:
    """Token for a known `regime_bens` (label or token); None clears; else ValueError."""
    return _canonico(valor, _REGIME, "regime_bens")
