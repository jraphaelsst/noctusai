"""`documents.providers` — the document-read vendor default + per-rung pins.

Owner directive 2026-09-22: OpenAI has no credit; document reads default to
the cheapest Claude that reads them correctly. These tests pin that answer so
a drift (a pin moved back up, a default flipped, a rung missing a vendor)
fails here instead of as a 429 in prod.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import providers
from noctusai_lib.integrations.documents.providers import (
    DEFAULT_DOCUMENT_PROVIDER,
    DOCUMENT_ANALYSIS_MODELS,
    DOCUMENT_PROVIDERS,
    OCR_MODELS,
)


def test_the_document_default_is_anthropic() -> None:
    assert DEFAULT_DOCUMENT_PROVIDER == "anthropic"


def test_both_rungs_pin_the_measured_cheapest_claude() -> None:
    """Haiku 4.5 matched Opus 5 on every scored synthetic-scan field at
    ~1/11th the cost (table in the module docstring). Moving a pin is a
    decision that needs its own measurement — this test makes it explicit."""
    assert OCR_MODELS["anthropic"] == "claude-haiku-4-5"
    assert DOCUMENT_ANALYSIS_MODELS["anthropic"] == "claude-haiku-4-5"


def test_every_rung_covers_every_vendor_and_the_default() -> None:
    """A vendor present on one rung but not the other would send the other
    rung a model id it cannot route — the cross-vendor 404."""
    assert set(DOCUMENT_ANALYSIS_MODELS) == set(OCR_MODELS) == set(DOCUMENT_PROVIDERS)
    assert DEFAULT_DOCUMENT_PROVIDER in DOCUMENT_PROVIDERS
    assert all(OCR_MODELS.values()) and all(DOCUMENT_ANALYSIS_MODELS.values())


def test_the_transcriber_reads_the_same_objects() -> None:
    """ONE place per rung: `transcription` re-exports, it does not copy."""
    from noctusai_lib.integrations.documents import transcription

    assert transcription.OCR_MODELS is providers.OCR_MODELS
    assert transcription.DEFAULT_VISION_PROVIDER == DEFAULT_DOCUMENT_PROVIDER
