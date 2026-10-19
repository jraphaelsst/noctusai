"""The closed block list + default stage map (maya-blocks CONTRACT §1): parity with the DB and the real defaults."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

from app.modules.atendimento_blocos.blocos import (
    BLOCOS,
    ETAPAS_PADRAO,
    NOMES_BLOCOS,
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    ConfigBloco,
    config_padrao,
    dono,
    sobreposicoes,
)

BACKEND = Path(__file__).resolve().parents[3]


def _sql(sufixo: str) -> str:
    raw = migration_path(BACKEND, sufixo).read_text(encoding="utf-8")
    return " ".join(re.sub(r"--[^\n]*", "", raw).split())


def test_the_constant_mirrors_every_db_check_of_286():
    sql = _sql("atendimento_blocos_supervisao")
    listas = re.findall(r"bloco IN \(([^)]*)\)", sql)
    assert len(listas) >= 4  # atendimento_blocos, handoffs x2, scorecards
    for lista in listas:
        assert {v.strip().strip("'") for v in lista.split(",")} == set(NOMES_BLOCOS)


def test_blocks_are_ordered_and_sdr_owns_no_pipeline():
    assert [b.ordem for b in BLOCOS] == list(range(1, 7))
    assert NOMES_BLOCOS[0] == "sdr" and BLOCOS[0].pipeline is None and ETAPAS_PADRAO["sdr"] == ()
    assert BLOCOS[0].agent_key_padrao == "lead-imob"  # Julia = studio key lead-imob, never `julia`
    assert all(b.agent_key_padrao is None for b in BLOCOS[1:])


def test_the_default_map_covers_exactly_the_060_default_stages_disjointly():
    sql = _sql("negociacoes_venda_to_atendimentos")
    defaults = set(re.findall(r"\(p_org_id, '(funil|processos_venda)', '([a-z0-9_]+)'", sql))
    mapeadas = {(b.pipeline, s) for b in BLOCOS for s in ETAPAS_PADRAO[b.bloco]}
    assert defaults and mapeadas == defaults
    padrao = {b.bloco: config_padrao(b.bloco) for b in BLOCOS}
    assert sobreposicoes(padrao) == []


def test_defaults_are_off():
    assert all(config_padrao(b.bloco).ativo is False and config_padrao(b.bloco).origem == "padrao" for b in BLOCOS)


def test_dono_resolves_by_pipeline_and_slug():
    padrao = {b.bloco: config_padrao(b.bloco) for b in BLOCOS}
    assert dono(padrao, PIPELINE_FUNIL, "visitas") == "atendimento"
    assert dono(padrao, PIPELINE_FUNIL, "proposta_decisao") == "negociacao"
    assert dono(padrao, PIPELINE_PROCESSOS, "assinatura") == "juridico"
    assert dono(padrao, PIPELINE_PROCESSOS, "nota_fiscal") == "contador"
    assert dono(padrao, PIPELINE_FUNIL, "assinatura") is None  # right slug, wrong pipeline
    assert dono(padrao, PIPELINE_FUNIL, "pos_venda") is None and dono(padrao, None, "visitas") is None


def test_overlap_detection_names_the_slug_and_both_blocks():
    cfg = {b.bloco: config_padrao(b.bloco) for b in BLOCOS}
    cfg["atendimento"] = ConfigBloco("atendimento", None, True, ("qualificacao", "negociacao"), "org")
    assert sobreposicoes(cfg) == [("negociacao", "atendimento", "negociacao")]
