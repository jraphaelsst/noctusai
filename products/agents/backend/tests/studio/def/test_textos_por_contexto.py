"""Q7: a system text is required only when the agent uses what shows it (a tool in its EFFECTIVE tool rows).

Owner rule (2026-11-10): "separate by context -- base text on base, sdr on sdr, julia's on julia". Implemented as
``TextoSpec.ferramentas`` (required iff any of those tools is active), never a layer name in code."""
from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import replace

from app.channels import tool_registry as tr
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.compiler import compile_prompt
from app.studio.models import FerramentaData
from app.studio.textos_registry import (
    CODIGOS_RECUSA,
    CODIGOS_RECUSA_OPCIONAIS,
    RECUSAS_POR_FERRAMENTA,
    TEXTOS,
    TextoSpec,
    chaves_exigidas,
)

_helpers = importlib.import_module("tests.studio.def.test_compiler_conteudo")  # ``def`` is a keyword: no plain import
BASE_TEXTOS, _codes, _conteudo, _inp = _helpers.BASE_TEXTOS, _helpers._codes, _helpers._conteudo, _helpers._inp

#: A generic assistant: it can hand off, close, open skills and record a data-subject request -- no qualification,
#: no credit consent, no property tools.
BASE_ONLY = frozenset({"handoff", "encerrar", "abrir_skill", "ler_arquivo_skill", "registrar_solicitacao_titular"})
#: Codes any tool may return (their row is owed by every channel agent).
GENERICOS = {"limite_recusas", "indisponivel", "limite_ferramentas", "argumentos_invalidos"}


def _exigidas(ferramentas, *, qualificacao=False, **kw):
    return chaves_exigidas(
        tool_policy={}, tem_skills=True, com_cliente=False, canal=True, com_qualificacao=qualificacao,
        ferramentas_ativas=ferramentas, **kw)


class TestBaseOnlyOwesNoSalesTexts:
    def test_a_base_only_tool_set_needs_none_of_the_sales_context_texts(self):
        exig = _exigidas(BASE_ONLY)
        sdr = {k for k, s in TEXTOS.items() if s.ferramentas or s.condicao == "qualificacao"}
        assert sdr, "the registry must carry context-owned texts"
        assert not (exig & {k for k in sdr if k.startswith(("credito.", "reengajamento.", "contexto.rotulo_", "contexto.titulo_credito", "contexto.titulo_reeng"))})
        for k in ("credito.pedir", "credito.consentiu", "credito.recusou", "contexto.titulo_credito",
                  "reengajamento.minutos", "reengajamento.regua", "contexto.titulo_reengajamento",
                  "ferramenta.resultado.concluido", "ferramenta.handoff.resumo_conclusao",
                  "contexto.rotulo_estagio", "contexto.rotulo_score",
                  "ferramenta.resultado.recusa.consentimento_sem_evidencia",
                  "ferramenta.resultado.recusa.nao_pode_ofertar",
                  "ferramenta.resultado.recusa.trecho_curto"):
            assert k not in exig, k

    def test_it_still_owes_the_generic_and_its_own_tools_refusals(self):
        exig = _exigidas(BASE_ONLY)
        for c in GENERICOS - {"argumentos_invalidos"}:
            assert f"ferramenta.resultado.recusa.{c}" in exig, c
        for c in ("skill_inexistente", "arquivo_inexistente", "motivo_texto_ausente", "opt_out_sem_evidencia",
                  "trecho_nao_confere"):
            assert f"ferramenta.resultado.recusa.{c}" in exig, c
        assert "ferramenta.resultado.encerrado" in exig

    def test_adding_a_tool_adds_exactly_its_texts(self):
        antes = _exigidas(BASE_ONLY)
        depois = _exigidas(BASE_ONLY | {"consentimento_credito"})
        assert depois - antes == {
            "credito.pedir", "credito.consentiu", "credito.recusou", "contexto.titulo_credito",
            "ferramenta.resultado.recusa.credito_inativo", "ferramenta.resultado.recusa.consentimento_sem_evidencia",
        }

    def test_the_qualification_labels_follow_the_standard(self):
        assert "contexto.rotulo_estagio" not in _exigidas(BASE_ONLY)
        assert "contexto.rotulo_estagio" in _exigidas(BASE_ONLY, qualificacao=True)

    def test_a_tool_that_is_not_active_owes_nothing_even_if_registered(self):
        assert _exigidas(frozenset()) <= _exigidas(BASE_ONLY)


class TestJuliaKeepsExactlyTodaysSet:
    def test_with_every_tool_active_the_required_set_is_the_pre_split_set(self):
        legado = {k: replace(s, ferramentas=frozenset()) for k, s in TEXTOS.items()}
        for qual in (True, False):
            hoje = _exigidas(frozenset(FERRAMENTAS_CONHECIDAS), qualificacao=qual, com_dados_org=True)
            antes = chaves_exigidas(
                tool_policy={}, tem_skills=True, com_cliente=False, canal=True, com_qualificacao=qual,
                com_dados_org=True, registro=legado, ferramentas_ativas=frozenset())
            # the only legitimately new keys of this slice are the optional ones, never required
            assert hoje == antes or not qual or hoje - antes == set(), (hoje ^ antes)
        # with the standard: nothing was lost
        legado_set = chaves_exigidas(
            tool_policy={}, tem_skills=True, com_cliente=False, canal=True, com_qualificacao=True,
            com_dados_org=True, registro=legado, ferramentas_ativas=frozenset())
        hoje = _exigidas(frozenset(FERRAMENTAS_CONHECIDAS), qualificacao=True, com_dados_org=True)
        assert hoje == legado_set

    def test_emergencia_aberta_is_optional_and_belongs_to_encerrar(self):
        assert "emergencia_aberta" in CODIGOS_RECUSA_OPCIONAIS
        assert TEXTOS["ferramenta.resultado.recusa.emergencia_aberta"].obrigatoria is False
        assert RECUSAS_POR_FERRAMENTA["emergencia_aberta"] == frozenset({"encerrar"})
        assert "ferramenta.resultado.recusa.emergencia_aberta" not in _exigidas(frozenset(FERRAMENTAS_CONHECIDAS), qualificacao=True)


