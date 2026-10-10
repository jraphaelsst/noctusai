"""Tests for ``noctus.transcription.*`` — injected httpx.MockTransport, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.transcription import client  # noqa: E402

TOKEN = "pk_secret_token_value"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOCTUS_TRANSCRIPTION_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_TRANSCRIPTION_URL", "https://core.test")


@pytest.fixture
def audio(tmp_path):
    f = tmp_path / "a.ogg"
    f.write_bytes(b"OggS" + b"\0" * 100)
    return str(f)


def _t(handler):
    return httpx.MockTransport(handler)


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_submit_parses_202_and_sends_auth_and_fields(audio):
    seen = {}

    def h(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["url"] = str(req.url)
        seen["body"] = req.content
        return httpx.Response(202, json={"id": "j1", "status": "na_fila", "posicao": 1,
                                         "estimativa_s": 30, "duracao_s": 12.5})

    out = client.submit(audio, rotulo="x", segmentos=True, _transport=_t(h))
    assert out["id"] == "j1" and out["status"] == "na_fila"
    assert seen["url"] == "https://core.test/api/transcriptions"
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert b'name="arquivo"' in seen["body"] and b"x" in seen["body"]
    assert b'name="segmentos"' in seen["body"] and b"true" in seen["body"]


def test_missing_token_no_request(monkeypatch, audio):
    monkeypatch.delenv("NOCTUS_TRANSCRIPTION_TOKEN")
    calls = []
    out = client.submit(audio, _transport=_t(lambda r: calls.append(r) or httpx.Response(202)))
    assert out["codigo"] == "nao_configurado" and not calls
    assert client.get("j1", _transport=_t(lambda r: calls.append(r)))["codigo"] == "nao_configurado"
    assert not calls


def test_oversize_refused_before_upload(tmp_path, monkeypatch, audio):
    monkeypatch.setattr(client, "MAX_BYTES", 10)
    calls = []
    out = client.submit(audio, _transport=_t(lambda r: calls.append(r) or httpx.Response(202)))
    assert out["codigo"] == "arquivo_grande" and not calls


def test_missing_file_refused(tmp_path):
    out = client.submit(str(tmp_path / "nope.ogg"), _transport=_t(lambda r: httpx.Response(202)))
    assert out["codigo"] == "arquivo_invalido"


def test_error_envelope_with_retry_after(audio):
    def h(req):
        return httpx.Response(429, headers={"Retry-After": "17"},
                              json={"codigo": "limite_envios_hora", "mensagem": "Muitos envios"})

    out = client.submit(audio, _transport=_t(h))
    assert out == {"codigo": "limite_envios_hora", "mensagem": "Muitos envios",
                   "status_code": 429, "retry_after": 17.0}


def test_token_never_in_results(monkeypatch, audio):
    def h(req):
        raise httpx.ConnectError("boom", request=req)

    out = client.submit(audio, _transport=_t(h))
    assert out["codigo"] == "erro_de_rede" and TOKEN not in repr(out)


def test_get_returns_job_and_404():
    def h(req):
        if req.url.path.endswith("/ok"):
            return httpx.Response(200, json={"id": "ok", "status": "processando"})
        return httpx.Response(404, json={"codigo": "nao_encontrado", "mensagem": "n"})

    assert client.get("ok", _transport=_t(h))["status"] == "processando"
    assert client.get("zz", _transport=_t(h))["status_code"] == 404


def test_transcribe_polls_to_concluida(audio):
    clock = Clock()
    n = {"get": 0}

    def h(req):
        if req.method == "POST":
            return httpx.Response(202, json={"id": "j1", "status": "na_fila"})
        n["get"] += 1
        if n["get"] < 3:
            return httpx.Response(200, json={"id": "j1", "status": "processando"})
        return httpx.Response(200, json={"id": "j1", "status": "concluida", "texto": "olá",
                                         "duracao_s": 3.0, "rtf": 0.2})

    out = client.transcribe(audio, _transport=_t(h), _sleep=clock.sleep, _clock=clock.now)
    assert out == {"status": "concluida", "texto": "olá", "duracao_s": 3.0, "rtf": 0.2, "id": "j1"}
    assert clock.sleeps == [5.0, 5.0]


def test_poll_interval_switches_to_30s_after_a_minute(audio):
    clock = Clock()

    def h(req):
        if req.method == "POST":
            return httpx.Response(202, json={"id": "j1", "status": "na_fila"})
        return httpx.Response(200, json={"id": "j1", "status": "processando"})

    out = client.transcribe(audio, timeout_s=200, _transport=_t(h), _sleep=clock.sleep, _clock=clock.now)
    assert out["status"] == "timeout" and out["id"] == "j1"
    assert "servidor" in out["mensagem"]
    assert clock.sleeps[:12] == [5.0] * 12 and 30.0 in clock.sleeps[12:]


def test_poll_honours_retry_after_on_503(audio):
    clock = Clock()
    n = {"get": 0}

    def h(req):
        if req.method == "POST":
            return httpx.Response(202, json={"id": "j1", "status": "na_fila"})
        n["get"] += 1
        if n["get"] == 1:
            return httpx.Response(503, headers={"Retry-After": "42"},
                                  json={"codigo": "transcricao_indisponivel", "mensagem": "x"})
        return httpx.Response(200, json={"id": "j1", "status": "falhou", "erro": {"codigo": "audio_corrompido", "mensagem": "m"}})

    out = client.transcribe(audio, _transport=_t(h), _sleep=clock.sleep, _clock=clock.now)
    assert clock.sleeps == [42.0]
    assert out["status"] == "falhou" and out["erro"]["codigo"] == "audio_corrompido"


def test_submit_429_retry_after_then_success(audio):
    clock = Clock()
    n = {"post": 0}

    def h(req):
        if req.method == "POST":
            n["post"] += 1
            if n["post"] == 1:
                return httpx.Response(429, headers={"Retry-After": "9"},
                                      json={"codigo": "limite_requisicoes", "mensagem": "x"})
            return httpx.Response(202, json={"id": "j1", "status": "na_fila"})
        return httpx.Response(200, json={"id": "j1", "status": "concluida", "texto": "t"})

    out = client.transcribe(audio, _transport=_t(h), _sleep=clock.sleep, _clock=clock.now)
    assert out["status"] == "concluida" and clock.sleeps == [9.0]


def test_transcribe_non_retryable_submit_error_returned(audio):
    def h(req):
        return httpx.Response(422, json={"codigo": "duracao_excedida", "mensagem": "x"})

    out = client.transcribe(audio, _transport=_t(h))
    assert out["codigo"] == "duracao_excedida" and out["status_code"] == 422


def test_register_exposes_three_tools():
    names = []

    class S:
        def tool(self, name, description):
            names.append(name)
            return lambda f: f

    from tools.noctus import transcription
    transcription.register_all(S())
    assert names == ["noctus.transcription.submit", "noctus.transcription.get",
                     "noctus.transcription.transcribe"]
