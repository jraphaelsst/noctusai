"""TTS adapter contract: Fake and Real (over an injected Transport), consent refusal, factory."""
from __future__ import annotations

import base64
import json
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from noctusai_lib.integrations.tts import (
    ConsentimentoAusente,
    ElevenLabsTtsClient,
    FakeTtsClient,
    HttpxTransport,
    TtsClient,
    TtsNotConfigured,
    TtsRefused,
    TtsUpstreamError,
    make_tts_client,
    palavras_do_alinhamento,
)

ALIGN = {
    "characters": list("Oi mundo"),
    "character_start_times_seconds": [0, .1, .2, .3, .4, .5, .6, .7],
    "character_end_times_seconds": [.1, .2, .3, .4, .5, .6, .7, .9],
}
VOICE = "21m00Tcm4TlvDq8ikWAM"


class Consent:
    def __init__(self, ok: bool = True):
        self.ok, self.asked = ok, []

    def vigente(self, org, voice_id):
        self.asked.append((org, voice_id))
        return self.ok


class Wire:
    """The vendor's HTTP surface, answered by path (injected Transport -- our DI seam, not a patch)."""

    def __init__(self, mult=1.0, remaining=10_000, headers=None):
        self.calls, self.mult, self.remaining = [], mult, remaining
        self.headers = {"request-id": "req_1", "x-character-count": "8"} if headers is None else headers

    def json(self, method, path, *, params=None, body=None, timeout=20.0):
        self.calls.append((method, path, params))
        if path == "/v1/models":
            return [{"model_id": "m1", "model_rates": {"character_cost_multiplier": self.mult},
                     "maximum_text_length_per_request": 10000}]
        if path == "/v1/user/subscription":
            return {"tier": "creator", "character_count": 100_000 - self.remaining, "character_limit": 100_000}
        raise AssertionError(path)

    def bytes(self, method, path, *, params=None, body=None, files=None, data=None, timeout=120.0):
        self.calls.append((method, path, params))
        if path == "/v1/voices/add":
            return json.dumps({"voice_id": "newvoice123"}).encode(), {}
        audio = b"ID3AUDIO"
        if path.endswith("/with-timestamps"):
            return json.dumps({"audio_base64": base64.b64encode(audio).decode(), "alignment": ALIGN}).encode(), self.headers
        return audio, self.headers

    def spent(self):
        return [c for c in self.calls if c[0] == "POST"]


def real(tmp_path, wire, consent=None, **kw):
    return ElevenLabsTtsClient("k", out_dir=tmp_path, org_id="org1", transport=wire,
                               consent=Consent() if consent is None else consent, **kw)


def test_alignment_groups_characters_into_words():
    w = palavras_do_alinhamento(ALIGN)
    assert [(x.texto, x.inicio_s, x.fim_s) for x in w] == [("Oi", 0.0, 0.2), ("mundo", 0.3, 0.9)]


def test_real_synthesize_maps_words_billing_and_privacy_default(tmp_path):
    wire, consent = Wire(), Consent()
    res = real(tmp_path, wire, consent).synthesize("Oi mundo", VOICE, "m1", consent_ref="termo-123")
    assert Path(res.audio_path).read_bytes() == b"ID3AUDIO"
    assert [(w.texto, w.inicio_s, w.fim_s) for w in res.timings][1] == ("mundo", 0.3, 0.9)
    assert (res.audio_s, res.caracteres, res.request_id) == (0.9, 8, "req_1")
    assert (res.creditos_cobrados, res.creditos_fonte) == (8, "response_header")
    assert consent.asked == [("org1", VOICE)]
    assert wire.spent()[0][2] == {"output_format": "mp3_44100_128", "enable_logging": "false"}
    assert json.loads(Path(res.timings_path).read_text())["words"][0] == {"word": "Oi", "start": 0.0, "end": 0.2}


def test_billing_falls_back_to_model_multiplier_estimate(tmp_path):
    res = real(tmp_path, Wire(mult=2.0, headers={})).synthesize("Oi mundo", VOICE, "m1", consent_ref="termo-123")
    assert (res.creditos_cobrados, res.creditos_fonte) == (16, "estimado_multiplicador")


def test_estimate_is_chars_times_multiplier_and_never_spends(tmp_path):
    wire = Wire(mult=0.5)
    assert real(tmp_path, wire).estimate("abcd", "m1") == 2.0
    assert wire.spent() == []


@pytest.mark.parametrize("ref", ["", "   "])
def test_synthesize_refuses_without_consent_reference(tmp_path, ref):
    wire = Wire()
    with pytest.raises(ConsentimentoAusente) as e:
        real(tmp_path, wire).synthesize("Oi", VOICE, "m1", consent_ref=ref)
    assert e.value.codigo == "consentimento_ausente" and wire.calls == []


