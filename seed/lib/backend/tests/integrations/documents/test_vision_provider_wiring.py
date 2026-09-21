"""The 2026-09-18 defect: `provider=` had no parameter to travel through
anywhere between `make_identity_extractor` / `make_matricula_extractor` and
the vision call — an org's `llm_vision_provider` setting was silently
ignored while OpenAI's account sat at zero credit and the org's Anthropic
key went unused.

These tests assert the parameter actually reaches every hop of BOTH
extractor chains, in a separate file from `test_extractor.py` /
`test_matricula_extractor.py` so this file's assertions never have to
share a module with those files' `unittest.mock.patch` fixtures.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import (
    make_identity_extractor,
    make_matricula_extractor,
)
from noctusai_lib.integrations.documents.matricula_extractor import (
    LadderMatriculaExtractor,
)
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.media.real_adapter import RealMediaResolver


class TestIdentityExtractorProviderWiring:
    def test_unset_by_default(self) -> None:
        """Behaviour-preserving: an org that never opted in threads `None`
        all the way down, unchanged."""
        extractor = make_identity_extractor(real=True)
        assert isinstance(extractor, LadderIdentityExtractor)
        assert extractor._ladder._provider is None

    def test_reaches_the_shared_ladder(self) -> None:
        extractor = make_identity_extractor(real=True, provider="anthropic")
        assert extractor._ladder._provider == "anthropic"

    def test_reaches_the_real_resolver(self) -> None:
        """End-to-end: the ladder's lazily-built resolver carries the SAME
        provider — this is what actually changes which vendor answers a
        vision call for an org that flipped the switch."""
        extractor = make_identity_extractor(real=True, provider="anthropic")
        resolver = extractor._ladder._get_resolver()
        assert isinstance(resolver, RealMediaResolver)
        assert resolver._provider == "anthropic"


class TestMatriculaExtractorProviderWiring:
    """The sibling extractor shares `DocumentTextLadder` — same gap,
    same fix."""

    def test_unset_by_default(self) -> None:
        extractor = make_matricula_extractor(real=True)
        assert isinstance(extractor, LadderMatriculaExtractor)
        assert extractor._ladder._provider is None

    def test_reaches_the_shared_ladder(self) -> None:
        extractor = make_matricula_extractor(real=True, provider="gemini")
        assert extractor._ladder._provider == "gemini"

    def test_reaches_the_real_resolver(self) -> None:
        extractor = make_matricula_extractor(real=True, provider="gemini")
        resolver = extractor._ladder._get_resolver()
        assert isinstance(resolver, RealMediaResolver)
        assert resolver._provider == "gemini"
