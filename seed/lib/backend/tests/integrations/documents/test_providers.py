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


def test_vision_pins_follow_the_real_document_benchmark() -> None:
    """2026-10-13 real-document benchmark (27 real docs x 3 runs, table in
    the module docstring) + owner decision: Sonnet 5 first read, Opus 5.5
    second (agreement-gate) read. Moving a pin is a decision that needs its
    own REAL-document measurement — this test makes it explicit. The chat
    rung (structured JSON over text) was not part of that benchmark and
    stays on Haiku until measured."""
    from noctusai_lib.integrations.documents.providers import ESCALATION_OCR_MODELS
    from noctusai_lib.integrations.llm.models import is_priced, models_for

    assert OCR_MODELS["anthropic"] == "claude-sonnet-5"
    assert ESCALATION_OCR_MODELS["anthropic"] == "claude-opus-5-5"
    assert DOCUMENT_ANALYSIS_MODELS["anthropic"] == "claude-haiku-4-5"
    # a pinned model must be priced, or usage records $0 and the budget guard is off
    priced = {m.id for m in models_for("anthropic", "vision") if is_priced(m)}
    for mid in (OCR_MODELS["anthropic"], ESCALATION_OCR_MODELS["anthropic"], "claude-fable-5-1"):
        assert mid in priced, mid


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
