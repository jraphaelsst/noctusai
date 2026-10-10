"""In-memory `RiskClassifier` — a lookup table keyed by a normalized text hash.

Unknown text ⇒ `indeterminado`, which makes the fail-closed branch testable
without a model. Only hashes are stored/recorded, never text.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from .types import Classificacao, LabelSet, indeterminado
from noctusai_lib.primitives.accents import fold_accents

FAKE_MODEL = "fake-risk-classifier"
FAKE_PROMPT_VERSION = "fake-v1"


def normalized_text_hash(text: str) -> str:
    """sha256 of the text lower-cased, accent-stripped, whitespace-collapsed."""
    stripped = fold_accents(text)
    norm = re.sub(r"\s+", " ", stripped.lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class FakeRiskClassifier:
    """Deterministic table-driven classifier."""

    def __init__(self, table: Optional[dict[str, Classificacao]] = None) -> None:
        self._table: dict[str, Classificacao] = dict(table or {})
        #: hashes of the texts classified, in order — never the texts.
        self.calls: list[str] = []

    def add(
        self, text: str, nivel: str, sinais: tuple[str, ...] = (), confianca: float = 1.0
    ) -> None:
        self._table[normalized_text_hash(text)] = Classificacao(
            nivel=nivel,
            sinais=tuple(sinais),
            confianca=confianca,
            modelo=FAKE_MODEL,
            versao_prompt=FAKE_PROMPT_VERSION,
        )

    async def classify(
        self,
        text: str,
        *,
        labels: LabelSet,
        context: Optional[dict[str, Any]] = None,
    ) -> Classificacao:
        key = normalized_text_hash(text)
        self.calls.append(key)
        hit = self._table.get(key)
        fail = indeterminado(modelo=FAKE_MODEL, versao_prompt=FAKE_PROMPT_VERSION)
        if hit is None:
            return fail
        # Same output validation the Real applies: a scripted verdict outside
        # the consumer's vocabulary is a schema mismatch, not a result.
        if hit.nivel not in labels.niveis or any(s not in labels.sinais for s in hit.sinais):
            return fail
        return hit


__all__ = ["FakeRiskClassifier", "normalized_text_hash", "FAKE_MODEL", "FAKE_PROMPT_VERSION"]
