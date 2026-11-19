"""Diretor de Criacao: the toolset wiring and the deterministic eval checks, driven by Fakes (no model, US$ 0).

Golden: a well-formed reply passes on every tenant world. Mutants: each broken rule is caught by its own code.
The LIVE-model suite (the prompt itself) is owner/eval-loop gated; these are the mechanism the loop scores with."""
from __future__ import annotations

import json

import pytest
from noctusai_lib.integrations.llm import ToolCall

from app.clients.social_wiring import JULIA_TOOL_UNAVAILABLE
from app.criacao.ferramentas import CRIACAO_TOOLS, MAX_CHAMADAS_POR_TURNO, construir_toolset_criacao, schema_de
from app.criacao.saida import avaliar_saida, extrair_publicacoes
from app.studio.ferramentas_registry import ferramenta_conhecida

from .mundo import MARCA, MUTANTES, ORG, URL_PESQUISA, mundo, percorrer, resposta, turno


def test_every_tool_is_known_to_the_studio_allowlist():
    assert all(ferramenta_conhecida(n) for n in CRIACAO_TOOLS)


def test_no_schema_lets_the_model_name_the_brand_or_org():
    for nome in CRIACAO_TOOLS:
        props = schema_de(nome)["properties"]
        assert not {"marca_id", "org_id"} & set(props)
        assert schema_de(nome)["additionalProperties"] is False


@pytest.mark.asyncio
async def test_marca_is_injected_server_side_and_estrutura_detalhe_gets_none():
    t, sw = turno(mundo("metodo9"))
    ts = construir_toolset_criacao(t)
    await ts.handler(ToolCall("1", "cerebros", {}))
    await ts.handler(ToolCall("2", "estrutura_detalhe", {"codigo": 101}))
    por_nome = {n: a for _o, n, a in sw.criacao_calls}
    assert por_nome["cerebros"]["marca_id"] == str(MARCA)
    assert "marca_id" not in por_nome["estrutura_detalhe"]
    assert all(o == ORG for o, _n, _a in sw.criacao_calls)


@pytest.mark.asyncio
async def test_model_supplied_marca_is_refused_by_the_strict_schema():
    t, sw = turno(mundo("metodo9"))
    r = await construir_toolset_criacao(t).handler(ToolCall("1", "cerebros", {"marca_id": "x"}))
    assert r.is_error and json.loads(r.content)["codigo"] == "argumentos_invalidos"
    assert sw.criacao_calls == []


@pytest.mark.asyncio
async def test_unavailable_sw_is_a_coded_error_never_an_exception():
    t, _ = turno(mundo("metodo9"), token=False)
    r = await construir_toolset_criacao(t).handler(ToolCall("1", "cerebros", {}))
    assert r.is_error and json.loads(r.content) == JULIA_TOOL_UNAVAILABLE


@pytest.mark.asyncio
async def test_tool_loop_is_capped():
    t, _ = turno(mundo("metodo9"))
    ts = construir_toolset_criacao(t)
    for i in range(MAX_CHAMADAS_POR_TURNO + 1):
        r = await ts.handler(ToolCall(str(i), "treinamentos", {}))
    assert r.is_error and json.loads(r.content)["codigo"] == "limite_ferramentas"


@pytest.mark.asyncio
@pytest.mark.parametrize("nome", ["metodo9", "sem_metodo", "sem_voz"])
async def test_golden_passes_on_every_world(nome):
    m = mundo(nome)
    t, _ = turno(m)
    await percorrer(t, m.caminho)
    voz = "amostras" if m.voz else "sem amostras"
    assert avaliar_saida(resposta(voz=voz), t.resultados, cta_proibidos=m.cta_proibidos, nomes_proibidos=m.nomes_proibidos) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mutante", sorted(MUTANTES))
async def test_each_broken_rule_is_caught_by_its_own_code(mutante):
    m = mundo("metodo9")
    t, _ = turno(m)
    await percorrer(t, m.caminho)
    texto, codigo = MUTANTES[mutante]()
    falhas = avaliar_saida(texto, t.resultados, cta_proibidos=m.cta_proibidos, nomes_proibidos=m.nomes_proibidos)
    assert any(f.startswith(codigo) for f in falhas), (mutante, falhas)


@pytest.mark.asyncio
async def test_no_voice_samples_path_says_so_and_never_pretends():
    """The pilot's gap: voz_amostras empty AND no voice brain -> the block must say 'sem amostras'."""
    m = mundo("sem_voz")
    t, _ = turno(m)
    await percorrer(t, m.caminho)
    fingida = avaliar_saida(resposta(voz="amostras"), t.resultados, cta_proibidos=m.cta_proibidos)
    assert "pub1:voz_fingida" in fingida
    assert avaliar_saida(resposta(voz="sem amostras"), t.resultados, cta_proibidos=m.cta_proibidos) == []


@pytest.mark.asyncio
async def test_voice_brain_fallback_counts_as_voice_when_the_tool_is_empty():
    """The pilot shape: tool empty, but a non-empty brain named 'Amostras de voz' -> the voice exists; declaring none is wrong."""
    m = mundo("sem_metodo")
    t, _ = turno(m)
    await percorrer(t, m.caminho)
    assert "pub1:voz_ignorada" in avaliar_saida(resposta(voz="sem amostras"), t.resultados, cta_proibidos=m.cta_proibidos)
    assert avaliar_saida(resposta(voz="cérebro: Amostras de voz"), t.resultados, cta_proibidos=m.cta_proibidos) == []


@pytest.mark.asyncio
async def test_a_tenant_without_a_method_is_not_forced_into_nine_blocks():
    m = mundo("sem_metodo")
    t, _ = turno(m)
    await percorrer(t, m.caminho)
    cerebros = next(p for n, p in t.resultados if n == "cerebros")
    assert not any(c["tipo"] == "metodo" for c in cerebros["cerebros"])
    assert avaliar_saida(resposta(voz="cérebro: Amostras de voz"), t.resultados, cta_proibidos=m.cta_proibidos) == []


def test_publicacao_block_parses():
    texto = resposta()
    pubs = extrair_publicacoes(texto)
    assert len(pubs) == 1 and pubs[0].get("fontes").startswith(URL_PESQUISA)
