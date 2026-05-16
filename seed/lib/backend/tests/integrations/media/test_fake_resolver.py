"""FakeMediaResolver + classify_media_kind + factory + output-contract tests.

Pattern parity with google_calendar/test_fake_adapter.py + whatsapp/
test_fake_adapter.py — Protocol/Fake/factory shape per
`KB § PATTERNS/seed-fake-real-adapter.md`. No IO: validates the
classification + ResolvedMedia output contract the chatbot consumes.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.media import (
    FakeMediaResolver,
    InboundMedia,
    MediaKind,
    MediaResolver,
    ResolvedMedia,
    classify_media_kind,
    get_media_resolver,
)


class TestClassifyMediaKind:
    @pytest.mark.parametrize(
        ("mimetype", "filename", "expected"),
        [
            ("audio/ogg", None, MediaKind.AUDIO),
            ("image/jpeg", None, MediaKind.IMAGE),
            ("video/mp4", None, MediaKind.VIDEO),
            ("application/pdf", None, MediaKind.PDF),
            ("text/plain", None, MediaKind.UNKNOWN),
            (None, "voice.opus", MediaKind.AUDIO),
            (None, "scan.PDF", MediaKind.PDF),
            ("application/octet-stream", "clip.mov", MediaKind.VIDEO),
            (None, None, MediaKind.UNKNOWN),
        ],
    )
    def test_classification(self, mimetype, filename, expected) -> None:
        assert classify_media_kind(mimetype, filename) is expected


class TestFakeMediaResolver:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeMediaResolver(), MediaResolver)

    @pytest.mark.asyncio
    async def test_audio_returns_canned_transcript(self) -> None:
        r = FakeMediaResolver()
        out = await r.resolve(InboundMedia(content=b"OGG", mimetype="audio/ogg"))
        assert isinstance(out, ResolvedMedia)
        assert out.kind is MediaKind.AUDIO
        assert "transcrição de áudio" in out.text
        assert out.error is None
        assert r.resolved[0].mimetype == "audio/ogg"

    @pytest.mark.asyncio
    async def test_image_video_pdf_each_have_distinct_enriched_text(self) -> None:
        r = FakeMediaResolver()
        img = await r.resolve(InboundMedia(content=b"x", mimetype="image/png"))
        vid = await r.resolve(InboundMedia(content=b"x", mimetype="video/mp4"))
        pdf = await r.resolve(InboundMedia(content=b"x", mimetype="application/pdf"))
        assert img.kind is MediaKind.IMAGE and "descrição da imagem" in img.text
        assert vid.kind is MediaKind.VIDEO and "análise de vídeo" in vid.text
        assert pdf.kind is MediaKind.PDF and "documento PDF" in pdf.text

    @pytest.mark.asyncio
    async def test_unknown_kind_returns_truthful_fallback_with_error(self) -> None:
        r = FakeMediaResolver()
        out = await r.resolve(InboundMedia(content=b"x", mimetype="text/plain"))
        assert out.kind is MediaKind.UNKNOWN
        assert out.text  # contract: never empty
        assert out.error == "unsupported_media_type"

    @pytest.mark.asyncio
    async def test_set_text_overrides_canned_enrichment(self) -> None:
        r = FakeMediaResolver()
        r.set_text(MediaKind.AUDIO, "CUSTOM transcript")
        out = await r.resolve(InboundMedia(content=b"x", mimetype="audio/ogg"))
        assert out.text == "CUSTOM transcript"

    @pytest.mark.asyncio
    async def test_fail_next_forces_degraded_contract(self) -> None:
        r = FakeMediaResolver()
        r.fail_next("download_failed", "boom")
        out = await r.resolve(InboundMedia(content=b"x", mimetype="image/png"))
        assert out.error == "download_failed"
        assert out.error_message == "boom"
        assert out.text  # still non-empty per contract
        # failure is one-shot
        nxt = await r.resolve(InboundMedia(content=b"x", mimetype="image/png"))
        assert nxt.error is None


class TestGetMediaResolverFactory:
    def test_default_is_fake(self) -> None:
        assert isinstance(get_media_resolver(), FakeMediaResolver)
        assert isinstance(get_media_resolver(), MediaResolver)

    def test_real_constructs_openai_resolver_lazily(self) -> None:
        # real=True imports OpenAIMediaResolver lazily; constructing it must
        # not require ffmpeg/PyMuPDF (heavy deps are lazy at resolve-time).
        from noctusai_lib.integrations.media.real_adapter import (
            OpenAIMediaResolver,
        )

        resolver = get_media_resolver(real=True, org_id="org-1")
        assert isinstance(resolver, OpenAIMediaResolver)
        assert isinstance(resolver, MediaResolver)
