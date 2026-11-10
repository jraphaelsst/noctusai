"""Owner-WhatsApp pieces of the eval-loop gate: the declared catalog kinds and the scripted pt-BR text builders."""
from __future__ import annotations

from noctusai_lib.domain.notification_catalog import declared_kinds

from app.notification_kinds import KIND_EVAL_LOOP_CHECKPOINT, KIND_EVAL_LOOP_PARADA, KINDS, PRODUCT
from app.studio.eval_loop_whatsapp import texto_checkpoint, texto_parada


def test_the_two_kinds_are_declared_for_whatsapp_and_in_app():
    assert PRODUCT == "agents"
    by = {k.kind: k for k in KINDS}
    assert set(by) == {KIND_EVAL_LOOP_PARADA, KIND_EVAL_LOOP_CHECKPOINT} == {"eval_loop_parada", "eval_loop_checkpoint"}
    assert all(k.canais == ("whatsapp", "in_app") and k.titulo and k.descricao and k.gatilho for k in KINDS)
    assert {k.kind for k in declared_kinds("agents")} >= set(by)


def test_parada_text_names_agent_suite_reason_score_cost_and_link():
    t = texto_parada(agente="julia", suite="comportamento", motivo="sem_melhora", melhor_nota=0.83, gasto_usd=7.5,
                     orcamento_usd=20.0, rodadas_feitas=4)
    for part in ("julia", "comportamento", "2 rodadas seguidas sem melhora", "83%", "US$ 7.50", "US$ 20.00", "4 rodada", "/agentes"):
        assert part in t


def test_parada_text_for_each_reason_is_human_not_the_code():
    for motivo in ("alvo_atingido", "orcamento_atingido", "rodadas_esgotadas", "parado_manualmente"):
        assert "_" not in texto_parada(agente="a", suite="mecanismo", motivo=motivo, melhor_nota=None, gasto_usd=0, orcamento_usd=20,
                                       rodadas_feitas=0).split("Motivo: ")[1].split(".")[0]


def test_checkpoint_text_carries_round_progress_cost_and_link():
    t = texto_checkpoint(agente="julia", suite="mecanismo", rodada=5, rodadas_planejadas=30, melhor_nota=0.9, gasto_usd=4.0,
                         orcamento_usd=20.0, rodadas_sem_melhora=1)
    for part in ("rodada 5 de 30", "90%", "US$ 4.00", "1 rodada(s) sem melhora", "/agentes"):
        assert part in t
