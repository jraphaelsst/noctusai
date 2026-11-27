"""escrita_humana in the Diretor's output check (avaliar_saida) and as a mechanism assert. US$ 0, no model."""
from __future__ import annotations

import pytest

from app.criacao.saida import avaliar_saida, checar_escrita_humana
from app.studio.eval_mecanismo import AssertInvalido, avaliar_asserts, validar_asserts
from tests.channels.test_eval_diretor_live import _traco

from .mundo import CORPO_BOM, CORPO_ROBOTICO, resposta


def test_golden_reply_has_no_slop_codes():
    assert checar_escrita_humana(resposta()) == []


def test_em_dash_in_a_roteiro_body_is_prefixed_per_roteiro():
    assert "roteiro1:travessao:1" in checar_escrita_humana(resposta(corpo=CORPO_BOM + "\nEu parei — e pensei."))


def test_lexicon_in_the_legenda_is_prefixed_per_publication():
    cods = checar_escrita_humana(resposta(legenda="Uma jornada de sono."))
    assert "pub1:legenda:lexico_ia:jornada" in cods


def test_headline_is_checked_with_the_headline_profile():
    texto = "1. Não é sorte, é método (estrutura #101)\n" + resposta()
    assert "headline1:contraste_nao_e:1" in checar_escrita_humana(texto)


def test_avaliar_saida_includes_the_new_codes_and_the_rhythm_codes_once():
    cods = avaliar_saida(resposta(corpo=CORPO_ROBOTICO + " Vale ressaltar isso."), [])
    assert sum(c.startswith("roteiro1:frases_curtas") for c in cods) == 1
    assert any(c.startswith("roteiro1:lexico_ia") for c in cods)


def test_carrossel_with_required_dashes_in_markup_is_not_flagged():
    corpo = (
        "**Slide 1 — Gancho**\nCansou de postar sem resposta?\n**Slide 2 — Virada**\n"
        "Mude o primeiro quadro. Teste por uma semana.\nSalve pra depois."
    )
    assert [c for c in checar_escrita_humana(resposta(corpo=corpo)) if "travessao" in c] == []


def test_saida_criacao_ignorar_accepts_the_new_prefixes():
    t = _traco(resposta(corpo=CORPO_BOM + "\nEu parei — e pensei."))
    assert any(f.codigo == "roteiro1:travessao:1" for f in avaliar_asserts({"saida_criacao": True}, t))
    ignorando = avaliar_asserts({"saida_criacao": {"ignorar": ["roteiro1:travessao"]}}, t)
    assert not any(f.codigo.startswith("roteiro1:travessao") for f in ignorando)


class TestAssertEscritaHumana:
    def test_roteiro_profile_reads_the_reply_and_ignorar_drops(self):
        t = _traco(resposta(corpo=CORPO_BOM + "\nEu parei — e pensei."))
        falhas = avaliar_asserts({"escrita_humana": {"perfil": "roteiro"}}, t)
        assert [f.codigo for f in falhas] == ["roteiro1:travessao:1"]
        assert avaliar_asserts({"escrita_humana": {"perfil": "roteiro", "ignorar": ["roteiro1:travessao"]}}, t) == []

    def test_legenda_profile_only_reports_legenda_codes(self):
        t = _traco(resposta(legenda="Vale ressaltar o sono.", corpo=CORPO_BOM + "\nEu parei — e pensei."))
        cods = [f.codigo for f in avaliar_asserts({"escrita_humana": {"perfil": "legenda"}}, t)]
        assert cods and all(c.startswith("pub1:legenda:") for c in cods)

    def test_chat_profile_judges_each_bubble(self):
        t = _traco("")
        t.bolhas = ["Oi, tudo certo por aí?", "Ótima pergunta! **Vamos** lá"]
        cods = [f.codigo for f in avaliar_asserts({"escrita_humana": {"perfil": "chat"}}, t)]
        assert "bolha2:abertura_bajuladora" in cods and "bolha2:markdown_no_chat" in cods
        assert not any(c.startswith("bolha1:") for c in cods)

    def test_registro_formal_flags_informal_speech(self):
        t = _traco("")
        t.bolhas = ["Tá bom, vou pra casa"]
        assert avaliar_asserts({"escrita_humana": {"perfil": "chat"}}, t) == []
        assert avaliar_asserts({"escrita_humana": {"perfil": "chat", "registro": "formal"}}, t)

    @pytest.mark.parametrize("valor", [
        True, {}, {"perfil": "blog"}, {"perfil": "chat", "registro": "neutro"}, {"perfil": "chat", "extra": 1},
        {"perfil": "chat", "ignorar": "x"},
    ])
    def test_shape_is_closed(self, valor):
        with pytest.raises(AssertInvalido):
            validar_asserts({"escrita_humana": valor})

    def test_valid_shapes_pass(self):
        validar_asserts({"escrita_humana": {"perfil": "roteiro", "registro": "informal", "ignorar": ["roteiro1:ritmo"]}})