def test_synthesize_refuses_when_checker_says_no_and_makes_no_call(tmp_path):
    wire = Wire()
    with pytest.raises(ConsentimentoAusente):
        real(tmp_path, wire, Consent(ok=False)).synthesize("Oi", VOICE, "m1", consent_ref="termo-123")
    assert wire.calls == []


def test_no_checker_means_refuse(tmp_path):
    c = ElevenLabsTtsClient("k", out_dir=tmp_path, transport=Wire(), consent=None)
    with pytest.raises(ConsentimentoAusente):
        c.synthesize("Oi", VOICE, "m1", consent_ref="termo-123")


def test_clone_refuses_without_consent_and_uploads_with_it(tmp_path):
    with pytest.raises(ConsentimentoAusente):
        real(tmp_path, Wire(), Consent(ok=False)).clone_instant("V", [("a.mp3", b"x", "audio/mpeg")], consent_ref="termo-123")
    wire = Wire()
    out = real(tmp_path, wire).clone_instant("V", [("a.mp3", b"x", "audio/mpeg")], consent_ref="termo-123")
    assert out.voice_id == "newvoice123" and wire.spent()[0][1] == "/v1/voices/add"


def test_guards_refuse_before_spend_cap_balance(tmp_path):
    wire = Wire()
    with pytest.raises(TtsRefused) as e:
        real(tmp_path, wire, max_chars=5).synthesize("x" * 6, VOICE, "m1", consent_ref="termo-123")
    assert e.value.codigo == "texto_excede_limite" and e.value.status == 422
    wire = Wire(remaining=3)
    with pytest.raises(TtsRefused) as e:
        real(tmp_path, wire).synthesize("Oi mundo", VOICE, "m1", consent_ref="termo-123")
    assert e.value.codigo == "saldo_insuficiente" and wire.spent() == []


def test_zero_retention_refusal_gets_actionable_hint(tmp_path):
    class Boom(Wire):
        def bytes(self, *a, **kw):
            raise TtsUpstreamError("HTTP 400", status=400)

    with pytest.raises(TtsUpstreamError) as e:
        real(tmp_path, Boom()).synthesize("Oi", VOICE, "m1", consent_ref="termo-123")
    assert e.value.status == 400 and "enterprise" in str(e.value)


def test_destination_is_never_overwritten(tmp_path):
    target = tmp_path / "x.mp3"
    target.write_bytes(b"old")
    with pytest.raises(TtsRefused):
        real(tmp_path, Wire()).synthesize("Oi", VOICE, "m1", consent_ref="termo-123", output_path=str(target))
    assert target.read_bytes() == b"old"


def test_httpx_transport_sends_key_header_and_never_leaks_it():
    class Resp:
        status_code, content, headers, text = 200, b"{}", {"Request-Id": "r1"}, ""

    with patch("httpx.request", return_value=Resp()) as req:  # external boundary
        HttpxTransport("sekret").json("GET", "/v1/models")
    assert req.call_args.kwargs["headers"] == {"xi-api-key": "sekret"}

    class Bad(Resp):
        status_code, text = 401, "nope"

    with patch("httpx.request", return_value=Bad()):  # external boundary
        with pytest.raises(TtsUpstreamError) as e:
            HttpxTransport("sekret").json("GET", "/v1/models")
    assert e.value.status == 401 and "sekret" not in str(e.value)


# -- Fake + factory -------------------------------------------------------


def test_fake_is_deterministic_at_wpm_and_writes_a_valid_wav(tmp_path):
    f = FakeTtsClient(out_dir=tmp_path, consent=Consent(), wpm=120)
    assert isinstance(f, TtsClient)
    res = f.synthesize("um dois tres quatro", VOICE, "m1", consent_ref="termo-123")
    assert [w.inicio_s for w in res.timings] == [0.0, 0.5, 1.0, 1.5] and res.audio_s == 2.0
    with wave.open(res.audio_path) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(2.0, abs=0.01)
    assert f.estimate("abcd", "m1") == 4.0


def test_fake_enforces_the_same_consent_refusal(tmp_path):
    with pytest.raises(ConsentimentoAusente):
        FakeTtsClient(out_dir=tmp_path, consent=Consent(ok=False)).synthesize("Oi", VOICE, "m1", consent_ref="t-1")


def test_factory_missing_key_is_a_declared_refusal_not_a_silent_fake(tmp_path):
    none = lambda org: None  # noqa: E731
    with pytest.raises(TtsNotConfigured) as e:
        make_tts_client(out_dir=tmp_path, org_id="o", key_resolver=none)
    assert e.value.status == 424
    assert isinstance(make_tts_client(out_dir=tmp_path, org_id="o", allow_fake=True, key_resolver=none), FakeTtsClient)


def test_factory_resolves_the_key_per_org_through_the_injected_chain(tmp_path):
    asked = []
    c = make_tts_client(out_dir=tmp_path, org_id="o", key_resolver=lambda org: asked.append(org) or "k")
    assert asked == ["o"] and isinstance(c, ElevenLabsTtsClient)
