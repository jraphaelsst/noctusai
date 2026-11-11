"""Q8: the handoff-summary outcomes are DATA -- exactly the values labelled in the effective ``registrar_resumo``
row; an unlabelled (legacy) row keeps the 5 legacy values on a logged branch; an out-of-set answer is logged and
counted, never silently replaced."""
from __future__ import annotations

import logging

from app.channels import extracao
from app.studio.compiler import _avisos_desfecho
from app.studio.models import ConteudoBundle, FerramentaData

ROTULOS_BASE = {f"desfecho_sugerido.{v}": f"rotulo {v}" for v in extracao.DESFECHOS_BASE}
ROTULOS_VENDAS = {f"desfecho_sugerido.{v}": f"rotulo {v}" for v in extracao.DESFECHOS_VENDAS}


def _c(parametros) -> ConteudoBundle:
    return ConteudoBundle(ferramentas=(FerramentaData("registrar_resumo", "Resume.", parametros=parametros),))


def test_offered_enum_equals_labelled_values():
    assert extracao.desfechos_oferecidos(_c(ROTULOS_BASE)) == extracao.DESFECHOS_BASE
    tool = extracao.resumo_tool(_c({**ROTULOS_BASE, **ROTULOS_VENDAS}))
    assert tool.parameters["properties"]["desfecho_sugerido"]["enum"] == list(extracao.DESFECHOS)


def test_legacy_unlabelled_row_gets_the_five_on_a_logged_branch(caplog):
    with caplog.at_level(logging.INFO, logger=extracao.logger.name):
        assert extracao.desfechos_oferecidos(_c({})) == extracao.DESFECHOS_LEGADO
    assert "desfecho.legado" in caplog.text
    assert set(extracao.DESFECHOS_LEGADO) == {"qualificado", "frio", "captacao", "invalido", "em_andamento"}


def test_unknown_label_is_a_blocking_warning():
    avisos = _avisos_desfecho({**ROTULOS_BASE, "desfecho_sugerido.maluco": "x"})
    assert [a.codigo for a in avisos] == ["desfecho_rotulo_invalido"] and avisos[0].bloqueante


def test_base_value_without_label_is_a_blocking_warning():
    parcial = {k: v for k, v in ROTULOS_BASE.items() if not k.endswith(".resolvido")}
    avisos = _avisos_desfecho(parcial)
    assert len(avisos) == 1 and "resolvido" in avisos[0].mensagem and avisos[0].bloqueante


def test_complete_and_legacy_rows_compile_clean():
    assert _avisos_desfecho({**ROTULOS_BASE, **ROTULOS_VENDAS}) == []
    assert _avisos_desfecho({}) == []


def test_invalid_outcome_is_logged_and_counted_not_silent(caplog):
    antes = extracao.DESFECHO_INVALIDOS["inventado"]
    with caplog.at_level(logging.WARNING, logger=extracao.logger.name):
        out = extracao.shape_resumo({"resumo": "ok", "desfecho_sugerido": "inventado"}, extracao.DESFECHOS_BASE)
    assert out["desfecho_sugerido"] == "em_andamento"
    assert extracao.DESFECHO_INVALIDOS["inventado"] == antes + 1
    assert "desfecho.invalido" in caplog.text


def test_sales_value_not_offered_is_invalid_for_a_base_only_agent():
    out = extracao.shape_resumo({"resumo": "ok", "desfecho_sugerido": "qualificado"}, extracao.DESFECHOS_BASE)
    assert out["desfecho_sugerido"] == "em_andamento"
    assert extracao.shape_resumo({"resumo": "ok", "desfecho_sugerido": "resolvido"}, extracao.DESFECHOS_BASE)["desfecho_sugerido"] == "resolvido"
