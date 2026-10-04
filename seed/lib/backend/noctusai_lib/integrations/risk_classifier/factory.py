"""The single seam consumers reach for — Fake or Real risk classifier."""
from __future__ import annotations

import os
from typing import Optional

from .fake import FakeRiskClassifier
from .protocol import RiskClassifier
from .real import (
    DEFAULT_MIN_CONFIANCA,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TIMEOUT_SECONDS,
    ChatFn,
    RealRiskClassifier,
)

ENV_PROVIDER = "RISK_CLASSIFIER_PROVIDER"


def make_risk_classifier(
    *,
    provider: Optional[str] = None,
    chat: Optional[ChatFn] = None,
    model: str = DEFAULT_MODEL,
    llm_provider: str = DEFAULT_PROVIDER,
    org_id: Optional[str] = None,
    min_confianca: float = DEFAULT_MIN_CONFIANCA,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> RiskClassifier:
    """Build a `RiskClassifier`.

    `provider` ('fake'|'real') falls back to env `RISK_CLASSIFIER_PROVIDER`;
    when neither is set the default is fake ONLY under pytest — outside it an
    unset value raises (a silent Fake in prod would disable the safety step).
    Real resolves the API key through the existing LLM credential resolution
    (`resolve_api_key`); a missing key raises `LLMNotConfigured` at build time
    rather than failing every request later. `chat` is the LLM-call DI seam.
    """
    chosen = (provider or os.environ.get(ENV_PROVIDER) or "").strip().lower()
    if not chosen:
        if "PYTEST_CURRENT_TEST" in os.environ:
            chosen = "fake"
        else:
            raise ValueError(f"{ENV_PROVIDER} must be set to 'fake' or 'real'")
    if chosen == "fake":
        return FakeRiskClassifier()
    if chosen != "real":
        raise ValueError(f"unknown risk classifier provider: {chosen!r}")
    if chat is None:
        from ..llm.client import resolve_api_key

        resolve_api_key(llm_provider, org_id)
    return RealRiskClassifier(
        chat=chat,
        model=model,
        provider=llm_provider,
        org_id=org_id,
        min_confianca=min_confianca,
        timeout_seconds=timeout_seconds,
    )


__all__ = ["make_risk_classifier", "ENV_PROVIDER"]
