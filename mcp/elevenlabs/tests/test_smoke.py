"""Tests for the ElevenLabs connector MCP. No network, no credits: only the external
HTTP seam (`elevenlabs.api.request_*`) is faked; our own guards are never patched."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively via `_kit`) must resolve to THIS
# worktree's seed — same editable-finder eviction mcp/n8n/tests does.
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    return str(_seed_lib) in (getattr(noctusai_lib, "__file__", "") or "")


if not _resolves_to_this_worktree():
    def _is_noctus_editable_finder(mp) -> bool:
        mod = getattr(mp, "__module__", "") or ""
        nm = getattr(mp, "__name__", "") or ""
        return "__editable__" in mod and nm == "_EditableFinder"

    sys.meta_path = [
        mp for mp in sys.meta_path if not _is_noctus_editable_finder(mp)
    ]
    for _name in list(sys.modules):
        if _name == "noctusai_lib" or _name.startswith("noctusai_lib."):
            del sys.modules[_name]

sys.path.insert(0, str(_SEED))

import base64
import json

import pytest

from elevenlabs import api
from elevenlabs.settings import ElevenLabsSettings

KEY = "sk_test_not_a_real_key"
_EXPECTED = {
    "elevenlabs.user.usage", "elevenlabs.model.list", "elevenlabs.voice.list",
    "elevenlabs.voice.get", "elevenlabs.voice.clone_instant", "elevenlabs.voice.delete",
    "elevenlabs.tts.synthesize",
}
_VOICE = "21m00Tcm4TlvDq8ikWAM"
_ALIGN = {
    "characters": list("Oi mundo"),
    "character_start_times_seconds": [0, .1, .2, .3, .4, .5, .6, .7],
    "character_end_times_seconds": [.1, .2, .3, .4, .5, .6, .7, .9],
}


def _settings(tmp_path, **kw):
    return ElevenLabsSettings(api_key=KEY, output_dir=str(tmp_path), **kw)


class Net:
    """Fake ElevenLabs: records calls, answers by path. External-boundary patch only."""

    def __init__(self, mult=1.0, remaining=10_000, tts_headers=None, tts_error=None):
        self.calls, self.mult, self.remaining = [], mult, remaining
        self.tts_headers = tts_headers if tts_headers is not None else {"request-id": "req_1", "x-character-count": "8"}
        self.tts_error = tts_error

    def json(self, method, path, **kw):
        self.calls.append((method, path, kw.get("params")))
        if path == "/v1/models":
            return [{"model_id": "eleven_multilingual_v2", "name": "M", "can_do_text_to_speech": True,
                     "model_rates": {"character_cost_multiplier": self.mult},
                     "maximum_text_length_per_request": 10000, "languages": [{"language_id": "pt"}]},
                    {"model_id": "x_en", "can_do_text_to_speech": False, "languages": [{"language_id": "en"}]}]
        if path == "/v1/user/subscription":
            return {"tier": "creator", "status": "active", "character_count": 100_000 - self.remaining,
                    "character_limit": 100_000}
        if path == "/v2/voices":
            return {"voices": [{"voice_id": _VOICE, "name": "V", "extra": 1}], "has_more": False}
        if path == "/v1/shared-voices":
            return {"voices": [{"voice_id": "lib1", "public_owner_id": "o", "name": "L"}]}
        if method == "DELETE":
            return {"status": "ok"}
        raise AssertionError(path)

    def bytes(self, method, path, **kw):
        self.calls.append((method, path, kw.get("params")))
        if self.tts_error:
            raise self.tts_error
        if path == "/v1/voices/add":
            return json.dumps({"voice_id": "newvoice123", "requires_verification": False}).encode(), {}
        audio = b"ID3FAKEAUDIO"
        if path.endswith("/with-timestamps"):
            return json.dumps({"audio_base64": base64.b64encode(audio).decode(),
                               "alignment": _ALIGN, "normalized_alignment": _ALIGN}).encode(), self.tts_headers
        return audio, self.tts_headers

    def __enter__(self):
        from unittest.mock import patch as p
        self._ps = [p("elevenlabs.api.request_json", side_effect=self.json),
                    p("elevenlabs.api.request_bytes", side_effect=self.bytes)]
        for x in self._ps:
            x.start()
        return self

    def __exit__(self, *a):
        for x in self._ps:
            x.stop()

    def spent_calls(self):
        return [c for c in self.calls if c[0] == "POST"]


def run(fn, args, settings):
    with patch("elevenlabs.tools._common.get_settings", return_value=settings), \
         patch("elevenlabs.tools.tts.get_settings", return_value=settings):
        return asyncio.run(fn(args))


# ─── registry ────────────────────────────────────────────────────────────


def test_registry_pinned_dotted_and_coherent():
    from elevenlabs.tools import all_descriptors, all_handlers

    assert set(all_handlers()) == _EXPECTED
    assert {d.name for d in all_descriptors()} == _EXPECTED
    assert all(n.count(".") == 2 and n.startswith("elevenlabs.") for n in _EXPECTED)


# ─── auth / settings ─────────────────────────────────────────────────────


def test_missing_key_is_typed_424_no_http():
    from elevenlabs.tools.account import user_usage

    with patch("elevenlabs.tools._common.get_settings", return_value=ElevenLabsSettings()), \
         patch("_kit.transport.urlopen") as net:
        out = asyncio.run(user_usage({}))
    net.assert_not_called()
    assert out["error"]["status"] == 424 and "ELEVENLABS_API_KEY" in out["error"]["message"]
    assert KEY not in json.dumps(out)


def test_settings_defaults_and_flags(monkeypatch):
    monkeypatch.delenv("NOCTUS_PRIVATE_DIR", raising=False)
    s = ElevenLabsSettings(api_key="k")
    assert s.configured and s.zero_retention is True and s.max_chars_cap == 5000
    assert s.default_output_dir == Path.home() / ".noctusai" / "private" / "elevenlabs"
    assert ElevenLabsSettings(zero_retention_raw="False").zero_retention is False
    assert ElevenLabsSettings(max_chars="abc").max_chars_cap == 5000
    assert ElevenLabsSettings(output_dir="/x/y").default_output_dir == Path("/x/y")
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", "/p")
    assert ElevenLabsSettings().default_output_dir == Path("/p/elevenlabs")


def test_api_sends_xi_api_key_header():
    from _kit import transport

    seen = {}

    class R:
        headers = {}
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=None):
        seen["h"] = dict(req.header_items())
        return R()

    with patch.object(transport, "urlopen", fake):
        api.request_json("GET", "/v1/models", base_url="https://x", api_key=KEY)
    assert seen["h"]["Xi-api-key"] == KEY


# ─── reads ───────────────────────────────────────────────────────────────


def test_usage_remaining(tmp_path):
    from elevenlabs.tools.account import user_usage

    with Net(remaining=4000):
        out = run(user_usage, {}, _settings(tmp_path))
    assert out["tier"] == "creator" and out["remaining"] == 4000


def test_models_filtered_to_tts_and_language(tmp_path):
    from elevenlabs.tools.account import model_list

    with Net(mult=0.5):
        out = run(model_list, {"language": "pt"}, _settings(tmp_path))
    assert [m["model_id"] for m in out["models"]] == ["eleven_multilingual_v2"]
    assert out["models"][0]["character_cost_multiplier"] == 0.5


def test_voice_list_includes_library_and_slims(tmp_path):
    from elevenlabs.tools.voices import voice_list

    with Net() as n:
        out = run(voice_list, {"search": "ana", "include_library": True}, _settings(tmp_path))
    assert out["voices"][0]["voice_id"] == _VOICE and "extra" not in out["voices"][0]
    assert out["library_voices"][0]["voice_id"] == "lib1"
    assert any(c[1] == "/v1/shared-voices" for c in n.calls)


def test_voice_id_validated_no_path_injection(tmp_path):
    from elevenlabs.tools.voices import voice_get
    from pydantic import ValidationError

    with Net() as n, pytest.raises(ValidationError):
        run(voice_get, {"voice_id": "../../etc"}, _settings(tmp_path))
    assert n.calls == []


# ─── TTS: estimate, gates, caps ──────────────────────────────────────────


def test_tts_without_confirm_returns_estimate_and_balance_no_spend(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net(mult=0.5, remaining=9000) as n:
        out = run(synthesize, {"text": "Oi mundo", "voice_id": _VOICE}, _settings(tmp_path))
    assert out["error"]["status"] == 412 and out["generated"] is False
    assert out["estimate"]["estimated_credits"] == 4.0  # 8 chars x 0.5
    assert out["balance"]["remaining"] == 9000
    assert n.spent_calls() == []
    assert list(tmp_path.iterdir()) == []


def test_tts_char_cap_refuses_before_any_call(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net() as n:
        out = run(synthesize, {"text": "x" * 11, "voice_id": _VOICE, "confirm": True},
                  _settings(tmp_path, max_chars="10"))
    assert out["error"]["status"] == 422 and "ELEVENLABS_MAX_CHARS" in out["error"]["message"]
    assert n.calls == []


def test_tts_refuses_when_estimate_exceeds_balance(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net(mult=1.0, remaining=3) as n:
        out = run(synthesize, {"text": "Oi mundo", "voice_id": _VOICE, "confirm": True}, _settings(tmp_path))
    assert out["error"]["status"] == 422 and n.spent_calls() == []


def test_tts_writes_audio_and_word_timings_json(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net() as n:
        out = run(synthesize, {"text": "Oi mundo", "voice_id": _VOICE, "confirm": True}, _settings(tmp_path))
    assert out["generated"] is True and out["error"] is None
    audio = Path(out["audio_path"])
    assert audio.read_bytes() == b"ID3FAKEAUDIO" and audio.parent.parent == tmp_path
    assert audio.suffix == ".mp3"
    t = json.loads(Path(out["timings_path"]).read_text())
    assert [w["word"] for w in t["words"]] == ["Oi", "mundo"]
    assert t["words"][1] == {"word": "mundo", "start": 0.3, "end": 0.9}
    assert out["duration_seconds"] == 0.9 and out["duration_source"] == "alignment"
    assert out["request_id"] == "req_1"
    assert out["characters_billed"] == 8 and out["characters_billed_source"] == "response_header"
    method, path, params = n.spent_calls()[0]
    assert path == f"/v1/text-to-speech/{_VOICE}/with-timestamps"
    assert params == {"output_format": "mp3_44100_128", "enable_logging": "false"}  # privacy default


def test_tts_without_timestamps_uses_plain_endpoint_and_bitrate_duration(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net(tts_headers={}) as n:
        out = run(synthesize, {"text": "Oi mundo", "voice_id": _VOICE, "confirm": True,
                               "timestamps": False, "output_format": "mp3_44100_128"}, _settings(tmp_path))
    assert out["timings_path"] is None and n.spent_calls()[0][1] == f"/v1/text-to-speech/{_VOICE}"
    assert out["duration_source"] == "estimated_from_bitrate"
    assert out["characters_billed_source"] == "estimated_from_model_multiplier"


def test_tts_zero_retention_refusal_adds_actionable_hint_and_can_be_overridden(tmp_path):
    from elevenlabs.tools.tts import synthesize

    boom = api.ElevenLabsApiError("HTTP 400", status=400)
    with Net(tts_error=boom):
        out = run(synthesize, {"text": "Oi", "voice_id": _VOICE, "confirm": True}, _settings(tmp_path))
    assert out["error"]["status"] == 400 and "enterprise" in out["error"]["message"]
    with Net() as n:
        run(synthesize, {"text": "Oi", "voice_id": _VOICE, "confirm": True, "zero_retention": False},
            _settings(tmp_path))
    assert n.spent_calls()[0][2]["enable_logging"] is None


def test_tts_refuses_output_path_inside_repo_and_does_not_overwrite(tmp_path):
    from elevenlabs.tools.tts import synthesize

    inside = str(_REPO_ROOT / "mcp" / "elevenlabs" / "oops.mp3")
    with Net() as n:
        out = run(synthesize, {"text": "Oi", "voice_id": _VOICE, "confirm": True, "output_path": inside},
                  _settings(tmp_path))
    assert out["error"]["status"] == 422 and "git" in out["error"]["message"]
    assert n.spent_calls() == [] and not Path(inside).exists()
    existing = tmp_path / "a.mp3"
    existing.write_bytes(b"keep")
    with Net() as n:
        out = run(synthesize, {"text": "Oi", "voice_id": _VOICE, "confirm": True, "output_path": str(existing)},
                  _settings(tmp_path))
    assert out["error"]["status"] == 422 and existing.read_bytes() == b"keep" and n.spent_calls() == []


def test_tts_relative_output_path_refused(tmp_path):
    from elevenlabs.tools.tts import synthesize

    with Net() as n:
        out = run(synthesize, {"text": "Oi", "voice_id": _VOICE, "confirm": True, "output_path": "rel.mp3"},
                  _settings(tmp_path))
    assert out["error"]["status"] == 422 and n.spent_calls() == []


# ─── path guard ──────────────────────────────────────────────────────────


def test_path_guard_allows_outside_and_git_ignored_inside_repo(tmp_path):
    from elevenlabs.paths import ensure_not_committable

    assert ensure_not_committable(str(tmp_path / "ok.mp3"), what="x") == (tmp_path / "ok.mp3").resolve()
    ignored = _REPO_ROOT / ".claude" / "cache" / "elevenlabs-test.mp3"  # `.claude/cache/` is gitignored
    assert ensure_not_committable(str(ignored), what="x") == ignored.resolve()
    with pytest.raises(api.RefusedError):
        ensure_not_committable(str(_REPO_ROOT / "README-tracked-guess.mp3"), what="x")


# ─── clone: consent + confirm + samples ──────────────────────────────────


def _sample(tmp_path):
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFFxxxx")
    return str(f)


def test_clone_refuses_without_consent_reference_even_with_confirm(tmp_path):
    from elevenlabs.tools.voices import voice_clone_instant

    with Net() as n:
        for ref in ("", "   ", "x"):
            out = run(voice_clone_instant, {"name": "n", "sample_paths": [_sample(tmp_path)],
                                            "consent_reference": ref, "confirm": True}, _settings(tmp_path))
            assert out["error"]["status"] == 422 and "consent" in out["error"]["message"].lower()
    assert n.calls == []


def test_clone_needs_confirm_after_consent(tmp_path):
    from elevenlabs.tools.voices import voice_clone_instant

    with Net() as n:
        out = run(voice_clone_instant, {"name": "n", "sample_paths": [_sample(tmp_path)],
                                        "consent_reference": "consent/2026-11-18-term.pdf"}, _settings(tmp_path))
    assert out["error"]["status"] == 412 and out["cloned"] is False and n.calls == []


def test_clone_refuses_samples_inside_repo(tmp_path):
    from elevenlabs.tools.voices import voice_clone_instant

    with Net() as n:
        out = run(voice_clone_instant, {"name": "n", "sample_paths": [str(_REPO_ROOT / "VERSION")],
                                        "consent_reference": "consent/term.pdf", "confirm": True},
                  _settings(tmp_path))
    assert out["error"]["status"] == 422 and n.calls == []


def test_clone_confirmed_uploads_multipart_and_returns_voice_id(tmp_path):
    from elevenlabs.tools.voices import voice_clone_instant

    with Net() as n, patch("elevenlabs.api.request_bytes", wraps=None) as rb:
        rb.return_value = (json.dumps({"voice_id": "newvoice123", "requires_verification": False}).encode(), {})
        out = run(voice_clone_instant, {"name": "Voz", "sample_paths": [_sample(tmp_path)],
                                        "consent_reference": "consent/term.pdf", "confirm": True,
                                        "labels": {"language": "pt"}}, _settings(tmp_path))
    assert out["cloned"] is True and out["voice_id"] == "newvoice123"
    assert out["consent_reference"] == "consent/term.pdf"
    body, ctype = rb.call_args.kwargs["raw_body"]
    assert ctype.startswith("multipart/form-data") and b'name="files"' in body and b"RIFFxxxx" in body
    assert b'{"language": "pt"}' in body


# ─── delete ──────────────────────────────────────────────────────────────


def test_delete_confirm_gated_then_deletes(tmp_path):
    from elevenlabs.tools.voices import voice_delete

    with Net() as n:
        out = run(voice_delete, {"voice_id": _VOICE}, _settings(tmp_path))
        assert out["error"]["status"] == 412 and n.calls == []
        out = run(voice_delete, {"voice_id": _VOICE, "confirm": True}, _settings(tmp_path))
    assert out["deleted"] is True and n.calls[0][:2] == ("DELETE", f"/v1/voices/{_VOICE}")


# ─── privacy ─────────────────────────────────────────────────────────────


def test_key_and_text_never_in_logs(tmp_path, caplog):
    from elevenlabs.tools.tts import synthesize

    caplog.set_level("DEBUG")
    with Net():
        run(synthesize, {"text": "segredo de teste", "voice_id": _VOICE, "confirm": True}, _settings(tmp_path))
    assert "segredo" not in caplog.text and KEY not in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
