"""The runtime reads ONLY the system texts the registry requires for that agent (prod 2026-11-18: an agent with no qualification
standard was evaluated, its dossier carried the null standard's stage, and ``contexto.rotulo_estagio`` -- owed only WITH a
standard -- was read from content that never had to carry it: 46 of 46 eval cases errored)."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from app.channels.contexto import Dossie, render_contexto_system
from app.channels.turno import _dossie
from app.qualificacao.models import padrao_nulo
from app.studio.models import ConteudoBundle, TextoData
from app.studio.textos_registry import chaves_exigidas
from tests.channels.test_julia_tools_foundation import AGORA


def _bundle(chaves: set[str]) -> ConteudoBundle:
    campos = {f.name for f in dataclasses.fields(TextoData)}
    textos = []
    for c in sorted(chaves):
        kw = {k: v for k, v in {"chave": c, "conteudo": "x"}.items() if k in campos}
        textos.append(TextoData(**kw))
    return ConteudoBundle(textos=tuple(textos))


_ESTADO = SimpleNamespace(
    encerrado=False, atendente_nome="Ana", origem=None, credito=None, reengajamento=None)
_ESTADO_NULO = SimpleNamespace(valores={}, estagio="sem_qualificacao", score=0, faltando=[])


def _exigidas(*, qualificacao: bool) -> set[str]:
    return chaves_exigidas(
        tool_policy={}, tem_skills=False, com_cliente=False, canal=True, ferramentas_ativas=frozenset(),
        com_qualificacao=qualificacao)


def test_null_standard_dossier_has_no_qualification_lines():
    d = _dossie(padrao_nulo(), _ESTADO_NULO, [], None)
    assert d.estagio is None and d.score is None and not d.faltando and not d.oferecidos and not d.gostou


def test_agent_without_a_standard_renders_with_exactly_the_required_texts():
    exigidas = _exigidas(qualificacao=False)
    assert "contexto.rotulo_estagio" not in exigidas
    dossie = _dossie(padrao_nulo(), _ESTADO_NULO, [], None)
    out = render_contexto_system(
        _bundle(exigidas), agora=AGORA, fuso="America/Sao_Paulo", estado=_ESTADO, dossie=dossie)
    assert "sem_qualificacao" not in out


def test_agent_with_a_standard_renders_every_qualification_line_from_required_texts():
    exigidas = _exigidas(qualificacao=True)
    assert "contexto.rotulo_estagio" in exigidas
    dossie = Dossie(estagio="em_conversa", score=3, faltando=["a"], oferecidos=["c1"], gostou=["c1"])
    out = render_contexto_system(
        _bundle(exigidas), agora=AGORA, fuso="America/Sao_Paulo", estado=_ESTADO, dossie=dossie)
    assert "em_conversa" in out
