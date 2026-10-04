"""Value objects for the generic risk classifier.

Pure: no IO. `Classificacao` carries a verdict and NEVER the input text (nor
any fragment of it) — that is the contract that lets a consumer log, cache or
persist a result without a privacy review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

#: Reserved fail-closed level. Never a member of a consumer's `LabelSet`.
INDETERMINADO = "indeterminado"


@dataclass(frozen=True)
class LabelSet:
    """The consumer-supplied vocabulary: labels are CONFIGURATION, the
    classifier is generic.

    `niveis` is ordered ascending by severity (e.g. verde < amarelo <
    vermelho; a category such as `violencia` is just another entry). `sinais`
    are the allowed signal tags. `descricoes` maps EVERY nivel and sinal to a
    one-line description the model is shown.
    """

    niveis: tuple[str, ...]
    sinais: tuple[str, ...]
    descricoes: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.niveis:
            raise ValueError("LabelSet.niveis must not be empty")
        for kind, values in (("niveis", self.niveis), ("sinais", self.sinais)):
            if len(set(values)) != len(values):
                raise ValueError(f"LabelSet.{kind} has duplicates")
            for v in values:
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"LabelSet.{kind} entries must be non-empty strings")
        if set(self.niveis) & set(self.sinais):
            raise ValueError("a label cannot be both a nivel and a sinal")
        if INDETERMINADO in self.niveis or INDETERMINADO in self.sinais:
            raise ValueError(f"{INDETERMINADO!r} is reserved for the fail-closed result")
        missing = [x for x in (*self.niveis, *self.sinais) if not str(self.descricoes.get(x, "")).strip()]
        if missing:
            raise ValueError(f"LabelSet.descricoes missing for: {missing}")

    def ordem(self, nivel: str) -> int:
        """Severity rank of `nivel` (higher = more severe)."""
        return self.niveis.index(nivel)


@dataclass(frozen=True)
class Classificacao:
    """One classification verdict. Contains no input text, by construction."""

    nivel: str
    sinais: tuple[str, ...]
    confianca: float
    modelo: str
    versao_prompt: str

    @property
    def indeterminado(self) -> bool:
        return self.nivel == INDETERMINADO


def indeterminado(*, modelo: str, versao_prompt: str) -> Classificacao:
    """The fail-closed result — callers treat it as "no generation"."""
    return Classificacao(
        nivel=INDETERMINADO, sinais=(), confianca=0.0, modelo=modelo, versao_prompt=versao_prompt
    )


__all__ = ["INDETERMINADO", "Classificacao", "LabelSet", "indeterminado"]
