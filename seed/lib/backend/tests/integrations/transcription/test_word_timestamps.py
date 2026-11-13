"""Per-word timestamps (`palavras`): opt-in end to end through the seed seam."""
from __future__ import annotations

import asyncio
import sys
import types

import httpx
import numpy as np
from fastapi.testclient import TestClient

from noctusai_lib.integrations.transcription import FakeTranscriber, LocalWhisperTranscriber
from noctusai_lib.integrations.transcription.server.app import create_app
from noctusai_lib.integrations.transcription.server.engine import EngineResult, FasterWhisperEngine

H = {"X-Transcriber-Token": "t"}


class _Seg:
    def __init__(self, with_words):
        self.start, self.end, self.text = 0.0, 1.0, " ola mundo "
        self.words = (
            [
                types.SimpleNamespace(word=" ola", start=0.0, end=0.4, probability=0.98),
                types.SimpleNamespace(word=" mundo", start=0.5, end=1.0, probability=0.91),
            ]
            if with_words
            else None
        )


class _Model:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kw):
        self.kwargs = kw
        return iter([_Seg("word_timestamps" in kw)]), None


def _engine():
    eng = FasterWhisperEngine("x")
    eng._model = _Model()
    return eng


def test_engine_passes_word_timestamps_only_when_asked():
    eng = _engine()
    plain = eng.transcribe(np.zeros(16000, dtype="float32"), language="pt")
    assert "word_timestamps" not in eng._model.kwargs
    assert plain.segmentos == [{"inicio": 0.0, "fim": 1.0, "texto": "ola mundo"}]
    rich = eng.transcribe(np.zeros(16000, dtype="float32"), language="pt", palavras=True)
    assert eng._model.kwargs["word_timestamps"] is True
    assert rich.segmentos[0]["palavras"] == [
        {"texto": "ola", "inicio": 0.0, "fim": 0.4, "confianca": 0.98},
        {"texto": "mundo", "inicio": 0.5, "fim": 1.0, "confianca": 0.91},
    ]


class _AppEngine:
    model_name = "m"
    loaded = True

    def __init__(self):
        self.calls = []

    def load(self):
        pass

    def transcribe(self, audio, *, language, palavras=False):
        self.calls.append(palavras)
        seg = {"inicio": 0, "fim": 1, "texto": "a"}
        if palavras:
            seg["palavras"] = [{"texto": "a", "inicio": 0, "fim": 1, "confianca": 0.9}]
        return EngineResult(text="a", segmentos=[seg])


async def _decode(body, max_seconds=None):
    return np.zeros(16000 * 3, dtype="float32")


def _client(eng):
    return TestClient(create_app(eng, token="t", load_in_background=False, decode_fn=_decode))


def test_server_flag_plumbs_and_default_payload_is_unchanged():
    eng = _AppEngine()
    with _client(eng) as c:
        off = c.post("/v1/transcribe", content=b"x", headers=H).json()
        on = c.post("/v1/transcribe?palavras=true", content=b"x", headers=H).json()
    assert eng.calls == [False, True]
    assert "palavras" not in off["segmentos"][0]
    assert on["segmentos"][0]["palavras"][0]["confianca"] == 0.9


def test_http_client_sends_flag_only_when_asked_and_round_trips():
    seen = []

    def handler(req: httpx.Request):
        seen.append(dict(req.url.params))
        seg = {"inicio": 0, "fim": 1, "texto": "a", "palavras": [{"texto": "a", "inicio": 0, "fim": 1, "confianca": 1.0}]}
        return httpx.Response(200, json={"text": "a", "segmentos": [seg]})

    c = LocalWhisperTranscriber(
        base_url="http://w", token="t", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    asyncio.run(c.transcribe(b"x"))
    res = asyncio.run(c.transcribe(b"x", palavras=True))
    assert "palavras" not in seen[0] and seen[1]["palavras"] == "true"
    assert res.segmentos[0]["palavras"][0]["texto"] == "a"


def test_fake_emits_plausible_word_timings_only_when_asked():
    f = FakeTranscriber(script=["ola mundo bom dia"])
    assert asyncio.run(f.transcribe(b"x")).segmentos is None
    r = asyncio.run(FakeTranscriber(script=["ola mundo bom dia"]).transcribe(b"x", palavras=True))
    words = r.segmentos[0]["palavras"]
    assert [w["texto"] for w in words] == ["ola", "mundo", "bom", "dia"]
    assert all(a["fim"] <= b["inicio"] + 1e-9 for a, b in zip(words, words[1:]))
    assert words[-1]["fim"] == r.duracao_s
