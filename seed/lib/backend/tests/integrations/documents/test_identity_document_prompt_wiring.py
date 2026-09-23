"""The 2026-09-23 defect: `LadderIdentityExtractor` never named its own
vision prompt, so an org that opted into nothing inherited `media`'s GENERIC
document prompt — "classify the type, then extract and list all fields",
tuned for the resolver's OTHER callers (a contract, a spreadsheet, a scene
photo). Real, measured: under that prompt, Claude Haiku 4.5 answered a
certidão de casamento in narrative prose, and every label-anchored parser in
this package (`name.find_name`, `cpf.find_cpf`, `rg.find_rg`, ...) found
nothing, because none of them read prose — they match a literal `LABEL:
value` pair on one line. `real._IDENTITY_DOCUMENT_PROMPT` is the fix: a
verbatim, label-preserving default, same posture as
`transcription.OCR_PROMPT` already proven on the matrícula pipeline.

Same shape as `test_vision_provider_wiring.py` (a DIFFERENT parameter that
had the identical "never wired past the constructor" defect) — kept in its
own file for the same reason that one is: these assertions should never have
to share a module with `test_extractor.py`'s `unittest.mock.patch` fixtures.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import make_identity_extractor
from noctusai_lib.integrations.documents.real import (
    _IDENTITY_DOCUMENT_PROMPT,
    LadderIdentityExtractor,
)


class TestIdentityDocumentPromptWiring:
    def test_default_is_the_verbatim_identity_prompt_not_none(self) -> None:
        """The regression this file exists to catch: `document_prompt`
        reaching the shared ladder as bare `None` silently re-inherits
        `media`'s generic prompt one hop further down."""
        extractor = make_identity_extractor(real=True)
        assert isinstance(extractor, LadderIdentityExtractor)
        assert extractor._ladder._document_prompt == _IDENTITY_DOCUMENT_PROMPT

    def test_the_prompt_asks_for_verbatim_label_value_pairs(self) -> None:
        """Structural assertion on the prompt's OWN content, not just its
        identity — a future edit that keeps the constant's name but drifts
        its wording back toward "summarize" should fail here, not silently
        reintroduce the narrative-prose defect."""
        texto = _IDENTITY_DOCUMENT_PROMPT.lower()
        assert "exatamente" in texto or "verbatim" in texto
        assert "mesma linha" in texto
        assert "resumir" in texto or "resuma" in texto  # names what NOT to do

    def test_an_explicit_override_still_wins(self) -> None:
        """A caller that names its OWN prompt is never silently overridden —
        `document_prompt or _IDENTITY_DOCUMENT_PROMPT` only substitutes on
        `None`/empty, exactly like the existing `provider` seam does."""
        extractor = make_identity_extractor(
            real=True, document_prompt="CUSTOM PROMPT FOR A TEST",
        )
        assert extractor._ladder._document_prompt == "CUSTOM PROMPT FOR A TEST"

    def test_reaches_the_real_resolver(self) -> None:
        """End-to-end: the ladder's lazily-built resolver carries the SAME
        prompt — this is what actually changes what the vision model is
        asked to do, not merely what the constructor stored."""
        from noctusai_lib.integrations.media.real_adapter import RealMediaResolver

        extractor = make_identity_extractor(real=True)
        resolver = extractor._ladder._get_resolver()
        assert isinstance(resolver, RealMediaResolver)
        assert resolver._doc_prompt == _IDENTITY_DOCUMENT_PROMPT
