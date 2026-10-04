"""Generic risk classifier — a fail-closed, text-free classification seam.

Protocol (`RiskClassifier`) + Fake + Real + factory (`make_risk_classifier`).
The consumer supplies a `LabelSet` (ordered severities + allowed signals +
descriptions); the classifier returns a `Classificacao` that NEVER contains
the input. Any failure is the distinct `indeterminado` level — callers treat
it as "no generation".

First consumer: the Limiar public-ask route (`projects/limiar-open-question`);
a therapy platform is a likely second. Recipe:

    clf = make_risk_classifier()           # env RISK_CLASSIFIER_PROVIDER
    c = await clf.classify(text, labels=MY_LABELS)
    if c.indeterminado: ...                # no generation

Real: Haiku-class via `noctusai_lib.integrations.llm.chat_completion`,
temperature 0, per-call nonce delimiter, `cache=False`, versioned prompt.
"""
from __future__ import annotations

from .factory import make_risk_classifier
from .fake import FakeRiskClassifier, normalized_text_hash
from .protocol import RiskClassifier
from .real import RealRiskClassifier
from .types import INDETERMINADO, Classificacao, LabelSet, indeterminado

__all__ = [
    "INDETERMINADO",
    "Classificacao",
    "FakeRiskClassifier",
    "LabelSet",
    "RealRiskClassifier",
    "RiskClassifier",
    "indeterminado",
    "make_risk_classifier",
    "normalized_text_hash",
]
