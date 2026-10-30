"""Worker app tests — model behind a fake engine seam; no network, no model."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.transcription.server import app as app_mod
from noctusai_lib.integrations.transcription.server.app import create_app
from noctusai_lib.integrations.transcription.server.media import ProbeInfo
from noctusai_lib.integrations.transcription.server.engine import EngineResult

TOKEN = "s3cret-token"
H = {"X-Transcriber-Token": TOKEN}


class FakeEngine:
    model_name = "fake-model"

    def __init__(self, loaded: bool = True, delay: float = 0.0, loadable: bool = True) -> None:
        self._loaded = loaded
        self._loadable = loadable
        self.delay = delay
        self.calls: list[dict] = []
        self.entered = threading.Event()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loadable:
            self._loaded = True

    def transcribe(self, audio, *, language):
        self.entered.set()
        self.calls.append({"n": len(audio), "language": language})
        if self.delay:
            time.sleep(self.delay)
        return EngineResult(text="ola mundo", segmentos=[{"inicio": 0, "fim": 1, "texto": "ola mundo"}])


def _pcm_decoder(seconds: float, seen: list | None = None):
    async def fake(audio: bytes, *, max_seconds, timeout: float = 120.0):
        if seen is not None:
            seen.append(max_seconds)
        n = seconds if max_seconds is None else min(seconds, max_seconds)
        return np.zeros(int(16000 * n), dtype=np.float32)

    return fake


@pytest.fixture
def engine():
    return FakeEngine()


def _app(engine, *, seconds: float = 5.0, **kw):
    """The worker app with the ffmpeg decoder replaced by a PCM fake of `seconds` (DI seam)."""
    return create_app(engine, token=TOKEN, load_in_background=False, decode_fn=_pcm_decoder(seconds), **kw)


@pytest.fixture
def client(engine):
    with TestClient(_app(engine)) as c:
        yield c


def test_healthz_503_until_model_loaded():
    # the background load runs but never completes: engine stays unloaded
    eng = FakeEngine(loaded=False, loadable=False)
    a = create_app(eng, token=TOKEN, load_in_background=True)
    with TestClient(a) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    assert r.json()["codigo"] == "modelo_carregando"


def test_healthz_200_when_loaded(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["modelo"] == "fake-model"


@pytest.mark.parametrize("path", ["/v1/probe", "/v1/transcribe"])
@pytest.mark.parametrize("headers", [{}, {"X-Transcriber-Token": "wrong"}])
def test_auth_required_strict_401(client, path, headers):
    r = client.post(path, content=b"x", headers=headers)
    assert r.status_code == 401


def test_empty_configured_token_fails_closed(monkeypatch):
    monkeypatch.delenv("TRANSCRIBER_TOKEN", raising=False)
    with TestClient(create_app(FakeEngine(), token="", load_in_background=False)) as c:
        r = c.post("/v1/transcribe", content=b"x", headers={"X-Transcriber-Token": ""})
    assert r.status_code == 401


def test_token_compare_is_constant_time():
    import hmac

    calls = []
    compare = lambda a, b: calls.append(1) or hmac.compare_digest(a, b)  # noqa: E731
    assert app_mod.create_app.__kwdefaults__["compare_fn"] is hmac.compare_digest
    with TestClient(create_app(FakeEngine(), token=TOKEN, load_in_background=False, compare_fn=compare)) as c:
        c.post("/v1/probe", content=b"x", headers={"X-Transcriber-Token": "nope"})
    assert calls


def test_transcribe_ok(client, engine):
    r = client.post("/v1/transcribe?language=pt&max_seconds=600", content=b"audio", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "ola mundo"
    assert body["idioma"] == "pt"
    assert body["modelo"] == "fake-model"
    assert body["duracao_s"] == pytest.approx(5.0)
    assert "rtf" in body
    assert engine.calls[0]["language"] == "pt"


def test_transcribe_duration_exceeded_422(client):
    r = client.post("/v1/transcribe?max_seconds=3", content=b"audio", headers=H)
    # decoder is faked to return min(5, max_seconds+1)=4 s > 3
    assert r.status_code == 422
    assert r.json()["codigo"] == "duracao_excedida"


def test_transcribe_too_short_422(engine):
    with TestClient(_app(engine, seconds=0.5)) as c:
        r = c.post("/v1/transcribe", content=b"a", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_vazio"


def test_empty_body_422(client):
    r = client.post("/v1/transcribe", content=b"", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_vazio"


def test_no_max_seconds_reads_the_whole_audio_and_never_cuts_it_off():
    # Owner, 2026-10-30: any length is read. A 2-hour note decodes uncapped and a
    # slow engine still answers 200 (no wall-clock 504 any more).
    eng, seen = FakeEngine(delay=0.3), []
    app = create_app(eng, token=TOKEN, load_in_background=False, daily_limit_min=1e9,
                     decode_fn=_pcm_decoder(7200.0, seen))
    with TestClient(app) as c:
        r = c.post("/v1/transcribe?language=pt", content=b"a", headers=H)
    assert r.status_code == 200
    assert seen == [None]
    assert r.json()["duracao_s"] == pytest.approx(7200.0)


def test_busy_503_with_retry_after():
    eng = FakeEngine(delay=0.6)
    app = _app(eng, seconds=5.0)
    results = {}
    with TestClient(app) as c:
        t = threading.Thread(
            target=lambda: results.setdefault("first", c.post("/v1/transcribe", content=b"a", headers=H))
        )
        t.start()
        assert eng.entered.wait(5)
        second = c.post("/v1/transcribe", content=b"a", headers=H)
        t.join()
    assert second.status_code == 503
    assert second.json() == {"codigo": "ocupado", "mensagem": "transcritor ocupado"}
    assert second.headers["Retry-After"] == "15"
    assert results["first"].status_code == 200


def test_daily_backstop_503():
    eng = FakeEngine()
    with TestClient(_app(eng, seconds=30.0, daily_limit_min=0.9)) as c:
        assert c.post("/v1/transcribe", content=b"a", headers=H).status_code == 200  # 0.5 min
        r = c.post("/v1/transcribe", content=b"a", headers=H)  # would be 1.0 > 0.9
    assert r.status_code == 503
    assert r.json()["codigo"] == "capacidade_diaria"


def test_probe_uses_probe_function(engine):
    async def fake_probe(audio, *, timeout):
        return ProbeInfo(12.5, "opus", "matroska,webm", 48000, 2)

    with TestClient(_app(engine, probe_fn=fake_probe)) as c:
        r = c.post("/v1/probe", content=b"a", headers=H)
    assert r.status_code == 200
    assert r.json() == {
        "duracao_s": 12.5, "codec": "opus", "container": "matroska,webm",
        "sample_rate": 48000, "canais": 2,
    }


def test_probe_corrupt_422(engine):
    async def bad(audio, *, timeout):
        raise app_mod.MediaError("ffprobe failed")

    with TestClient(_app(engine, probe_fn=bad)) as c:
        r = c.post("/v1/probe", content=b"a", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_corrompido"


def test_upload_cap_admits_platform_size_and_still_refuses_above_it(client):
    over = b"0" * 16  # body content is irrelevant: Content-Length is checked first
    r = client.post(
        "/v1/transcribe", content=over,
        headers={**H, "Content-Length": str(app_mod.MAX_UPLOAD_BYTES + 1)},
    )
    assert r.status_code == 413
    assert app_mod.MAX_UPLOAD_BYTES > 100 * 1024 * 1024

