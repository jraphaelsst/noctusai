"""The decision-free guards of the Diretor de Edição: the plan is anchored by word id and adds no new text; the measured
checks never pass on a value that was not measured. Pure functions -- no Fake needed."""
from __future__ import annotations

import pytest

from app.modules.media_creation.direcao.tipos import CenaPlanejada, EntradaCongelada, EstiloRef, Palavra, PlanoDeCenas
from app.modules.media_creation.direcao.validacao import Alvos, avaliar_medicoes, cobertura, validar_plano

TEXTO = "Você já sentiu que o dia passa e nada muda"
PALAVRAS = tuple(Palavra(f"w{i}", t) for i, t in enumerate(TEXTO.split()))
ENTRADA = EntradaCongelada(
    org_id="o", post_id="p", marca_id="m", rodada=1, headline_id="h", headline="Um jeito simples", roteiro_id="r",
    roteiro_versao=1, roteiro_sha256="x", headline_sha256="y", palavras=PALAVRAS,
)
ESTILO = EstiloRef("e", "1", "fake")


def plano(*cenas: CenaPlanejada, rotulos=()) -> PlanoDeCenas:
    return PlanoDeCenas("p", "1", ESTILO, tuple(cenas), tuple(rotulos))


def codigos(violacoes) -> list[str]:
    return [v.codigo for v in violacoes]


def test_a_plan_anchored_by_word_id_with_literal_screen_text_is_valid():
    p = plano(
        CenaPlanejada("c1", "w0", "w4", ("Você já sentiu",)),
        CenaPlanejada("c2", "w5", "w9", ("o dia passa",)),
    )
    assert validar_plano(ENTRADA, p) == []


def test_a_plan_without_scenes_is_refused():
    assert codigos(validar_plano(ENTRADA, plano())) == ["plano_sem_cenas"]


def test_an_anchor_that_is_not_a_word_of_the_script_is_refused():
    assert codigos(validar_plano(ENTRADA, plano(CenaPlanejada("c1", "w0", "w99")))) == ["ancora_desconhecida"]
    assert codigos(validar_plano(ENTRADA, plano(CenaPlanejada("c1", "5.2s", "w3")))) == ["ancora_desconhecida"]


def test_an_inverted_scene_is_refused():
    assert codigos(validar_plano(ENTRADA, plano(CenaPlanejada("c1", "w6", "w2")))) == ["cena_invertida"]


def test_duplicate_scene_ids_are_refused():
    p = plano(CenaPlanejada("c1", "w0", "w2"), CenaPlanejada("c1", "w3", "w5"))
    assert "cena_id_duplicado" in codigos(validar_plano(ENTRADA, p))


def test_screen_text_that_is_not_a_span_of_the_speech_is_new_text_and_is_refused():
    p = plano(CenaPlanejada("c1", "w0", "w4", ("Compre agora com desconto",)))
    out = validar_plano(ENTRADA, p)
    assert codigos(out) == ["texto_novo_na_tela"]
    assert "Compre" not in str(out[0])  # the violation never echoes script/plan text


def test_screen_text_is_compared_without_case_and_punctuation():
    p = plano(CenaPlanejada("c1", "w0", "w4", ("VOCÊ, já sentiu?",)))
    assert validar_plano(ENTRADA, p) == []


def test_an_approved_label_is_allowed_on_screen():
    p = plano(CenaPlanejada("c1", "w0", "w4", ("salve",)), rotulos=("salve",))
    assert validar_plano(ENTRADA, p) == []


def test_the_plan_is_not_forced_into_a_partition_overlays_and_gaps_are_measured_not_refused():
    # storytelling stays open: overlapping and partial scene sets are VALID; coverage is a measurement
    p = plano(CenaPlanejada("c1", "w0", "w5"), CenaPlanejada("c2", "w3", "w7"))
    assert validar_plano(ENTRADA, p) == []
    c = cobertura(ENTRADA, p)
    assert c == {"palavras": 10, "palavras_cobertas": 8, "palavras_sem_cena": 2, "sobreposicoes": 3}


def test_a_complete_measurement_inside_the_targets_passes():
    assert avaliar_medicoes(_boas(), Alvos()) == []


@pytest.mark.parametrize("campo", ["lufs", "true_peak_db", "violacoes_zona_segura", "duracao_s", "largura", "altura"])
def test_a_core_measurement_that_is_missing_is_never_a_pass(campo):
    m = _boas()
    del m[campo]
    assert codigos(avaliar_medicoes(m, Alvos())) == ["nao_medido"]
    assert avaliar_medicoes(m, Alvos())[0].detalhe == campo


def test_loudness_off_target_peak_over_and_safe_zone_violations_are_measured_failures():
    m = _boas(lufs=-11.3, true_peak_db=-0.8, violacoes_zona_segura=["c2"])
    assert sorted(codigos(avaliar_medicoes(m, Alvos()))) == ["loudness_fora_do_alvo", "pico_acima_do_alvo", "zona_segura_violada"]


def test_the_format_is_checked_against_the_target():
    assert codigos(avaliar_medicoes(_boas(largura=1920, altura=1080), Alvos())) == ["formato_fora_do_alvo"]


def test_hook_and_sync_that_were_not_measured_are_advisories_not_blockers():
    m = _boas()
    assert "gancho_quadro_0" not in m
    assert avaliar_medicoes(m, Alvos()) == []
    assert codigos(avaliar_medicoes(_boas(gancho_quadro_0=False), Alvos())) == ["gancho_reprovado"]


def _boas(**kw):
    base = {
        "lufs": -14.1, "true_peak_db": -2.1, "violacoes_zona_segura": [], "duracao_s": 80.0, "largura": 1080, "altura": 1920,
    }
    base.update(kw)
    return base
