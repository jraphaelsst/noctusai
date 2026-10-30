"""media_service provider seams: audio -> seed transcription seam (self-hosted Whisper), vision / text -> Claude with the org's key.
No OpenAI anywhere; every provider call is injected through the DI seams."""
from __future__ import annotations

import pytest

from app.services.media_service import MediaService
from noctusai_lib.integrations.transcription import (
    TranscriberBusy, TranscriberUnavailable, TranscriptionNotConfigured, TranscriptResult,
)

pytestmark = pytest.mark.asyncio


class ScriptedTranscriber:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def probe(self, audio):  # pragma: no cover - not used here
        raise NotImplementedError

    async def transcribe(self, audio, *, language="pt", max_seconds=None):
        self.calls.append({"language": language, "max_seconds": max_seconds, "n": len(audio)})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return TranscriptResult(text=outcome, duracao_s=1.0, idioma="pt", modelo="fake")


def make(**kw) -> MediaService:
    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)

    svc = MediaService(waha_base_url="http://waha", waha_api_key="k", org_id="org-1", sleep=sleep, **kw)
    svc.sleeps = sleeps  # type: ignore[attr-defined]
    return svc


class TestAudio:
    async def test_transcribes_in_portuguese_with_no_length_limit(self):
        t = ScriptedTranscriber("  ola mundo ")
        svc = make(transcriber_factory=lambda: t)
        assert await svc.transcribe_audio(b"abc") == "ola mundo"
        assert t.calls == [{"language": "pt", "max_seconds": None, "n": 3}]

    async def test_a_busy_engine_is_retried_once_honouring_retry_after_capped(self):
        t = ScriptedTranscriber(TranscriberBusy(retry_after_s=999), "depois de esperar")
        svc = make(transcriber_factory=lambda: t)
        assert await svc.transcribe_audio(b"abc") == "depois de esperar"
        assert svc.sleeps == [10.0] and len(t.calls) == 2

    async def test_still_busy_after_the_bounded_retry_fails_gracefully(self, caplog):
        t = ScriptedTranscriber(TranscriberBusy(retry_after_s=1), TranscriberBusy(retry_after_s=1), "never")
        svc = make(transcriber_factory=lambda: t)
        assert await svc.transcribe_audio(b"abc") == ""
        assert len(t.calls) == 2 and "TranscriberBusy" in caplog.text

    async def test_unavailable_and_not_configured_never_raise(self, caplog):
        t = ScriptedTranscriber(TranscriberUnavailable("down"))
        assert await make(transcriber_factory=lambda: t).transcribe_audio(b"a") == ""

        def not_configured():
            raise TranscriptionNotConfigured("unset")

        assert await make(transcriber_factory=not_configured).transcribe_audio(b"a") == ""
        assert "TranscriptionNotConfigured" in caplog.text

    async def test_the_resolved_voice_note_carries_the_transcript(self):
        t = ScriptedTranscriber("quero o ONE123")
        res = await make(transcriber_factory=lambda: t)._resolve_audio(b"a", mimetype="audio/ogg", fallback_text="")
        assert "quero o ONE123" in res.text


class TestVisionAndText:
    async def test_vision_goes_to_anthropic_with_model_and_org(self):
        seen = {}

        async def vision(images, prompt, **kw):
            seen.update(images=images, prompt=prompt, **kw)
            return " uma casa "

        svc = make(vision_fn=vision, vision_model="claude-sonnet-5")
        assert await svc.describe_image(b"img", prompt="descreva") == "uma casa"
        assert seen["provider"] == "anthropic" and seen["model"] == "claude-sonnet-5" and seen["org_id"] == "org-1"
        assert seen["images"] == b"img" and seen["prompt"] == "descreva"

    async def test_multi_sends_one_request_capped_at_six(self):
        calls = []

        async def vision(images, prompt, **kw):
            calls.append(images)
            return "ok"

        await make(vision_fn=vision)._call_vision_multi([b"x"] * 9, prompt="p")
        assert len(calls) == 1 and len(calls[0]) == 6

    async def test_text_summary_uses_haiku_and_the_org(self):
        seen = {}

        async def text(messages, **kw):
            seen.update(messages=messages, **kw)
            return "Tipo: contrato"

        svc = make(text_fn=text, text_model="claude-haiku-4-5")
        assert await svc._summarize_document_text("conteudo") == "Tipo: contrato"
        assert seen["provider"] == "anthropic" and seen["model"] == "claude-haiku-4-5" and seen["org_id"] == "org-1"
        assert seen["messages"][1] == {"role": "user", "content": "conteudo"}
        assert await svc._summarize_document_text("   ") == ""

    async def test_a_provider_failure_keeps_describe_image_never_raising(self, caplog):
        async def vision(*a, **k):
            raise RuntimeError("no key")

        assert await make(vision_fn=vision).describe_image(b"i") == ""
        assert "RuntimeError" in caplog.text


def _clip(path, *, audio: bool) -> bytes:
    import subprocess

    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=2:r=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:d=2", "-shortest"]
    subprocess.run(cmd + [str(path)], check=True)
    return path.read_bytes()


@pytest.mark.skipif(
    not __import__("noctusai_lib.integrations.media", fromlist=["ffmpeg_available"]).ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed on this test host",
)
class TestVideoViaSeedFfmpeg:
    """The ffmpeg helpers are the seed `integrations.media.video` module (real binary)."""

    async def test_keyframes_are_four_jpegs_capped(self, tmp_path):
        from app.services.media_service import _extract_keyframes_via_ffmpeg

        frames = _extract_keyframes_via_ffmpeg(_clip(tmp_path / "v.mp4", audio=False), count=4, max_width=320)
        assert len(frames) == 4 and all(f[:2] == b"\xff\xd8" for f in frames)

    async def test_video_audio_reaches_the_transcriber_and_a_silent_clip_skips_it(self, tmp_path):
        t = ScriptedTranscriber("falou algo")
        svc = make(transcriber_factory=lambda: t)
        assert await svc._transcribe_video_audio(_clip(tmp_path / "a.mp4", audio=True), input_ext=".mp4") == "falou algo"
        assert await svc._transcribe_video_audio(_clip(tmp_path / "m.mp4", audio=False), input_ext=".mp4") == ""
        assert len(t.calls) == 1
