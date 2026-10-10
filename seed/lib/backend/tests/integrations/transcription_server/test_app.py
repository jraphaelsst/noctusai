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
from noctusai_lib.integrations.transcription.server.engine import EngineResult, EngineTimeout

TOKEN = "s3cret-token"
H = {"X-Transcriber-Token": TOKEN}


class FakeEngine:
    model_name = "fake-model"

    def __init__(self, loaded: bool = True, delay: float = 0.0, timeout: bool = False) -> None:
        self._loaded = loaded
        self.delay = delay
        self.timeout = timeout
        self.calls: list[dict] = []
        self.entered = threading.Event()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def transcribe(self, audio, *, language, deadline):
        self.entered.set()
        self.calls.append({"n": len(audio), "language": language, "deadline": deadline})
        if self.delay:
            time.sleep(self.delay)
        if self.timeout:
            raise EngineTimeout()
        return EngineResult(text="ola mundo", segmentos=[{"inicio": 0, "fim": 1, "texto": "ola mundo"}])


def _pcm_decoder(seconds: float):
    async def fake(audio: bytes, *, max_seconds: float, timeout: float = 120.0):
        return np.zeros(int(16000 * min(seconds, max_seconds)), dtype=np.float32)

    return fake


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(5.0))
    with TestClient(create_app(engine, token=TOKEN, load_in_background=False)) as c:
        yield c


def test_healthz_503_until_model_loaded(monkeypatch):
    eng = FakeEngine(loaded=False)
    # background load never runs in this test: engine stays unloaded
    a = create_app(eng, token=TOKEN, load_in_background=True)
    monkeypatch.setattr(eng, "load", lambda: None)
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


def test_token_compare_is_constant_time(monkeypatch):
    calls = []
    real = app_mod.hmac.compare_digest
    monkeypatch.setattr(app_mod.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    with TestClient(create_app(FakeEngine(), token=TOKEN, load_in_background=False)) as c:
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
    # hard cap = min(MAX_HARD_S, 3 x dur)
    assert engine.calls[0]["language"] == "pt"


def test_transcribe_duration_exceeded_422(client):
    r = client.post("/v1/transcribe?max_seconds=3", content=b"audio", headers=H)
    # decoder is faked to return min(5, max_seconds+1)=4 s > 3
    assert r.status_code == 422
    assert r.json()["codigo"] == "duracao_excedida"


def test_transcribe_too_short_422(engine, monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(0.5))
    with TestClient(create_app(engine, token=TOKEN, load_in_background=False)) as c:
        r = c.post("/v1/transcribe", content=b"a", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_vazio"


def test_empty_body_422(client):
    r = client.post("/v1/transcribe", content=b"", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_vazio"


def test_engine_timeout_maps_to_504(monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(5.0))
    with TestClient(create_app(FakeEngine(timeout=True), token=TOKEN, load_in_background=False)) as c:
        r = c.post("/v1/transcribe", content=b"a", headers=H)
    assert r.status_code == 504
    assert r.json()["codigo"] == "tempo_excedido"


def test_deadline_is_3x_duration_for_short_audio(monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(5.0))
    eng = FakeEngine()
    with TestClient(create_app(eng, token=TOKEN, load_in_background=False)) as c:
        t0 = time.monotonic()
        c.post("/v1/transcribe", content=b"a", headers=H)
    assert 14.0 < eng.calls[0]["deadline"] - t0 < 16.5  # 3 x 5 s


def test_busy_503_with_retry_after(monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(5.0))
    eng = FakeEngine(delay=0.6)
    app = create_app(eng, token=TOKEN, load_in_background=False)
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


def test_daily_backstop_503(monkeypatch):
    monkeypatch.setattr(app_mod, "decode_to_float32", _pcm_decoder(30.0))
    eng = FakeEngine()
    with TestClient(create_app(eng, token=TOKEN, daily_limit_min=0.9, load_in_background=False)) as c:
        assert c.post("/v1/transcribe", content=b"a", headers=H).status_code == 200  # 0.5 min
        r = c.post("/v1/transcribe", content=b"a", headers=H)  # would be 1.0 > 0.9
    assert r.status_code == 503
    assert r.json()["codigo"] == "capacidade_diaria"


def test_probe_uses_probe_function(client, monkeypatch):
    async def fake_probe(audio, *, timeout):
        return ProbeInfo(12.5, "opus", "matroska,webm", 48000, 2)

    monkeypatch.setattr(app_mod, "probe_bytes", fake_probe)
    r = client.post("/v1/probe", content=b"a", headers=H)
    assert r.status_code == 200
    assert r.json() == {
        "duracao_s": 12.5, "codec": "opus", "container": "matroska,webm",
        "sample_rate": 48000, "canais": 2,
    }


def test_probe_corrupt_422(client, monkeypatch):
    async def bad(audio, *, timeout):
        raise app_mod.MediaError("ffprobe failed")

    monkeypatch.setattr(app_mod, "probe_bytes", bad)
    r = client.post("/v1/probe", content=b"a", headers=H)
    assert r.status_code == 422
    assert r.json()["codigo"] == "audio_corrompido"


def test_hard_cap_allows_the_platform_45_min_max_and_stays_bounded():
    # Pure function: no 45-min PCM buffer is allocated to test the ceiling.
    assert app_mod.hard_cap_s(5.0) == 15.0
    assert app_mod.hard_cap_s(2700.0) == 8100.0
    assert app_mod.hard_cap_s(10_000.0) == app_mod.MAX_HARD_S


def test_upload_cap_admits_platform_size_and_still_refuses_above_it(client):
    over = b"0" * 16  # body content is irrelevant: Content-Length is checked first
    r = client.post(
        "/v1/transcribe", content=over,
        headers={**H, "Content-Length": str(app_mod.MAX_UPLOAD_BYTES + 1)},
    )
    assert r.status_code == 413
    assert app_mod.MAX_UPLOAD_BYTES > 100 * 1024 * 1024

