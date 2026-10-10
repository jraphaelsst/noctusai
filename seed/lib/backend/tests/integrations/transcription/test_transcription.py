"""Transcription seam: validation, Fake, factory, local HTTP client (MockTransport)."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from noctusai_lib.integrations.transcription import (
    AudioProbe,
    FakeTranscriber,
    LocalWhisperTranscriber,
    OpenAIWhisperTranscriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionLimits,
    TranscriptionNotConfigured,
    TranscriptionRejected,
    make_transcriber,
    sniff_container,
)
from noctusai_lib.integrations.transcription import validation as v
from noctusai_lib.integrations.transcription.local_whisper_http import transcribe_timeout
from noctusai_lib.integrations.transcription.types import ProbeNotSupported


def run(c):
    return asyncio.run(c)


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"\x1a\x45\xdf\xa3rest", "webm"),
        (b"\x00\x00\x00\x20ftypM4A ", "mp4"),
        (b"OggSxxxx", "ogg"),
        (b"ID3\x04", "mp3"),
        (b"\xff\xfbxx", "mp3"),
        (b"\xff\xf3xx", "mp3"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav"),
        (b"MZ\x90\x00", None),
        (b"", None),
    ],
)
def test_sniff(data, expected):
    assert sniff_container(data) == expected


def test_limits_and_checks():
    lim = TranscriptionLimits()
    assert lim.max_bytes == 15 * 1024 * 1024 and lim.max_duration_s == 600
    assert v.check_size(lim.max_bytes + 1) == "arquivo_grande"
    assert v.check_size(lim.max_bytes) is None
    assert v.check_format(b"MZ..") == "formato_invalido"
    assert v.check_format(b"OggS....") is None
    ok = AudioProbe(30.0, "opus", "webm")
    assert v.check_probe(ok) is None
    assert v.check_probe(AudioProbe(0.5, "opus", "webm")) == "audio_vazio"
    assert v.check_probe(AudioProbe(601, "opus", "webm")) == "duracao_excedida"
    assert v.check_probe(AudioProbe(30, "h264", "webm")) == "formato_invalido"
    assert v.check_probe(AudioProbe(30, "opus", "mkv")) == "formato_invalido"


def test_fake_deterministic_and_scripted():
    audio = b"OggSabc"
    f = FakeTranscriber(script=[FakeTranscriber.busy(7), FakeTranscriber.rejected("audio_vazio"), "ola"])
    with pytest.raises(TranscriberBusy) as e:
        run(f.transcribe(audio, max_seconds=60))
    assert e.value.retry_after_s == 7
    with pytest.raises(TranscriptionRejected) as e2:
        run(f.transcribe(audio, max_seconds=60))
    assert e2.value.codigo == "audio_vazio"
    assert run(f.transcribe(audio, max_seconds=60)).text == "ola"
    a = run(f.transcribe(audio, max_seconds=60)).text
    assert a == run(f.transcribe(audio, max_seconds=60)).text
    custom = AudioProbe(12.0, "aac", "mp4")
    assert run(FakeTranscriber(probes={audio: custom}).probe(audio)) == custom


def test_factory(monkeypatch):
    for k in ("TRANSCRIPTION_BACKEND", "TRANSCRIBER_URL", "TRANSCRIBER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(TranscriptionNotConfigured):
        make_transcriber()
    with pytest.raises(TranscriptionNotConfigured):
        make_transcriber("bogus")
    monkeypatch.setenv("TRANSCRIPTION_BACKEND", "local_whisper")
    with pytest.raises(TranscriptionNotConfigured):  # never falls back to openai
        make_transcriber()
    monkeypatch.setenv("TRANSCRIBER_URL", "http://t:9000")
    with pytest.raises(TranscriptionNotConfigured):
        make_transcriber()
    monkeypatch.setenv("TRANSCRIBER_TOKEN", "tok")
    assert isinstance(make_transcriber(), LocalWhisperTranscriber)
    assert isinstance(make_transcriber("openai"), OpenAIWhisperTranscriber)
    assert isinstance(make_transcriber("fake"), FakeTranscriber)


def test_openai_probe_unsupported():
    with pytest.raises(ProbeNotSupported):
        run(OpenAIWhisperTranscriber().probe(b"x"))


def _client(handler):
    return LocalWhisperTranscriber(
        base_url="http://t:9000/",
        token="tok",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_http_probe_and_transcribe_ok_and_auth_header():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/v1/probe":
            return httpx.Response(200, json={"duracao_s": 12.5, "codec": "opus", "container": "webm", "sample_rate": 48000, "canais": 1})
        return httpx.Response(200, json={"text": "oi", "duracao_s": 12.5, "idioma": "pt", "modelo": "m", "rtf": 1.1})

    async def go():
        t = _client(handler)
        p = await t.probe(b"abc")
        r = await t.transcribe(b"abc", language="pt", max_seconds=60)
        return p, r

    p, r = run(go())
    assert p.duracao_s == 12.5 and p.codec == "opus"
    assert r.text == "oi" and r.rtf == 1.1
    assert all(q.headers["X-Transcriber-Token"] == "tok" for q in seen)
    assert seen[1].url.params["max_seconds"] == "60"


def test_http_error_mapping():
    def make(resp):
        return _client(lambda req: resp)

    with pytest.raises(TranscriberBusy) as e:
        run(make(httpx.Response(503, headers={"Retry-After": "22"}, json={"codigo": "ocupado"})).transcribe(b"a", max_seconds=10))
    assert e.value.retry_after_s == 22
    with pytest.raises(TranscriptionRejected) as e2:
        run(make(httpx.Response(422, json={"codigo": "audio_vazio", "mensagem": "x"})).probe(b"a"))
    assert e2.value.codigo == "audio_vazio"
    with pytest.raises(TranscriberUnavailable):
        run(make(httpx.Response(500)).probe(b"a"))
    with pytest.raises(TranscriberUnavailable):
        run(make(httpx.Response(200, content=b"not json")).probe(b"a"))

    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(TranscriberUnavailable):
        run(_client(boom).probe(b"a"))

    def slow(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(TranscriberUnavailable):
        run(_client(slow).transcribe(b"a", max_seconds=10))


def test_timeout_formula():
    assert transcribe_timeout(10) == 90
    assert transcribe_timeout(600) == 1860
    # 45-min platform max must fit (old 1800 s ceiling abandoned anything > ~10 min)
    assert transcribe_timeout(2700) == 8160
    assert transcribe_timeout(100000) == 9000