class TestSpecSemantics:
    def test_ferramentas_and_condicao_must_both_hold(self):
        reg = {"x.y": TextoSpec("x", aplica_a="canal", condicao="qualificacao", ferramentas=frozenset({"t"}))}
        kw = dict(tool_policy={}, tem_skills=False, com_cliente=False, canal=True, registro=reg)
        assert chaves_exigidas(ferramentas_ativas={"t"}, com_qualificacao=True, **kw) == {"x.y"}
        assert chaves_exigidas(ferramentas_ativas={"t"}, com_qualificacao=False, **kw) == set()
        assert chaves_exigidas(ferramentas_ativas=set(), com_qualificacao=True, **kw) == set()

    def test_the_registry_maps_only_known_codes_and_tools(self):
        todos = set(CODIGOS_RECUSA) | set(CODIGOS_RECUSA_OPCIONAIS)
        assert set(RECUSAS_POR_FERRAMENTA) <= todos
        assert all(t in tr.TOOLS for ts in RECUSAS_POR_FERRAMENTA.values() for t in ts)
        assert GENERICOS - {"argumentos_invalidos"} <= todos - set(RECUSAS_POR_FERRAMENTA)


class TestCompileFollowsTheEffectiveTools:
    def _sem(self, prefixos):
        return tuple(t for t in BASE_TEXTOS if not t.chave.startswith(prefixos))

    def test_credit_texts_are_a_blocking_gap_only_when_the_agent_has_the_tool(self):
        sem_credito = self._sem(("credito.", "contexto.titulo_credito", "ferramenta.resultado.recusa.credito_inativo",
                                 "ferramenta.resultado.recusa.consentimento_sem_evidencia"))
        so_handoff = _conteudo(textos=sem_credito)
        assert "texto_ausente" not in _codes(compile_prompt(_inp(so_handoff)))
        com_credito = _conteudo(
            textos=sem_credito,
            ferramentas=(FerramentaData("handoff", "x"), FerramentaData("consentimento_credito", "Registra o consentimento.")))
        assert "texto_ausente" in _codes(compile_prompt(_inp(com_credito)))
        inativa = _conteudo(
            textos=sem_credito,
            ferramentas=(FerramentaData("handoff", "x"), FerramentaData("consentimento_credito", "x", ativo=False)))
        assert "texto_ausente" not in _codes(compile_prompt(_inp(inativa)))


def _codigos_literais(call: ast.Call) -> set[str]:
    if len(call.args) < 2:
        return set()
    a = call.args[1]
    nos = a.values if isinstance(a, ast.BoolOp) else [a.body, a.orelse] if isinstance(a, ast.IfExp) else [a]
    return {v.value for v in nos if isinstance(v, ast.Constant)}


def _chamados(h: ast.AsyncFunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(h) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


class TestRecusasCallSitesMatchTheMap:
    def test_every_recusa_call_site_sits_in_a_handler_whose_tool_maps_to_that_code(self):
        fn = next(n for n in ast.walk(ast.parse(inspect.getsource(tr)))
                  if isinstance(n, ast.FunctionDef) and n.name == "construir_toolset")
        despacho = next(n for n in ast.walk(fn) if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "despacho")
        handler_de_ferramenta: dict[str, str] = {}
        for k, v in zip(despacho.value.keys, despacho.value.values):
            if isinstance(v, ast.Lambda):  # ``lambda a: _concluir()``
                v = v.body.func
            handler_de_ferramenta[v.id] = k.value
        # a nested helper (a shared core) answers for every tool whose handler reaches it, directly or through another
        # helper: its refusal literals need to be tied to AT LEAST ONE of those tools
        funcoes = {n.name: n for n in ast.walk(fn) if isinstance(n, ast.AsyncFunctionDef)}
        ferramentas_de: dict[str, set[str]] = {h: {t} for h, t in handler_de_ferramenta.items()}
        mudou = True
        while mudou:
            mudou = False
            for nome, tools in list(ferramentas_de.items()):
                for chamado in (_chamados(funcoes[nome]) & funcoes.keys()) - {nome}:
                    antes = len(ferramentas_de.setdefault(chamado, set()))
                    ferramentas_de[chamado] |= tools
                    mudou |= len(ferramentas_de[chamado]) != antes
        achados = 0
        for nome, h in funcoes.items():
            for c in (n for n in ast.walk(h) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_recusa"):
                for codigo in _codigos_literais(c):
                    if nome not in ferramentas_de:  # the shared dispatcher: GENERIC codes only
                        assert codigo in GENERICOS, (nome, codigo)
                        continue
                    achados += 1
                    assert ferramentas_de[nome] & RECUSAS_POR_FERRAMENTA.get(codigo, frozenset()), (
                        f"{nome} ({sorted(ferramentas_de[nome])}) refuses with {codigo!r} but the registry ties that text to none of its tools")
        assert achados >= 20
