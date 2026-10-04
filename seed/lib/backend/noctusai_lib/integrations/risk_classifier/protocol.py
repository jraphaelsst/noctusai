"""`RiskClassifier` — the Protocol every adapter (Fake + Real) satisfies."""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .types import Classificacao, LabelSet


@runtime_checkable
class RiskClassifier(Protocol):
    """Classify one short text against a consumer-supplied `LabelSet`."""

    async def classify(
        self,
        text: str,
        *,
        labels: LabelSet,
        context: Optional[dict[str, Any]] = None,
    ) -> Classificacao:
        """Return a `Classificacao`; never raises for model/transport failures.

        Every failure (timeout, invalid JSON, schema mismatch, unknown
        label/signal, confidence below threshold) is the distinct
        `nivel == "indeterminado"` result — a consumer treats it as "do not
        generate". The result never contains or echoes `text`.
        """
        ...


__all__ = ["RiskClassifier"]
