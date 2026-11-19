"""motion_render: retime refusal, Fake, factory, and one real 3 s smoke render (gated on tools)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from noctusai_lib.integrations.media.video import ffmpeg_available
from noctusai_lib.integrations.motion_render import (
    FakeMotionRenderer,
    FerramentaAusente,
    RealMotionRenderer,
    RetimeRecusado,
    SpecInvalida,
    ferramentas_disponiveis,
    make_motion_renderer,
    retime,
)
from noctusai_lib.integrations.motion_render import preset as P
from noctusai_lib.integrations.motion_render.papel_engine import agrupar_legenda, titulo_grande
from noctusai_lib.integrations.tts import PalavraTiming

TOKENS = ["Oi,", "mundo", "são", "10", "anos."]


def spec(tokens=TOKENS, extra_batida=None):
    pal = [{"id": f"w{i}", "texto": t, "inicio_s": round(i * 0.3, 3), "fim_s": round(i * 0.3 + 0.3, 3)}
           for i, t in enumerate(tokens)]
    b = {"titulo": "10 anos", "ilustracao": "livro", **(extra_batida or {})}
    return {"palavras": pal, "cauda_s": 0.5,
            "cenas": [{"id": "c1", "ancora": {"palavra_id": "w0"}, "fundo": "papel", "batidas": [b]},
                      {"id": "c2", "ancora": {"palavra_id": "w3"}, "fundo": "interior", "transicao": "corte",
                       "batidas": [{"ilustracao": "xicara"}]}]}


def tim(tokens, shift=0.0):
    return [PalavraTiming(t, round(i * 0.25 + shift, 3), round(i * 0.25 + 0.2 + shift, 3)) for i, t in enumerate(tokens)]


# ── retime (pure) ────────────────────────────────────────────────────────


def test_retime_replaces_times_keeping_ids_and_is_punctuation_and_case_insensitive():
    out = retime(spec(), tim(["oi", "MUNDO", "são", "10", "anos"]))
    assert [(w["id"], w["texto"]) for w in out["palavras"]][:2] == [("w0", "Oi,"), ("w1", "mundo")]
    assert out["palavras"][4]["inicio_s"] == 1.0 and out["fala_fim_s"] == 1.2
    assert spec()["palavras"][4]["inicio_s"] == 1.2  # input untouched


def test_retime_accepts_dict_timings_from_a_stored_payload():
    out = retime(spec(), [{"word": t, "start": i, "end": i + 0.5} for i, t in enumerate(TOKENS)])
    assert out["palavras"][2]["inicio_s"] == 2.0


def test_retime_refuses_a_different_word_count():
    with pytest.raises(RetimeRecusado) as e:
        retime(spec(), tim(TOKENS[:-1]))
    assert e.value.codigo == "retime_palavras_divergem"


def test_retime_refuses_a_changed_word_without_echoing_the_script():
    with pytest.raises(RetimeRecusado) as e:
        retime(spec(), tim(["Oi", "mundo", "sao", "10", "anos"]))  # accent dropped = a different token
    assert "mundo" not in str(e.value)


# ── pure rules ───────────────────────────────────────────────────────────


def test_big_title_only_for_digit_or_key_phrase():
    assert titulo_grande({"titulo": "10 anos"}) and titulo_grande({"titulo": "Algo", "chave": True})
    assert not titulo_grande({"titulo": "Algo"}) and not titulo_grande({})


def test_caption_groups_respect_size_and_sentence_limits():
    pal = [{"id": f"w{i}", "texto": t} for i, t in enumerate("a b c d e f g h. i j".split())]
    gs = agrupar_legenda(pal)
    assert all(len(g["palavra_ids"]) <= 5 for g in gs)
    assert any(g["palavra_ids"][-1] == "w7" for g in gs)  # the sentence end closes a group


# ── Fake + factory ───────────────────────────────────────────────────────


def test_fake_returns_a_flagged_result_and_the_real_retime(tmp_path):
    f = FakeMotionRenderer()
    r = f.render("papel-explainer", spec(), None, str(tmp_path))
    assert Path(r.mp4_path).exists() and Path(r.srt_path).exists() and r.medicoes["fake"] is True
    assert r.stub == (not ffmpeg_available())
    with pytest.raises(RetimeRecusado):
        f.retime(spec(), tim(["x"]))


def test_fake_without_ffmpeg_writes_a_stub_flagged_not_playable(tmp_path):
    r = FakeMotionRenderer(ffmpeg_ok=False).render("papel-explainer", spec(), None, str(tmp_path))
    assert r.stub is True and Path(r.mp4_path).read_bytes().startswith(b"NOC-FAKE")


def test_factory_refuses_when_tools_are_missing_unless_fake_is_opted_in():
    with pytest.raises(FerramentaAusente):
        make_motion_renderer(tools_available=lambda: False)
    assert isinstance(make_motion_renderer(allow_fake=True, tools_available=lambda: False), FakeMotionRenderer)
    assert isinstance(make_motion_renderer(tools_available=lambda: True), RealMotionRenderer)


def test_real_refuses_unknown_preset_before_touching_tools(tmp_path):
    with pytest.raises(SpecInvalida) as e:
        RealMotionRenderer().render("outro", spec(), None, str(tmp_path))
    assert e.value.codigo == "preset_desconhecido"


# ── real render (ffmpeg + ImageMagick) ───────────────────────────────────

needs_tools = pytest.mark.skipif(not ferramentas_disponiveis(), reason="ffmpeg/ffprobe/magick not installed on this host")


@needs_tools
def test_real_smoke_render_of_a_three_second_spec(tmp_path):
    sp = retime(spec(TOKENS, {"etiquetas": ["mundo"], "circulo": "mundo", "ficha": "Fonte, 2020"}), tim(TOKENS))
    sp["cauda_s"] = 1.8  # 1.2 s of speech + tail = a 3.0 s video
    wav = tmp_path / "voz.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.4", "-ac", "1", str(wav)],
                   check=True)
    r = RealMotionRenderer().render("papel-explainer", sp, str(wav), str(tmp_path / "out"))
    m = r.medicoes
    assert Path(r.mp4_path).stat().st_size > 10_000 and Path(r.srt_path).read_text().strip()
    assert 2.8 <= m["duracao_s"] <= 3.2 and m["velocidade_render_x"] > 0
    assert abs(m["lufs"] - P.ALVO_LUFS) <= 1.0 and m["true_peak_db"] <= P.PICO_DBTP  # measured on the encoded mp4
    assert m["violacoes_zona_segura"] == [] and m["sincronia_cortes"]["ok"] == m["sincronia_cortes"]["cenas"]
    assert len(r.quadros_chave) == 3 and all(Path(q).exists() for q in r.quadros_chave)
    assert not list((tmp_path / "out").glob("papel-*"))  # scratch dir cleaned


@needs_tools
def test_real_refuses_an_on_screen_label_that_is_not_in_the_speech(tmp_path):
    with pytest.raises(SpecInvalida) as e:
        RealMotionRenderer().render("papel-explainer", spec(extra_batida={"etiquetas": ["inventado"]}), None, str(tmp_path))
    assert e.value.codigo == "texto_tela_nao_literal" and "inventado" not in str(e.value)
